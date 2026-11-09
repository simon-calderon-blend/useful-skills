"""Ejecución del plan: el ÚNICO camino que escribe en AWS (``launch.py --execute``).

Orden (todo lo que puede fallar falla ANTES de tocar el dispatch):
plan_id -> ambiente/perfil/cuenta -> procedencia del plan -> corrida/miga previas -> deriva de
configuración -> secreto/token/aud -> túnel + sondeo -> estrategia -> miga + pausa -> línea OFF ->
POST+siembra por claim -> (finally) restaurar dispatch, borrar miga, cerrar túnel -> reporte.

Errores previos a la primera escritura => Outcome(1, {"abort": ...}). Una vez creada la miga todo
error se reporta en el ``launch_report.json`` (``error``), nunca como "abortado antes de escribir".
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, ContextManager, Mapping
from urllib.parse import urlsplit

from . import api, auth, dispatch, envs, monitor, structuring
from . import live as live_mod
from . import plan as plan_mod
from .checks import TERMINAL_TRACKER
from .runindex import RunIndex, RunIndexError
from .runner import Clients
from .seed import SeedItem, parse_s3_uri, seed_items

log = logging.getLogger("iae_launch.launch")
MIN_SETTLE = 61  # el agente de AppConfig sondea cada 60 s (CDK appconfig-agent-extension.ts:137)
TOKEN_MAX_AGE = 240.0      # solo si el token no trae exp
TOKEN_EXP_MARGIN = 60.0    # se renueva cuando faltan menos de estos segundos para exp
# El agente de AppConfig del throttle controller puede servir el valor viejo en la primera
# invocación tras descongelar el contenedor (evidencia real: ejecuciones iniciadas 2 min después
# del cierre). Solo es seguro sembrar tras ver "Dispatch feature flag is OFF" en sus logs.
OFF_MARKER = "Dispatch feature flag is OFF"
OFF_TIMEOUT = 420.0
OFF_POLL = 15.0
FALLBACK_LOOKBACK_MIN = 15
STOP_VERIFY_TIMEOUT = 60.0
STOP_VERIFY_POLL = 5.0
TRACKER_HINT = "revisa el tracker (DynamoDB) antes de reintentar: el POST pudo haber sido recibido"


@dataclass
class Deps:
    clients: Clients
    environ: Mapping[str, str] = field(repr=False)
    token_fn: Callable[[envs.EnvSpec, str], auth.Token] = field(repr=False)
    open_tunnel: Callable[[str], ContextManager[Any]]
    gather: Callable[[], live_mod.LivePaths]
    reload_dispatch: Callable[[], live_mod.Deployed]
    api_url: Callable[[], str]
    state_home: Path
    now: Callable[[], datetime]
    post_fn: Callable[..., api.IniciarResult] = api.post_iniciar
    probe_fn: Callable[..., int] = api.probe_proceso
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic


@dataclass
class Outcome:
    exit_code: int
    report: dict = field(default_factory=dict)


class _Abort(Exception):
    pass


class _TokenHolder:
    """Token con renovación por ``exp`` (menos un margen); sin ``exp``, por antigüedad."""

    def __init__(self, deps: Deps, spec: envs.EnvSpec):
        self.deps, self.spec = deps, spec
        self.token = self._fetch()

    def __repr__(self) -> str:
        return "_TokenHolder(***)"

    def _fetch(self) -> auth.Token:
        token = self.deps.token_fn(self.spec, self.deps.environ[envs.SECRET_ENV_VAR])
        self.at = self.deps.clock()
        self.exp = auth.decode_claims(token).get("exp")
        return token

    def fresh(self) -> auth.Token:
        if self.exp is not None:
            stale = self.exp - self.deps.now().timestamp() < TOKEN_EXP_MARGIN
        else:
            stale = self.deps.clock() - self.at > TOKEN_MAX_AGE
        if stale:
            self.token = self._fetch()
        return self.token


def throttle_log_group(env: str) -> str:
    return f"/aws/lambda/adr-{env}-medicalaudit-api-throttle-controller"


def wait_for_off(logs: Any, env: str, since: datetime, *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, timeout: float | None = None) -> None:
    """Espera una línea OFF del throttle controller posterior a ``since`` (logs:FilterLogEvents)."""
    timeout = OFF_TIMEOUT if timeout is None else timeout
    deadline = clock() + timeout
    start_ms = int(since.timestamp() * 1000)
    while True:
        token = None
        while True:
            kwargs = {"logGroupName": throttle_log_group(env), "startTime": start_ms,
                      "filterPattern": f'"{OFF_MARKER}"'}
            if token:
                kwargs["nextToken"] = token
            resp = logs.filter_log_events(**kwargs)
            if any(OFF_MARKER in e.get("message", "") for e in resp.get("events", [])):
                return
            token = resp.get("nextToken")
            if not token:
                break
        if clock() >= deadline:
            raise dispatch.DispatchError(
                f"el throttle controller no registró '{OFF_MARKER}' en {timeout:g} s: el flag cerrado "
                "no está vigente en su caché; no se siembra")
        sleep(OFF_POLL)


def describe(plan_path: Path) -> str:
    plan = plan_mod.load_plan(plan_path)
    d = plan["dispatch"]
    lines = [f"plan {plan['plan_id']} ({plan['env']}, run {plan['run_id']}) — NO se ejecutó nada (falta --execute).",
             "Acciones al ejecutar:"]
    if d["was_enabled"]:
        lines.append("  1. pausar dispatch (cerrar), esperar el asentamiento y la línea OFF del throttle "
                     f"controller; luego restaurarlo a {d['restore_to']}")
    elif d["restore_to"]:
        lines.append("  1. el dispatch está cerrado: se ABRIRÁ al terminar de sembrar")
    else:
        lines.append("  1. el dispatch está cerrado y seguirá cerrado (sin cambios)")
    for c in plan["claims"]:
        origin = f" (request de {c['request_source_pid']})" if c.get("request_source_pid") else ""
        lines.append(f"  - POST /iniciar {c['folder']}{origin} y sembrar {len(c['seed_items'])} objetos en "
                     f"s3://{plan['live']['workarea_bucket']}/{plan['live']['base_prefix']}/<pid>/")
    cmd = plan_mod.launch_command(plan["env"], plan_path, plan["plan_id"])
    lines += ["Comando (con el secreto inyectado por asm-exec):", "  " + " ".join(cmd)]
    return "\n".join(lines)


# ------------------------------------------------------------------ verificación previa a escribir
def _allowed_roots(plan: dict, run_dir: Path) -> list[Path]:
    roots = [run_dir.resolve()]
    decisions = plan.get("decisions", {})
    if decisions.get("source_dir"):
        roots.append(Path(decisions["source_dir"]).resolve())
    ref = decisions.get("structuring") or ""
    if ref.startswith("local:"):
        roots.append(Path(ref.split(":", 1)[1]).resolve())
    return roots


def _check_item(item: dict, folder: str, plan: dict, roots: list[Path], spec: envs.EnvSpec) -> None:
    dest = item["dest_suffix"]
    if dest.startswith("/") or ".." in dest.split("/"):
        raise _Abort(f"{folder}: destino de siembra inválido {dest!r}")
    if item["kind"] == "put":
        path = Path(item["source"]).resolve()
        if not any(path == r or r in path.parents for r in roots):
            raise _Abort(f"{folder}: el archivo local {item['source']} está fuera de las carpetas del plan")
        if not path.is_file() or path.stat().st_size != item.get("size"):
            raise _Abort(f"{item['source']} cambió o no existe desde el plan")
        return
    bucket, key = parse_s3_uri(item["source"])
    workarea = f"adr-{spec.name}-medicalaudit-workarea"
    ok = ((bucket == workarea and key.startswith(f"{plan['live']['base_prefix']}/"))
          or (bucket == structuring.MAI_BUCKETS[spec.name] and key.startswith("runs/")))
    if not ok:
        raise _Abort(f"{folder}: la copia desde {item['source']} no está en el workarea/MAI de {spec.name}")


def _refuse_previous_run(plan: dict, run_dir: Path, deps: Deps, spec: envs.EnvSpec) -> None:
    if (run_dir / "launch_report.json").exists():
        raise _Abort(f"{run_dir} ya tiene launch_report.json: esta corrida ya se ejecutó "
                     "(relanzar duplicaría procesos); genera otro plan con otro --run-id")
    index_path = run_dir / "process_index.csv"
    if index_path.exists():
        try:
            rows = RunIndex(index_path).rows
        except RunIndexError as exc:
            raise _Abort(str(exc)) from None
        launched = [c["folder"] for c in plan["claims"] if rows.get(c["folder"], {}).get("pid")]
        if launched:
            raise _Abort(f"process_index.csv ya tiene pids para {', '.join(launched)}: ya se lanzaron")
    crumbs = dispatch.existing_breadcrumbs(spec.name, deps.state_home)
    if crumbs:
        raise _Abort("hay una miga de pausa (otra corrida o el runner): " + ", ".join(map(str, crumbs))
                     + "; revisa con launch.py --recover")


def _verify_plan(plan_path: Path, plan_id: str, deps: Deps):
    try:
        plan = plan_mod.load_plan(plan_path)
    except (plan_mod.PlanError, OSError, ValueError) as exc:
        raise _Abort(f"plan inválido: {exc}") from None
    if plan["plan_id"] != plan_id:
        raise _Abort(f"plan_id {plan_id} no coincide con el del plan ({plan['plan_id']}); vuelve a correr prepare.py")
    if plan["env"] not in envs.ENVS:
        raise _Abort(f"ambiente {plan['env']!r} no soportado")
    spec = envs.get_env(plan["env"])
    if envs.is_sensitive_profile(plan["profile"]):
        raise _Abort(f"el perfil {plan['profile']} es sensible: no se escribe con él")
    if plan["account_id"] != spec.account_id:
        raise _Abort("la cuenta del plan no corresponde al ambiente")
    account = deps.clients["sts"].get_caller_identity()["Account"]
    if account != plan["account_id"]:
        raise _Abort(f"sts responde cuenta {account}, el plan es de {plan['account_id']}")
    # Procedencia: un plan editado a mano con el hash recalculado no debe poder apuntar a otro bucket/API.
    if plan["live"]["workarea_bucket"] != f"adr-{spec.name}-medicalaudit-workarea":
        raise _Abort(f"el bucket del plan {plan['live']['workarea_bucket']!r} no es el workarea de {spec.name}")
    fresh_url = deps.api_url()
    if urlsplit(fresh_url).hostname != urlsplit(plan["live"]["api_base_url"]).hostname:
        raise _Abort("el host del API del plan no coincide con el API vivo del ambiente")
    roots = _allowed_roots(plan, plan_path.parent)
    for claim in plan["claims"]:
        for item in claim["seed_items"]:
            _check_item(item, claim["folder"], plan, roots, spec)
    _refuse_previous_run(plan, plan_path.parent, deps, spec)
    return plan, spec


def _verify_live(plan: dict, deps: Deps) -> live_mod.LivePaths:
    try:
        live = deps.gather()
    except live_mod.LiveConfigError as exc:
        raise _Abort(f"no se pudo leer la configuración viva: {exc}") from None
    if live.in_progress:
        raise _Abort(f"hay deployments de AppConfig en curso: {live.in_progress}")
    if live.base_prefix != plan["live"]["base_prefix"]:
        raise _Abort(f"base_prefix del plan {plan['live']['base_prefix']!r} != vivo {live.base_prefix!r}")
    drift = live_mod.version_drift(plan["live"]["versions"], live.versions)
    if drift:
        raise _Abort("config cambió desde el plan; vuelve a correr prepare.py: "
                     + ", ".join(f"{k}: {a} -> {b}" for k, (a, b) in drift.items()))
    return live


def _preflight_auth(plan: dict, spec: envs.EnvSpec, deps: Deps) -> _TokenHolder:
    if not deps.environ.get(envs.SECRET_ENV_VAR):
        cmd = " ".join(plan_mod.launch_command(plan["env"], Path("<plan.json>"), plan["plan_id"]))
        raise _Abort(f"falta {envs.SECRET_ENV_VAR}; corre con asm-exec: {cmd}")
    holder = _TokenHolder(deps, spec)
    auds = auth.audiences(auth.decode_claims(holder.token))
    want = envs.expected_audience(spec.name)
    if want not in auds:
        raise _Abort(f"el token no tiene la aud esperada {want} (aud={auds})")
    return holder


def execute_plan(plan_path: Path, plan_id: str, deps: Deps, *, settle_seconds: float = 75,
                 leave_closed: bool = False) -> Outcome:
    if settle_seconds < MIN_SETTLE:
        raise ValueError(f"--pause-settle-seconds mínimo {MIN_SETTLE} (el agente AppConfig sondea cada 60 s)")
    plan_path = Path(plan_path)
    try:
        plan, spec = _verify_plan(plan_path, plan_id, deps)
        live = _verify_live(plan, deps)
        holder = _preflight_auth(plan, spec, deps)
        return _run(plan, spec, live, holder, deps, plan_path.parent, settle_seconds, leave_closed)
    except _Abort as exc:
        log.error("abortado antes de escribir: %s", exc)
        return Outcome(1, {"abort": str(exc)})
    except Exception as exc:  # noqa: BLE001 - _run reporta sus propios errores post-escritura
        log.error("abortado antes de escribir: %s: %s", type(exc).__name__, exc)
        return Outcome(1, {"abort": f"{type(exc).__name__}: {exc}"})


# ------------------------------------------------------------------ ejecución
def _safe_delete_crumb(env: str, deps: Deps, report: dict) -> None:
    try:
        dispatch.delete_breadcrumb(env, deps.state_home)
    except OSError as exc:
        report["crumb_delete_failed"] = True
        log.error("no se pudo borrar la miga de pausa (%s); bórrala a mano tras revisar", exc)


def _write_report(run_dir: Path, report: dict) -> None:
    try:
        (run_dir / "launch_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        extra = f"no se pudo escribir launch_report.json: {exc}"
        report["error"] = f"{report['error']}; {extra}" if report.get("error") else extra
        log.error("%s", extra)


def _run(plan: dict, spec: envs.EnvSpec, live: live_mod.LivePaths, holder: _TokenHolder, deps: Deps,
         run_dir: Path, settle_seconds: float, leave_closed: bool = False) -> Outcome:
    base_url = plan["live"]["api_base_url"]
    host = urlsplit(base_url).hostname
    deployed = live.dispatch
    was_enabled = dispatch.read_enabled(deployed)
    restore_to = False if leave_closed else plan["dispatch"]["restore_to"]
    need_pause = was_enabled
    after_pause = False if need_pause else was_enabled
    need_restore = restore_to != after_pause
    need_write = need_pause or need_restore
    report: dict = {"run_id": plan["run_id"], "plan_id": plan["plan_id"], "env": plan["env"],
                    "started_at": deps.now().isoformat(), "claims": [], "failures": [],
                    "dispatch": {"before": was_enabled, "after": None, "restore_to": restore_to},
                    "opened_dispatch": False, "restore_failed": False, "left_closed": leave_closed}
    index = RunIndex(run_dir / "process_index.csv")
    appconfig = deps.clients["appconfig"]

    with deps.open_tunnel(host) as tun:
        try:
            status = deps.probe_fn(tun.connection_factory, base_url, holder.fresh(), str(uuid.uuid4()))
            if status != 404:
                raise _Abort(f"el sondeo GET /proceso/<uuid> devolvió {status}, se esperaba 404")
            strategy = dispatch.resolve_strategy_id(appconfig) if need_write else None
            if need_write and strategy is None:
                raise _Abort("no hay estrategia de AppConfig con duración 0 y bake 0 (estrategia)")
            if need_write:
                dispatch.write_breadcrumb(spec.name, deps.state_home, app=deployed.app_id,
                                          was_enabled=was_enabled, restore_to=restore_to,
                                          run_id=plan["run_id"], pid=os.getpid())
        except dispatch.BreadcrumbExists as exc:
            raise _Abort(str(exc)) from None
        crumb_written = need_write
        paused_ok = False
        try:
            if need_pause:
                started = deps.now()
                done = dispatch.set_enabled_fresh(appconfig, deps.reload_dispatch, strategy, False,
                                                  sleep=deps.sleep, clock=deps.clock)
                paused_ok = True
                since = done.completed_at or started  # el OFF debe ser posterior al fin del deployment
                log.info("dispatch cerrado; esperando %s s (mínimo) y luego la línea OFF", settle_seconds)
                deps.sleep(settle_seconds)
            else:  # ya cerrado: exigir igualmente un OFF posterior al último deployment del flag
                since = (dispatch.latest_dispatch_time(appconfig, deployed)
                         or deps.now() - timedelta(minutes=FALLBACK_LOOKBACK_MIN))
            wait_for_off(deps.clients["logs"], spec.name, since, sleep=deps.sleep, clock=deps.clock)
            for claim in plan["claims"]:
                _launch_claim(claim, plan, holder, tun, base_url, deps, index, report)
        except Exception as exc:  # noqa: BLE001 - se reporta; el finally restaura
            log.error("error durante el lanzamiento (después de escribir): %s: %s", type(exc).__name__, exc)
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            _finish_dispatch(report, plan, spec, deps, appconfig, strategy, restore_to, need_restore,
                             need_pause, paused_ok, after_pause, was_enabled, crumb_written, run_dir)
    ok = all(c["status"] == "launched" for c in report["claims"]) and len(report["claims"]) == len(plan["claims"])
    clean = (ok and not report["restore_failed"] and "error" not in report and not report.get("held_closed")
             and not report.get("pause_incomplete"))
    return Outcome(0 if clean else (3 if report["claims"] else 1), report)


def _finish_dispatch(report, plan, spec, deps, appconfig, strategy, restore_to, need_restore, need_pause,
                     paused_ok, after_pause, was_enabled, crumb_written, run_dir) -> None:
    """Estado final del dispatch + reporte. Nunca lanza (salvo BaseException)."""
    hold = any(c["status"] == "seed_failed" for c in report["claims"])
    try:
        if hold:
            # Un proceso aceptado quedó a medio sembrar: abrir el dispatch lo despacharía incompleto.
            report["held_closed"] = True
            report["dispatch"]["after"] = after_pause if (paused_ok or not need_pause) else None
            report["hint"] = (f"siembra incompleta: el dispatch NO se abre. Detén la corrida con "
                              f"`launch.py --stop-run {run_dir} --execute` y luego `--recover`/`--open-dispatch`")
            log.error("%s", report["hint"])
        elif need_restore:
            try:
                dispatch.set_enabled_fresh(appconfig, deps.reload_dispatch, strategy, restore_to,
                                           sleep=deps.sleep, clock=deps.clock)
                report["dispatch"]["after"] = restore_to
                report["opened_dispatch"] = bool(restore_to and not was_enabled)
                if crumb_written:
                    _safe_delete_crumb(spec.name, deps, report)
            except Exception as exc:  # noqa: BLE001 - la miga queda para --recover
                report["restore_failed"] = True
                log.error("NO se pudo restaurar el dispatch (%s: %s); queda la miga de pausa; "
                          "usa launch.py --recover", type(exc).__name__, exc)
        elif need_pause and not paused_ok:  # --leave-dispatch-closed con pausa que no se completó
            report["pause_incomplete"] = True
            report["dispatch"]["after"] = None
            log.error("la pausa del dispatch no se completó: estado desconocido; queda la miga de pausa")
        else:  # estado final intencional (sin cambios, o --leave-dispatch-closed)
            report["dispatch"]["after"] = after_pause
            if crumb_written:
                _safe_delete_crumb(spec.name, deps, report)
    finally:
        report["finished_at"] = deps.now().isoformat()
        _write_report(run_dir, report)


def _launch_claim(claim: dict, plan: dict, holder: _TokenHolder, tun: Any, base_url: str, deps: Deps,
                  index: RunIndex, report: dict) -> int:
    folder = claim["folder"]
    try:
        result = deps.post_fn(tun.connection_factory, base_url, holder.fresh(), claim["body"])
    except api.ApiError as exc:  # el servidor respondió: no se creó proceso
        return _fail(report, folder, "post_failed", None, f"HTTP {exc.status}: {exc.body}")
    except Exception as exc:  # noqa: BLE001 - timeout/transporte: el POST pudo haberse recibido
        return _fail(report, folder, "post_failed", None, f"{type(exc).__name__}: {exc}; {TRACKER_HINT}")
    if result.bad_response:
        return _fail(report, folder, "bad_response", None, f"{result.mensaje}; {TRACKER_HINT}")
    if not result.accepted:
        return _fail(report, folder, "rejected", result.process_id,
                     f"{result.estado}: {result.mensaje}")
    pid = result.process_id
    index.record(folder, pid=pid, descargado=False,
                 s3uri=f"s3://{plan['live']['workarea_bucket']}/{plan['live']['base_prefix']}/{pid}/")
    items = [SeedItem(i["kind"], i["source"], i["dest_suffix"], i["content_type"]) for i in claim["seed_items"]]
    try:
        keys = seed_items(deps.clients["s3"], plan["live"]["workarea_bucket"], plan["live"]["base_prefix"],
                          pid, items)
    except Exception as exc:  # noqa: BLE001 - un claim no tumba el lote
        _fail(report, folder, "seed_failed", pid, f"{type(exc).__name__}: {exc}")
        return 1
    report["claims"].append({"folder": folder, "pid": pid, "status": "launched", "seeded": len(keys)})
    return 1


def _fail(report: dict, folder: str, status: str, pid: str | None, detail: str) -> int:
    entry = {"folder": folder, "pid": pid, "status": status, "detail": detail}
    report["claims"].append(entry)
    report["failures"].append(entry)
    log.error("%s: %s (%s)", folder, status, detail)
    return 0


# ------------------------------------------------------------------ recover / open / stop
def _guard_env(env: str, deps: Deps) -> str | None:
    spec = envs.get_env(env)
    if envs.is_sensitive_profile(spec.profile):
        return f"el perfil {spec.profile} es sensible"
    account = deps.clients["sts"].get_caller_identity()["Account"]
    if account != spec.account_id:
        return f"sts responde cuenta {account}, se esperaba {spec.account_id}"
    return None


def _crumb_owner_alive(crumb: dict | None) -> int | None:
    pid = (crumb or {}).get("pid")
    if isinstance(pid, int) and pid != os.getpid() and dispatch.pid_alive(pid):
        return pid
    return None


def recover(env: str, deps: Deps, *, execute: bool) -> Outcome:
    crumb = dispatch.read_breadcrumb(env, deps.state_home)
    if crumb is None:
        return Outcome(0, {"recover": "sin miga de pausa"})
    if not execute:
        return Outcome(0, {"recover": "pendiente", "breadcrumb": crumb,
                           "action": f"restaurar dispatch a {crumb['restore_to']} (requiere --execute)"})
    owner = _crumb_owner_alive(crumb)
    if owner:
        return Outcome(1, {"abort": f"el proceso {owner} (launch.py en curso) es dueño de la miga; "
                                    "espera a que termine"})
    problem = _guard_env(env, deps)
    if problem:
        return Outcome(1, {"abort": problem})
    strategy = dispatch.resolve_strategy_id(deps.clients["appconfig"])
    if strategy is None:
        return Outcome(1, {"abort": "no hay estrategia de AppConfig con duración 0 y bake 0"})
    dispatch.set_enabled_fresh(deps.clients["appconfig"], deps.reload_dispatch, strategy,
                               bool(crumb["restore_to"]), sleep=deps.sleep, clock=deps.clock)
    dispatch.delete_breadcrumb(env, deps.state_home)
    return Outcome(0, {"recover": "restaurado", "restore_to": crumb["restore_to"]})


def open_dispatch(env: str, deps: Deps, *, execute: bool) -> Outcome:
    """Abre el dispatch más tarde (tras ``--leave-dispatch-closed``)."""
    if not execute:
        return Outcome(0, {"open": "pendiente: abrir el dispatch requiere --execute"})
    owner = _crumb_owner_alive(dispatch.read_breadcrumb(env, deps.state_home))
    if owner:
        return Outcome(1, {"abort": f"el proceso {owner} (launch.py en curso) es dueño de la miga; "
                                    "espera a que termine"})
    problem = _guard_env(env, deps)
    if problem:
        return Outcome(1, {"abort": problem})
    if dispatch.read_enabled(deps.reload_dispatch()):
        return Outcome(0, {"open": "ya estaba abierto"})
    strategy = dispatch.resolve_strategy_id(deps.clients["appconfig"])
    if strategy is None:
        return Outcome(1, {"abort": "no hay estrategia de AppConfig con duración 0 y bake 0"})
    dispatch.set_enabled_fresh(deps.clients["appconfig"], deps.reload_dispatch, strategy, True,
                               sleep=deps.sleep, clock=deps.clock)
    dispatch.delete_breadcrumb(env, deps.state_home)
    return Outcome(0, {"open": "abierto"})


def _running_by_pid(sfn: Any, arn: str, pids: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    token = None
    while True:
        resp = sfn.list_executions(stateMachineArn=arn, statusFilter="RUNNING",
                                   **({"nextToken": token} if token else {}))
        for e in resp.get("executions", []):
            for pid in pids:
                if e["name"].startswith(f"{pid}-"):
                    found[pid] = e["executionArn"]
        token = resp.get("nextToken")
        if not token:
            return found


def stop_run(run_dir: Path, deps: Deps, *, execute: bool, cause: str = "Relaunch") -> Outcome:
    """Detiene las ejecuciones RUNNING de los pids de una corrida y verifica el tracker terminal."""
    ctx = monitor.load_run(run_dir)
    pids = [t.pid for t in ctx.tracked.values()]
    if not execute:
        running = _running_by_pid(deps.clients["stepfunctions"], ctx.state_machine_arn, pids)
        return Outcome(0, {"would_stop": sorted(running), "nota": "falta --execute"})
    problem = _guard_env(ctx.env, deps)
    if problem:
        return Outcome(1, {"abort": problem})
    sfn = deps.clients["stepfunctions"]
    running = _running_by_pid(sfn, ctx.state_machine_arn, pids)
    stopped, errors = [], {}
    for pid, arn in running.items():  # una falla no impide detener las demás
        try:
            sfn.stop_execution(executionArn=arn, error="Relaunch", cause=cause)
            stopped.append(pid)
        except Exception as exc:  # noqa: BLE001
            errors[pid] = f"{type(exc).__name__}: {exc}"
            log.error("no se pudo detener la ejecución de %s: %s", pid, errors[pid])
    ddb = deps.clients["dynamodb"]
    table = f"adr-{ctx.env}-medicalaudit-tracker-data"
    status: dict[str, str | None] = {pid: None for pid in pids}
    deadline = deps.clock() + STOP_VERIFY_TIMEOUT
    while True:
        for pid in [p for p in pids if status[p] not in TERMINAL_TRACKER]:
            item = ddb.get_item(TableName=table, Key={"process_id": {"S": pid}}, ProjectionExpression="#s",
                                ExpressionAttributeNames={"#s": "status"}).get("Item")
            status[pid] = item["status"]["S"] if item else None
        if all(v in TERMINAL_TRACKER for v in status.values()) or deps.clock() >= deadline:
            break
        deps.sleep(STOP_VERIFY_POLL)
    done = all(v in TERMINAL_TRACKER for v in status.values()) and not errors
    report = {"stopped": sorted(stopped), "tracker": status}
    if errors:
        report["stop_errors"] = errors
    return Outcome(0 if done else 3, report)

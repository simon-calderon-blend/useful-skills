"""Capa argparse de preflight/prepare/launch/monitor. Los .py de la raíz solo la llaman."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

import boto3

from . import api, auth, dispatch, envs, jumphost, launcher, monitor, runner, tunnel
from . import live as live_mod
from . import plan as plan_mod
from .envs import REGION


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")


def make_session(profile: str) -> Any:
    return boto3.Session(profile_name=profile, region_name=REGION)


def _env_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--env", required=True, choices=sorted(envs.ENVS))
    p.add_argument("--profile", help="perfil AWS (por defecto el del ambiente)")


def _request_value(text: str) -> str:
    if text in ("api", "local", "source") or re.fullmatch(r"source:[0-9a-fA-F-]{36}", text):
        return text
    raise argparse.ArgumentTypeError(f"{text!r}: usa api | local | source | source:<pid UUID>")


DECISIONS = ("structuring", "request", "invoice")


def _claim_args(p: argparse.ArgumentParser, required_decisions: bool = False) -> None:
    src = p.add_mutually_exclusive_group()
    src.add_argument("--source-dir", type=Path, help="carpeta con los claims")
    src.add_argument("--source-index", type=Path,
                     help="process_index.csv de una corrida previa (reutiliza claims completos del mismo ambiente)")
    p.add_argument("--claim", nargs="+", default=[],
                   help="carpetas de claim (explícitas); con --source-index filtra las filas del índice")
    req = required_decisions
    p.add_argument("--structuring", default=None, required=req,
                   help="none | local[:ruta] | workarea:<pid> | mai:<run-id>; con --source-index: workarea | none")
    p.add_argument("--request", type=_request_value, default=None, required=req,
                   help="api | local; con --source-index: source | source:<pid> (request original del "
                        "tracker, el más antiguo entregable)")
    p.add_argument("--invoice", choices=("local", "ser", "source", "lambda"), default=None, required=req,
                   help="local | ser | lambda (no sembrar: la Lambda consulta a SIA); "
                        "con --source-index: lambda | source")
    p.add_argument("--skip-delivery", action="store_true", help="no entregar a SIA (solo test)")
    p.add_argument("--name-template")
    p.add_argument("--name-regex")
    p.add_argument("--allow-open-dispatch", action="store_true")


def _inputs(a: argparse.Namespace, run_id: str = "preflight") -> runner.Inputs:
    index = getattr(a, "source_index", None)
    return runner.Inputs(env=a.env, profile=a.profile or envs.get_env(a.env).profile, source_dir=a.source_dir,
                         source_index=index,
                         claims=a.claim, name_template=a.name_template, name_regex=a.name_regex,
                         structuring=a.structuring or ("workarea" if index else "none"),
                         request=a.request or ("source" if index else "api"),
                         invoice=a.invoice or ("lambda" if index else "local"),
                         probe_api=getattr(a, "probe_api", False), allow_open_dispatch=a.allow_open_dispatch,
                         run_id=run_id, skip_delivery=a.skip_delivery)


def _probe_factory(spec: envs.EnvSpec, clients: runner.Clients):
    def factory(resolved: runner.Resolved, token: auth.Token):
        host = urlsplit(resolved.api_base_url).hostname
        bastion = resolved.jump_host.instance_id if resolved.jump_host else spec.bastion_instance_id

        def probe() -> int:
            with tunnel.open_tunnel(profile=spec.profile, bastion=bastion, host=host,
                                    region=REGION, ssm=clients["ssm"]) as t:
                return api.probe_proceso(t.connection_factory, resolved.api_base_url, token, str(uuid.uuid4()))
        return probe
    return factory


def _preflight(a: argparse.Namespace, run_id: str):
    spec = envs.get_env(a.env)
    inp = _inputs(a, run_id)
    try:
        runner.validate_inputs(inp)
    except ValueError as exc:
        print(f"argumentos incoherentes: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    clients = runner.Clients(make_session(inp.profile)) if not envs.is_sensitive_profile(inp.profile) \
        else runner.Clients()
    res = runner.run_preflight(
        inp, clients, environ=os.environ,
        config_path=getattr(a, "aws_config", None) or Path.home() / ".aws" / "config",
        sso_cache=Path.home() / ".aws" / "sso" / "cache", state_home=dispatch.state_home(),
        now=datetime.now().astimezone(), probe_factory=_probe_factory(spec, clients),
        agentcore=True)
    return inp, clients, res


def _claims_summary(inp: runner.Inputs, res: runner.PreflightResult) -> dict:
    """Lo que el usuario debe confirmar: ids parseados + patrón (modo carpeta), pid del request (índice)."""
    out: dict = {}
    if inp.source_index:
        out["request_source_pid"] = {c: sc.request_pid or sc.row.pid for c, sc in res.sources.items()}
        discarded = {c: sc.inspected for c, sc in res.sources.items() if sc.inspected}
        if discarded:
            out["request_pids_descartados"] = {c: [f"{p}: {why}" for p, why in d] for c, d in discarded.items()}
    else:
        out["name_pattern"] = {"template": inp.name_template or "<ignore>_<numero> (por defecto)",
                               "regex": inp.name_regex,
                               "efectivo": res.pattern.pattern if res.pattern is not None else None}
        out["claims_parsed"] = res.fields_by_claim
    return out


def _rerun_hint(spec: envs.EnvSpec, argv: Sequence[str]) -> str:
    cmd = envs.asm_exec_command(spec, ["uv", "run", "--project", str(plan_mod.SCRIPTS_DIR),
                                       str(plan_mod.SCRIPTS_DIR / "preflight.py"), *argv])
    return "token/aud/api checks skipped — rerun under: " + " ".join(cmd)


def main_preflight(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(description="Preflight de solo lectura para lanzar corridas IAE.")
    _env_arg(p)
    _claim_args(p)
    p.add_argument("--probe-api", action="store_true", help="abre el túnel SSM y sondea GET /proceso/<uuid>")
    p.add_argument("--aws-config", type=Path, help="ruta de ~/.aws/config (pruebas)")
    p.add_argument("--json", action="store_true", default=True, help="salida JSON (por defecto)")
    a = p.parse_args(argv)
    missing = [d for d in DECISIONS if getattr(a, d) is None]
    inp, _, res = _preflight(a, "preflight")
    summary: dict = {"decisions": {d: getattr(inp, d) for d in DECISIONS}, **_claims_summary(inp, res)}
    if missing:
        summary["missing_decisions"] = (f"no indicaste {', '.join('--' + m for m in missing)}: se usaron valores "
                                        "por defecto SOLO para evaluar; prepare.py los exige explícitos")
    if not os.environ.get(envs.SECRET_ENV_VAR):
        summary["token_checks"] = _rerun_hint(envs.get_env(a.env), argv)
    print(json.dumps({**json.loads(res.report.to_json()), "summary": summary}, ensure_ascii=False, indent=2))
    return 0 if res.report.ok else 1


def main_prepare(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Prepara plan.json (solo lectura en AWS).")
    _env_arg(p)
    _claim_args(p, required_decisions=True)
    p.add_argument("--run-id", default=datetime.now().strftime("skill-%Y%m%d-%H%M%S"))
    p.add_argument("--out-dir", type=Path, default=Path("runs"))
    p.add_argument("--skip-preflight", action="store_true")
    a = p.parse_args(argv)
    if a.skip_preflight:
        print("prepare.py no genera plan sin preflight (--skip-preflight rechazado)", file=sys.stderr)
        return 2
    if not (a.source_index or (a.source_dir and a.claim)):
        p.error("indica --source-index, o --source-dir con --claim (explícitos)")
    inp, clients, res = _preflight(a, a.run_id)
    if not res.report.ok:
        print(res.report.to_json())
        return 1
    closed = dispatch.closed_by_marker(clients["appconfig"], res.resolved.live.dispatch)
    print(json.dumps(_claims_summary(inp, res), ensure_ascii=False, indent=2))
    plan = plan_mod.build_plan(inp, res, run_id=a.run_id, out_dir=a.out_dir, now=datetime.now().astimezone(),
                               closed_by_marker=closed, skip_delivery=a.skip_delivery, s3=clients["s3"])
    path = plan_mod.write_plan(plan, a.out_dir)
    cmd = plan_mod.launch_command(a.env, path, plan["plan_id"])
    print(plan_mod.summarize(plan, cmd))
    print(f"plan: {path}")
    return 0


def _launch_deps(env: str, profile: str) -> launcher.Deps:
    spec = envs.get_env(env)
    clients = runner.Clients(make_session(profile))

    def open_tunnel(host: str):
        # Los bastiones estáticos pueden estar detenidos: se resuelve el jump host vivo (y el
        # sondeo /proceso/<uuid> == 404 lo valida antes de escribir nada).
        jump = jumphost.resolve(clients["ssm"], clients["ec2"], spec)
        return tunnel.open_tunnel(profile=profile, bastion=jump.instance_id, host=host,
                                  region=REGION, ssm=clients["ssm"])
    loader = live_mod.appconfig_loader(clients["appconfig"], env)
    return launcher.Deps(
        clients=clients, environ=os.environ, token_fn=auth.get_token, open_tunnel=open_tunnel,
        gather=lambda: live_mod.gather_live_paths(loader),
        reload_dispatch=lambda: loader("throttle-controller", "dispatch"),  # lectura fresca del flag
        api_url=lambda: live_mod.api_base_url(clients["apigateway"], env),
        state_home=dispatch.state_home(), now=lambda: datetime.now().astimezone())


def main_launch(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Lanza un plan. SOLO --execute escribe en AWS.")
    _env_arg(p)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--plan", type=Path)
    mode.add_argument("--recover", action="store_true", help="restaura el dispatch desde la miga de pausa")
    mode.add_argument("--open-dispatch", action="store_true", help="abre el dispatch (requiere --execute)")
    mode.add_argument("--stop-run", type=Path, metavar="RUN_DIR",
                      help="detiene las ejecuciones RUNNING de la corrida y verifica el tracker (requiere --execute)")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--plan-id")
    p.add_argument("--pause-settle-seconds", type=float, default=75)
    p.add_argument("--leave-dispatch-closed", action="store_true",
                   help="POST + siembra y deja el dispatch CERRADO (p. ej. para cambiar el qualifier)")
    p.add_argument("--stop-cause", default="Relaunch")
    a = p.parse_args(argv)
    profile = a.profile or envs.get_env(a.env).profile
    if envs.is_sensitive_profile(profile):
        print(f"el perfil {profile} es sensible", file=sys.stderr)
        return 1
    if a.open_dispatch:
        out = launcher.open_dispatch(a.env, _launch_deps(a.env, profile), execute=a.execute)
        print(json.dumps(out.report, indent=2, ensure_ascii=False, default=str))
        return out.exit_code
    if a.stop_run:
        out = launcher.stop_run(a.stop_run, _launch_deps(a.env, profile), execute=a.execute, cause=a.stop_cause)
        print(json.dumps(out.report, indent=2, ensure_ascii=False, default=str))
        return out.exit_code
    if a.recover:
        out = launcher.recover(a.env, _launch_deps(a.env, profile), execute=a.execute)
        print(json.dumps(out.report, indent=2, ensure_ascii=False, default=str))
        return out.exit_code
    if not a.plan:
        p.error("--plan es obligatorio (o --recover)")
    if not a.execute:
        try:
            print(launcher.describe(a.plan))
        except (OSError, plan_mod.PlanError, ValueError) as exc:
            print(f"plan inválido: {exc}", file=sys.stderr)
            return 1
        return 0
    if not a.plan_id:
        p.error("--execute requiere --plan-id")
    for sig in (signal.SIGTERM, signal.SIGHUP):  # para que el finally restaure el dispatch
        signal.signal(sig, lambda *_: sys.exit(143))
    out = launcher.execute_plan(a.plan, a.plan_id, _launch_deps(a.env, profile),
                                settle_seconds=a.pause_settle_seconds, leave_closed=a.leave_dispatch_closed)
    print(json.dumps(out.report, indent=2, ensure_ascii=False, default=str))
    return out.exit_code


def main_monitor(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Sigue las ejecuciones de una corrida y descarga resultados.")
    _env_arg(p)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--once", action="store_true")
    p.add_argument("--poll", type=float, default=30)
    p.add_argument("--download", action="store_true")
    p.add_argument("--close-dispatch-when-done", choices=("auto", "yes", "no"), default="auto")
    p.add_argument("--execute", action="store_true", help="necesario para cerrar el dispatch")
    a = p.parse_args(argv)
    spec = envs.get_env(a.env)
    profile = a.profile or spec.profile
    if envs.is_sensitive_profile(profile):
        print(f"el perfil {profile} es sensible", file=sys.stderr)
        return 1
    clients = runner.Clients(make_session(profile))
    loader = live_mod.appconfig_loader(clients["appconfig"], a.env)

    def gather():
        return live_mod.gather_live_paths(loader)
    status = monitor.run_monitor(a.run_dir, clients, once=a.once, poll=a.poll, download=a.download,
                                 close_mode=a.close_dispatch_when_done, execute=a.execute, gather=gather)
    print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
    return 1 if status.get("dispatch_error") or status.get("gave_up") else 0

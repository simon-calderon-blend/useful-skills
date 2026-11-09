"""Seguimiento de ejecuciones, descarga de resultados y cierre del dispatch.

Un solo poller (no un hilo por claim): cada ciclo lista las ejecuciones de la
state machine (más nuevas primero) y asocia por prefijo ``<pid>-``. Un error de
sondeo JAMÁS marca un claim como fallido: queda ``unknown_poll_error``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from botocore.exceptions import ClientError

from . import dispatch, envs
from . import live as live_mod
from .runindex import RunIndex
from .runner import Clients

log = logging.getLogger("iae_launch.monitor")
TERMINAL = {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}
MAX_RETRIES = 3
MAX_UNKNOWN_CYCLES = 10  # ciclos consecutivos con errores de sondeo antes de rendirse
WINDOW = timedelta(minutes=5)
ENGINE_OUTPUT = "staging/engine/"  # IAE storage.output (perfil intelligent-audit-engine/storage)


class MonitorError(RuntimeError):
    pass


@dataclass
class Tracked:
    folder: str
    pid: str
    status: str = "pending"
    execution_arn: str | None = None


@dataclass
class RunContext:
    env: str
    state_machine_arn: str
    bucket: str
    base_prefix: str
    started_at: datetime
    opened_dispatch: bool
    tracked: dict[str, Tracked] = field(default_factory=dict)


def load_run(run_dir: Path) -> RunContext:
    plan = json.loads((Path(run_dir) / "plan.json").read_text(encoding="utf-8"))
    report = json.loads((Path(run_dir) / "launch_report.json").read_text(encoding="utf-8"))
    tracked = {c["folder"]: Tracked(c["folder"], c["pid"]) for c in report["claims"]
               if c.get("pid") and c.get("status") in ("launched", "seed_failed")}
    return RunContext(plan["env"], plan["live"]["state_machine_arn"], plan["live"]["workarea_bucket"],
                      plan["live"]["base_prefix"], datetime.fromisoformat(report["started_at"]),
                      bool(report.get("opened_dispatch")), tracked)


def all_terminal(tracked: dict[str, Tracked]) -> bool:
    return all(t.status in TERMINAL for t in tracked.values())


def _call(fn: Callable[..., Any], sleep: Callable[[float], None], **kwargs):
    delay = 2
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn(**kwargs)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ThrottlingException" or attempt == MAX_RETRIES:
                raise
            sleep(delay)
            delay *= 2


def poll_once(sfn: Any, arn: str, tracked: dict[str, Tracked], run_start: datetime, *,
              sleep: Callable[[float], None] = time.sleep) -> None:
    by_prefix = {f"{t.pid}-": t for t in tracked.values()}
    found: dict[str, dict] = {}
    try:
        token = None
        while True:
            kwargs = {"stateMachineArn": arn, **({"nextToken": token} if token else {})}
            page = _call(sfn.list_executions, sleep, **kwargs)
            executions = page.get("executions", [])
            for e in executions:
                for prefix, t in by_prefix.items():
                    if e["name"].startswith(prefix) and t.folder not in found:
                        found[t.folder] = e  # más nueva primero
            token = page.get("nextToken")
            if not token or (executions and executions[-1]["startDate"] < run_start - WINDOW):
                break
        for folder, e in found.items():
            t = tracked[folder]
            t.execution_arn, t.status = e["executionArn"], e["status"]
            if t.status not in TERMINAL:
                t.status = _call(sfn.describe_execution, sleep, executionArn=e["executionArn"])["status"]
    except Exception as exc:  # noqa: BLE001 - nunca marcar failed por un error de sondeo
        log.warning("error de sondeo (%s: %s); los claims en curso quedan unknown_poll_error",
                    type(exc).__name__, exc)
        for t in tracked.values():
            if t.status not in TERMINAL:
                t.status = "unknown_poll_error"
        return
    for t in tracked.values():
        if t.folder not in found and t.status not in TERMINAL and t.execution_arn is None:
            t.status = "not_started"


def write_status(run_dir: Path, ctx: RunContext, now: datetime) -> dict:
    status = {"updated_at": now.isoformat(), "all_terminal": all_terminal(ctx.tracked),
              "claims": [{"folder": t.folder, "pid": t.pid, "status": t.status,
                          "execution_arn": t.execution_arn} for t in ctx.tracked.values()]}
    (Path(run_dir) / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def download_claim(s3: Any, ctx: RunContext, t: Tracked, run_dir: Path) -> int:
    prefix = f"{ctx.base_prefix}/{t.pid}/{ENGINE_OUTPUT}"
    dest_root = (Path(run_dir) / t.folder).resolve()
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=ctx.bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            dest = (dest_root / key[len(prefix):]).resolve()
            if dest_root not in dest.parents:
                raise MonitorError(f"la clave {key!r} resolvería fuera de {dest_root}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            body = s3.get_object(Bucket=ctx.bucket, Key=key)["Body"]
            with dest.open("wb") as fh:
                for chunk in body.iter_chunks():
                    fh.write(chunk)
            count += 1
    RunIndex(Path(run_dir) / "process_index.csv").record(t.folder, descargado=True)
    return count


def should_close(mode: str, opened_dispatch: bool, env: str) -> bool:
    if mode == "yes":
        return True
    if mode == "no":
        return False
    return envs.get_env(env).leave_dispatch_closed_after and opened_dispatch


def close_dispatch(env: str, clients: Clients, gather: Callable[[], live_mod.LivePaths], *,
                   execute: bool, sleep: Callable[[float], None] = time.sleep) -> str:
    if not execute:
        return "no se cierra el dispatch sin --execute"
    spec = envs.get_env(env)
    if envs.is_sensitive_profile(spec.profile):
        raise MonitorError(f"el perfil {spec.profile} es sensible")
    account = clients["sts"].get_caller_identity()["Account"]
    if account != spec.account_id:
        raise MonitorError(f"cuenta {account} != {spec.account_id}")
    live = gather()
    if not dispatch.read_enabled(live.dispatch):
        return "ya estaba cerrado"
    strategy = dispatch.resolve_strategy_id(clients["appconfig"])
    if strategy is None:
        raise MonitorError("no hay estrategia de AppConfig con duración 0 y bake 0")
    dispatch.set_enabled_fresh(clients["appconfig"], lambda: gather().dispatch, strategy, False,
                               description=dispatch.CLOSE_MARKER, sleep=sleep)
    return "dispatch cerrado"


def run_monitor(run_dir: Path, clients: Clients, *, once: bool, poll: float, download: bool,
                close_mode: str, execute: bool, gather: Callable[[], live_mod.LivePaths] | None,
                sleep: Callable[[float], None] = time.sleep,
                now: Callable[[], datetime] = lambda: datetime.now().astimezone()) -> dict:
    run_dir = Path(run_dir)
    ctx = load_run(run_dir)
    bad_cycles = 0
    while True:
        poll_once(clients["stepfunctions"], ctx.state_machine_arn, ctx.tracked, ctx.started_at, sleep=sleep)
        status = write_status(run_dir, ctx, now())
        bad_cycles = bad_cycles + 1 if any(t.status == "unknown_poll_error" for t in ctx.tracked.values()) else 0
        if status["all_terminal"] or once:
            break
        if bad_cycles >= MAX_UNKNOWN_CYCLES:
            status["gave_up"] = (f"{bad_cycles} ciclos seguidos con errores de sondeo: se deja de consultar "
                                 "(los claims NO se marcan fallidos)")
            log.error("%s", status["gave_up"])
            return status
        sleep(poll)
    status["downloaded"], status["dispatch"] = [], None
    if status["all_terminal"]:
        if download:
            for t in ctx.tracked.values():
                download_claim(clients["s3"], ctx, t, run_dir)
                status["downloaded"].append(t.folder)
        if should_close(close_mode, ctx.opened_dispatch, ctx.env):
            try:  # el estado ya está en status.json; un fallo al cerrar no debe ocultarlo
                status["dispatch"] = close_dispatch(ctx.env, clients, gather, execute=execute, sleep=sleep)
            except Exception as exc:  # noqa: BLE001
                status["dispatch"] = f"ERROR al cerrar el dispatch: {type(exc).__name__}: {exc}"
                status["dispatch_error"] = True
                log.error("%s", status["dispatch"])
    return status

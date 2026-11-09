"""Compuerta de dispatch (throttle-controller, AppConfig feature flag).

Diferencia con el runner (pipeline_runner/dispatcher.py:read_dispatch_document):
el documento base es el DESPLEGADO (último deployment COMPLETE), no la última
versión hospedada, que puede ser una versión creada y nunca desplegada.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, NamedTuple

from botocore.exceptions import ClientError

from .live import Deployed, read_dispatch_enabled

log = logging.getLogger("iae_launch.dispatch")

# Misma cadena que el runner: ambas herramientas coinciden en "quién cerró".
CLOSE_MARKER = "pipeline-runner: dispatch closed after batch"
PREFERRED_STRATEGIES = ("adr-appconfig-seed-nobake", "instant-allatonce-0bake", "instant-0bake")
OUR_TOOL = "launching-iae-pipeline-runs"
RUNNER_TOOL = "pipeline-runner"
DEPLOY_TIMEOUT = 120.0
POLL_INTERVAL = 2.0
RETRY_ATTEMPTS = 4
RETRY_BACKOFF = 5.0
IDLE_TIMEOUT = 180.0
RETRIABLE_CODES = ("ConflictException", "ThrottlingException")
# Solo estas claves las mantiene AppConfig (FeatureFlags); cualquier otra "_x" es contenido legítimo.
METADATA_KEYS = ("_createdAt", "_updatedAt")


class Deployment(NamedTuple):
    number: int
    completed_at: datetime | None


class DispatchError(RuntimeError):
    pass


def read_enabled(deployed: Deployed) -> bool:
    return read_dispatch_enabled(deployed)


def _strip_underscore(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_underscore(v) for k, v in node.items() if k not in METADATA_KEYS}
    if isinstance(node, list):
        return [_strip_underscore(v) for v in node]
    return node


def build_content(deployed: Deployed, enabled: bool) -> bytes:
    doc = _strip_underscore(deployed.content)
    doc.setdefault("values", {}).setdefault("dispatch", {})["enabled"] = enabled
    return json.dumps(doc).encode()


def set_enabled(appconfig: Any, deployed: Deployed, strategy_id: str, enabled: bool,
                description: str | None = None, *,
                sleep: Callable[[float], None] = time.sleep,
                clock: Callable[[], float] = time.monotonic) -> Deployment:
    ver = appconfig.create_hosted_configuration_version(
        ApplicationId=deployed.app_id, ConfigurationProfileId=deployed.profile_id,
        Content=build_content(deployed, enabled), ContentType="application/json")["VersionNumber"]
    kwargs = dict(ApplicationId=deployed.app_id, EnvironmentId=deployed.env_id,
                  DeploymentStrategyId=strategy_id, ConfigurationProfileId=deployed.profile_id,
                  ConfigurationVersion=str(ver))
    if description:
        kwargs["Description"] = description
    number = appconfig.start_deployment(**kwargs)["DeploymentNumber"]
    log.info("dispatch enabled=%s: deployment %s (config v%s)", enabled, number, ver)
    deadline = clock() + DEPLOY_TIMEOUT
    while True:
        resp = appconfig.get_deployment(ApplicationId=deployed.app_id, EnvironmentId=deployed.env_id,
                                        DeploymentNumber=number)
        state = resp["State"]
        if state == "COMPLETE":
            return Deployment(number, resp.get("CompletedAt"))
        if state in ("ROLLED_BACK", "REVERTED"):
            raise DispatchError(f"el deployment {number} terminó en {state}")
        if clock() >= deadline:
            raise DispatchError(f"el deployment {number} no llegó a COMPLETE en {DEPLOY_TIMEOUT:g} s")
        sleep(POLL_INTERVAL)


def _wait_idle(reload: Callable[[], Deployed], sleep: Callable[[float], None],
               clock: Callable[[], float]) -> Deployed:
    """Relee el dispatch DESPLEGADO y espera a que no haya un deployment en curso del perfil."""
    deadline = clock() + IDLE_TIMEOUT
    current = reload()
    while current.in_progress:
        if clock() >= deadline:
            raise DispatchError(f"deployments en curso {current.in_progress} no terminaron en {IDLE_TIMEOUT:g} s")
        sleep(POLL_INTERVAL)
        current = reload()
    return current


def set_enabled_fresh(appconfig: Any, reload: Callable[[], Deployed], strategy_id: str, enabled: bool,
                      description: str | None = None, *, sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.monotonic) -> Deployment:
    """``set_enabled`` con documento base FRESCO, espera de deployments en curso y reintentos.

    El documento del inicio de la corrida puede estar desactualizado (alguien editó el flag
    mientras sembrábamos): restaurar con él pisaría ese cambio. Un ConflictException (otro
    deployment en curso) o Throttling se reintenta con backoff exponencial.
    """
    delay = RETRY_BACKOFF
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return set_enabled(appconfig, _wait_idle(reload, sleep, clock), strategy_id, enabled,
                               description, sleep=sleep, clock=clock)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in RETRIABLE_CODES or attempt == RETRY_ATTEMPTS:
                raise
            log.warning("set_enabled(%s) intento %s/%s: %s; reintento en %.0f s", enabled, attempt,
                        RETRY_ATTEMPTS, code, delay)
            sleep(delay)
            delay *= 2
    raise AssertionError("inalcanzable")


def _is_instant(s: dict) -> bool:
    return s.get("DeploymentDurationInMinutes") == 0 and s.get("FinalBakeTimeInMinutes") == 0


def resolve_strategy(appconfig: Any) -> tuple[str, str] | None:
    """(id, nombre) de la estrategia 0 duración / 0 bake. El comportamiento decide; el nombre solo prioriza.

    ``AppConfig.AllAtOnce`` se excluye: aunque deploya al 100%, hornea 10 minutos.
    """
    found: dict[str, tuple[str, str]] = {}
    fallback: tuple[str, str] | None = None
    for page in appconfig.get_paginator("list_deployment_strategies").paginate():
        for s in page.get("Items", []):
            if not _is_instant(s):
                continue
            if s.get("Name") in PREFERRED_STRATEGIES:
                found.setdefault(s["Name"], (s["Id"], s["Name"]))
            elif fallback is None and not str(s.get("Id", "")).startswith("AppConfig."):
                fallback = (s["Id"], s["Name"])
    for name in PREFERRED_STRATEGIES:
        if name in found:
            return found[name]
    return fallback


def resolve_strategy_id(appconfig: Any) -> str | None:
    found = resolve_strategy(appconfig)
    return found[0] if found else None


def closed_by_marker(appconfig: Any, deployed: Deployed) -> bool:
    """¿El último deployment del perfil dispatch lo dejó cerrado un lote previo?"""
    deps: list[dict] = []
    for page in appconfig.get_paginator("list_deployments").paginate(
            ApplicationId=deployed.app_id, EnvironmentId=deployed.env_id):
        deps += page.get("Items", [])
    mine = [d for d in deps if d.get("ConfigurationName") == "dispatch" and d.get("State") == "COMPLETE"]
    if not mine:
        return False
    newest = max(mine, key=lambda d: d["DeploymentNumber"])
    # list_deployments devuelve resúmenes SIN Description (el closed_by_runner del
    # runner, dispatcher.py, leía ese campo del resumen y por eso siempre daba False).
    full = appconfig.get_deployment(ApplicationId=deployed.app_id, EnvironmentId=deployed.env_id,
                                    DeploymentNumber=newest["DeploymentNumber"])
    return CLOSE_MARKER in (full.get("Description") or "")


def latest_dispatch_time(appconfig: Any, deployed: Deployed) -> datetime | None:
    """Fin (o inicio) del último deployment del perfil dispatch; None si no hay."""
    deps: list[dict] = []
    for page in appconfig.get_paginator("list_deployments").paginate(
            ApplicationId=deployed.app_id, EnvironmentId=deployed.env_id):
        deps += page.get("Items", [])
    mine = [d for d in deps if d.get("ConfigurationName") == "dispatch" and d.get("State") == "COMPLETE"]
    if not mine:
        return None
    newest = max(mine, key=lambda d: d["DeploymentNumber"])
    full = appconfig.get_deployment(ApplicationId=deployed.app_id, EnvironmentId=deployed.env_id,
                                    DeploymentNumber=newest["DeploymentNumber"])
    return full.get("CompletedAt") or full.get("StartedAt")


def compute_restore_to(was_enabled: bool, closed_by_marker: bool, allow_open: bool) -> bool:
    """A qué valor volver. Cerrado por un lote previo (o abierto a propósito) => abierto."""
    return was_enabled or closed_by_marker or allow_open


# ---- breadcrumb --------------------------------------------------------------
def state_home() -> Path:
    env = os.environ.get("XDG_STATE_HOME")
    return Path(env) if env else Path.home() / ".local" / "state"


def _crumb(env: str, home: Path, tool: str = OUR_TOOL) -> Path:
    return Path(home) / tool / f"paused-{env}.json"


class BreadcrumbExists(RuntimeError):
    pass


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_breadcrumb(env: str, home: Path, *, app: str, was_enabled: bool, restore_to: bool,
                     run_id: str, pid: int) -> Path:
    """Atómica: escribe a un temporal y ``os.link`` (falla si la miga ya existe)."""
    path = _crumb(env, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".paused-")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump({"env": env, "app": app, "was_enabled": was_enabled, "restore_to": restore_to,
                       "started_at": datetime.now(timezone.utc).isoformat(), "pid": pid,
                       "run_id": run_id}, fh)
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise BreadcrumbExists(f"ya existe la miga de pausa {path}") from None
    finally:
        os.unlink(tmp)
    return path


def read_breadcrumb(env: str, home: Path) -> dict | None:
    try:
        return json.loads(_crumb(env, home).read_text())
    except FileNotFoundError:
        return None


def delete_breadcrumb(env: str, home: Path) -> None:
    _crumb(env, home).unlink(missing_ok=True)


def existing_breadcrumbs(env: str, home: Path) -> list[Path]:
    return [p for p in (_crumb(env, home, RUNNER_TOOL), _crumb(env, home)) if p.exists()]

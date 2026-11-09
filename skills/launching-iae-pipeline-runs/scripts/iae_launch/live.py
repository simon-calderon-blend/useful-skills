"""Resolución en vivo (solo lectura) de la configuración DESPLEGADA.

Reglas:
* Nombres exactos: dev tiene copias de infra ``e1-adr-dev-medicalaudit-*``.
* Se lee la última versión de un deployment ``COMPLETE`` por perfil, NUNCA la
  "última versión hospedada": la última puede ser una versión creada y no
  desplegada (terraform crea hosted versions pero no las despliega).
* Toda lista se pagina.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .envs import REGION

IN_PROGRESS_STATES = {"DEPLOYING", "BAKING", "VALIDATING", "ROLLING_BACK"}
# Fuente: CDK lambda-init-handler/index.py:105 (env var WORKAREA_BASE_PREFIX) y
# docs/adr/005-storage-convention.md ("WORKAREA_BASE_PREFIX (= audit-processes)").
# No es un perfil de AppConfig: lo inyecta CDK como variable de entorno.
WORKAREA_BASE_PREFIX = "audit-processes"
DEFAULT_MIN_RECORDS_PER_JOB = 100  # doc-extraction/<env>/batch.json


class LiveConfigError(RuntimeError):
    """La configuración viva no se puede resolver o no es consistente."""


@dataclass(frozen=True)
class Deployed:
    app_id: str
    env_id: str
    profile_id: str
    version: int
    deployment_number: int
    content: dict
    in_progress: tuple[int, ...] = ()


def _exact(items: list[dict], name: str, kind: str, where: str) -> dict:
    for item in items:
        if item.get("Name") == name:
            return item
    raise LiveConfigError(f"{kind} {name!r} no existe en {where} (coincidencia exacta)")


def _paginate(client: Any, op: str, key: str, **kwargs) -> list[dict]:
    out: list[dict] = []
    for page in client.get_paginator(op).paginate(**kwargs):
        out.extend(page.get(key, []))
    return out


def deployed_config(appconfig: Any, app_name: str, env_name: str, profile_name: str) -> Deployed:
    app = _exact(_paginate(appconfig, "list_applications", "Items"), app_name, "aplicación",
                 "AppConfig")
    app_id = app["Id"]
    env = _exact(_paginate(appconfig, "list_environments", "Items", ApplicationId=app_id),
                 env_name, "ambiente", app_name)
    prof = _exact(_paginate(appconfig, "list_configuration_profiles", "Items",
                            ApplicationId=app_id), profile_name, "perfil", app_name)
    deployments = [d for d in _paginate(appconfig, "list_deployments", "Items",
                                        ApplicationId=app_id, EnvironmentId=env["Id"])
                   if d.get("ConfigurationName") == profile_name]
    complete = [d for d in deployments if d.get("State") == "COMPLETE"]
    if not complete:
        raise LiveConfigError(
            f"{app_name}/{profile_name} no tiene ningún deployment COMPLETE en {env_name}")
    latest = max(complete, key=lambda d: d["DeploymentNumber"])
    version = int(latest["ConfigurationVersion"])
    body = appconfig.get_hosted_configuration_version(
        ApplicationId=app_id, ConfigurationProfileId=prof["Id"], VersionNumber=version)
    in_progress = tuple(sorted(d["DeploymentNumber"] for d in deployments
                               if d.get("State") in IN_PROGRESS_STATES))
    return Deployed(app_id, env["Id"], prof["Id"], version, latest["DeploymentNumber"],
                    json.loads(body["Content"].read()), in_progress)


@dataclass(frozen=True)
class LivePaths:
    base_prefix: str
    intake: str
    structured: str
    consolidated: str
    invoice_output: str
    ingest_mappings: dict
    qualifier: str
    rules: list
    min_records_per_job: int
    dispatch: Deployed
    versions: dict[str, int] = field(default_factory=dict)
    in_progress: dict[str, tuple[int, ...]] = field(default_factory=dict)

    def to_plan_dict(self) -> dict:
        return {"base_prefix": self.base_prefix, "intake": self.intake,
                "structured": self.structured, "consolidated": self.consolidated,
                "invoice_output": self.invoice_output, "qualifier": self.qualifier,
                "min_records_per_job": self.min_records_per_job,
                "dispatch_enabled": read_dispatch_enabled(self.dispatch)}


def read_dispatch_enabled(dispatch: Deployed) -> bool:
    return bool(dispatch.content.get("values", {}).get("dispatch", {}).get("enabled", False))


def _dig(doc: dict, path: str, where: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise LiveConfigError(f"{where}: falta la clave {path!r} en la config desplegada")
        cur = cur[part]
    return cur


# (alias, app suffix, perfil)
_PROFILES = {
    "api/storage": ("api", "storage"),
    "doc-extraction/storage": ("doc-extraction", "storage"),
    "doc-extraction/batch": ("doc-extraction", "batch"),
    "fetch-claim-invoice-details/storage": ("fetch-claim-invoice-details", "storage"),
    "intelligent-audit-engine/engine_ingest_mappings":
        ("intelligent-audit-engine", "engine_ingest_mappings"),
    "intelligent-audit-engine/runtime": ("intelligent-audit-engine", "runtime"),
    "prerequisite-engine/minimum-requirements": ("prerequisite-engine", "minimum-requirements"),
    "throttle-controller/dispatch": ("throttle-controller", "dispatch"),
}


def appconfig_loader(appconfig: Any, env_name: str) -> Callable[[str, str], Deployed]:
    def load(app_suffix: str, profile: str) -> Deployed:
        return deployed_config(appconfig, f"adr-{env_name}-medicalaudit-{app_suffix}-appconfig",
                               env_name, profile)
    return load


def gather_live_paths(load: Callable[[str, str], Deployed]) -> LivePaths:
    loaded = {alias: load(*key) for alias, key in _PROFILES.items()}
    c = {alias: d.content for alias, d in loaded.items()}
    mappings = _dig(c["intelligent-audit-engine/engine_ingest_mappings"], "mappings",
                    "engine_ingest_mappings")
    batch = c["doc-extraction/batch"]
    lp = LivePaths(
        base_prefix=WORKAREA_BASE_PREFIX,
        intake=_dig(c["api/storage"], "output.intake", "api/storage"),
        structured=_dig(c["doc-extraction/storage"], "output.structured", "doc-extraction/storage"),
        consolidated=_dig(c["doc-extraction/storage"], "work.consolidated", "doc-extraction/storage"),
        invoice_output=_dig(c["fetch-claim-invoice-details/storage"], "output",
                            "fetch-claim-invoice-details/storage"),
        ingest_mappings=mappings,
        qualifier=_dig(c["intelligent-audit-engine/runtime"], "qualifier", "runtime"),
        rules=_dig(c["prerequisite-engine/minimum-requirements"], "rules", "minimum-requirements"),
        min_records_per_job=int(batch.get("min_records_per_job", DEFAULT_MIN_RECORDS_PER_JOB)),
        dispatch=loaded["throttle-controller/dispatch"],
        versions={alias: d.version for alias, d in loaded.items()},
        in_progress={alias: d.in_progress for alias, d in loaded.items() if d.in_progress},
    )
    for name in ("intake", "structured", "consolidated", "invoice_output"):
        _check_prefix(name, getattr(lp, name))
    return lp


def _check_prefix(name: str, value: Any) -> None:
    """Los prefijos del perfil se concatenan tal cual (D-SLASH): terminan en '/' y son relativos."""
    if not isinstance(value, str) or not value.endswith("/") or value.startswith("/") or ".." in value.split("/"):
        raise LiveConfigError(f"prefijo {name}={value!r} inválido: debe terminar en '/', ser relativo y sin '..'")


def ingest_mismatches(lp: LivePaths) -> list[str]:
    """Prefijos que sembramos pero que el motor no lee (staging/structured, etc.)."""
    return [p for p in (lp.intake, lp.structured) if p not in lp.ingest_mappings]


def version_drift(planned: dict[str, int], now: dict[str, int]) -> dict[str, tuple[Any, Any]]:
    keys = set(planned) | set(now)
    return {k: (planned.get(k), now.get(k)) for k in sorted(keys) if planned.get(k) != now.get(k)}


def api_base_url(apigateway: Any, env_name: str) -> str:
    name = f"adr-{env_name}-medicalaudit-api-gateway"
    apis = [a for a in _paginate(apigateway, "get_rest_apis", "items") if a.get("name") == name]
    if not apis:
        raise LiveConfigError(f"API Gateway {name!r} no existe (coincidencia exacta)")
    api_id = apis[0]["id"]
    stages = apigateway.get_stages(restApiId=api_id).get("item", [])
    if not any(s.get("stageName") == "v1" for s in stages):
        raise LiveConfigError(f"la API {name} no tiene el stage v1")
    return f"https://{api_id}.execute-api.{REGION}.amazonaws.com/v1"


def state_machine_arn(sfn: Any, env_name: str) -> str:
    name = f"adr-{env_name}-medicalaudit-pipeline"
    for sm in _paginate(sfn, "list_state_machines", "stateMachines"):
        if sm["name"] == name:
            return sm["stateMachineArn"]
    raise LiveConfigError(f"state machine {name!r} no existe (coincidencia exacta)")


def workarea_bucket(s3: Any, env_name: str) -> str:
    bucket = f"adr-{env_name}-medicalaudit-workarea"
    s3.head_bucket(Bucket=bucket)
    return bucket


def conveyor_queue_url(sqs: Any, env_name: str) -> str:
    return sqs.get_queue_url(
        QueueName=f"adr-{env_name}-medicalaudit-doc-extraction-chunks-conveyor")["QueueUrl"]

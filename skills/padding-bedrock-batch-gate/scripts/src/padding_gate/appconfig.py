"""Read the doc-extraction settings batch-trigger actually runs with.

"Actually runs with" means the last COMPLETE deployment of each profile, not the
newest hosted version: terraform/CDK create hosted versions without deploying
them, so the newest version can be a value no Lambda has ever seen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# extraction carries the doc_code lists; batch and storage are what batch-trigger
# reads on every tick (lambda-batch-trigger/index.py handler).
_PROFILES = ("batch", "storage", "extraction")


class AppConfigError(Exception):
    """The live configuration could not be resolved unambiguously."""


@dataclass(frozen=True)
class LiveConfig:
    min_records: int
    run_configs_prefix: str
    pointers_prefix: str
    # Codes that reach Bedrock Batch: extractable minus always-on-demand.
    batch_doc_codes: frozenset[str]
    sources: dict[str, str] = field(default_factory=dict)


def _all_items(client: Any, operation: str, **params: Any) -> list[dict]:
    paginator = client.get_paginator(operation)
    return [item for page in paginator.paginate(**params) for item in page.get("Items", [])]


def _one_by_name(items: list[dict], name: str, what: str) -> dict:
    matches = [item for item in items if item["Name"] == name]
    if len(matches) != 1:
        found = sorted(item["Name"] for item in items)
        raise AppConfigError(f"no AppConfig {what} named {name!r} (found {len(matches)}; available: {found})")
    return matches[0]


def _storage_prefix(storage: dict, key: str) -> str:
    """Mirror of batch-trigger's _resolve_storage_prefix(..., 'work', key, legacy=key)."""
    value = storage.get("work", {}).get(key) or storage.get(key)
    if not value:
        raise AppConfigError(f"storage profile has no work.{key}")
    return value


def load_live_config(appconfig: Any, app_name: str, env_name: str) -> LiveConfig:
    app = _one_by_name(_all_items(appconfig, "list_applications"), app_name, "application")
    app_id = app["Id"]
    env = _one_by_name(
        _all_items(appconfig, "list_environments", ApplicationId=app_id), env_name, "environment"
    )
    profile_ids = {
        p["Name"]: p["Id"]
        for p in _all_items(appconfig, "list_configuration_profiles", ApplicationId=app_id)
    }
    deployments = sorted(
        _all_items(appconfig, "list_deployments", ApplicationId=app_id, EnvironmentId=env["Id"]),
        key=lambda d: d["DeploymentNumber"],
        reverse=True,
    )

    contents: dict[str, dict] = {}
    sources: dict[str, str] = {}
    for name in _PROFILES:
        deployed = next(
            (d for d in deployments if d["ConfigurationName"] == name and d["State"] == "COMPLETE"),
            None,
        )
        if deployed is None or name not in profile_ids:
            raise AppConfigError(f"profile {name!r} has no COMPLETE deployment in {env_name!r}")
        version = int(deployed["ConfigurationVersion"])
        raw = appconfig.get_hosted_configuration_version(
            ApplicationId=app_id, ConfigurationProfileId=profile_ids[name], VersionNumber=version
        )["Content"]
        try:
            contents[name] = json.loads(raw.read() if hasattr(raw, "read") else raw)
        except ValueError as error:
            raise AppConfigError(f"profile {name!r} is not valid JSON: {error}") from error
        sources[name] = f"deployment #{deployed['DeploymentNumber']} (version {version})"

    extraction = contents["extraction"]
    batch_codes = set(extraction.get("extractable_doc_codes", [])) - set(
        extraction.get("always_ondemand_doc_codes", [])
    )
    try:
        min_records = int(contents["batch"]["min_records_per_job"])
    except (KeyError, TypeError, ValueError) as error:
        raise AppConfigError(f"batch profile has no usable min_records_per_job: {error!r}") from error
    return LiveConfig(
        min_records=min_records,
        run_configs_prefix=_storage_prefix(contents["storage"], "run_configs"),
        pointers_prefix=_storage_prefix(contents["storage"], "run_config_pointers"),
        batch_doc_codes=frozenset(batch_codes),
        sources=sources,
    )

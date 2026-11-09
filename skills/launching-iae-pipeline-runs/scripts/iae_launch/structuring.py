"""Estructuración (carpeta 200_): normalización, marcador consolidated.json y fuentes.

Hallazgos verificados en el repo CDK (adr-medicalAudit-pipelineCDK @4a0090b9) sobre
``consolidated.json``:
* lambda-extraction-dispatcher/index.py:193-196 solo hace ``head_object`` de
  ``<work.consolidated>consolidated.json`` (guarda "ya extraído", solo dev/test).
* lambda-finalize-claim/index.py:212-250 lee SOLO ``run_id`` (idempotencia); el real
  escribe ``{process_id, run_id, documents}`` (index.py:448). Nadie en CDK parsea
  ``documents``; nuestro marcador mantiene ``run_id`` y ``documents`` para no romper
  nada. Es transitorio (tag lifecycle=transient, 7 días).
* El API ya soporta ``executionMode: skip_extraction`` + ``sourcePrefix`` (dev/test,
  lambda-init-handler/index.py:442+): alternativa server-side a sembrar a mano.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .live import LivePaths
from .seed import SeedItem

STRUCTURED_DIR = "200_soportes_estructurados"
GENERATED_BY = "launching-iae-pipeline-runs"
_CODE_PREFIX = re.compile(r"^\d{3}_")
MAI_BUCKETS = {"dev": "adr-medical-audit-executions-local-mai",
               "test": "adr-test-medical-audit-executions-local-mai"}


class StructuringError(RuntimeError):
    pass


@dataclass(frozen=True)
class Decision:
    kind: str  # none | local | workarea | mai
    ref: str = ""

    def label(self) -> str:
        return self.kind if self.kind == "none" else f"{self.kind}:{self.ref}"


@dataclass(frozen=True)
class StructuringPlan:
    items: list[SeedItem]
    artifacts: int
    source: str


_MAI_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _is_uuid(text: str) -> bool:
    try:
        uuid.UUID(text)
    except ValueError:
        return False
    return True


def parse_decision(text: str, claim_dir: Path) -> Decision:
    kind, _, ref = text.partition(":")
    if kind == "none" and not ref:
        return Decision("none")
    if kind == "local":
        return Decision("local", ref or str(Path(claim_dir) / STRUCTURED_DIR))
    if kind == "workarea" and _is_uuid(ref):
        return Decision(kind, ref)
    if kind == "mai" and _MAI_REF.fullmatch(ref):
        return Decision(kind, ref)
    raise StructuringError(
        f"--structuring {text!r} inválido (none | local[:ruta] | workarea:<pid UUID> | mai:<run-id [A-Za-z0-9._-]>)")


def normalize_artifact_name(name: str) -> str:
    """El motor agrega ``NNN_`` al ingerir (rename_with_code_prefix: true)."""
    return _CODE_PREFIX.sub("", name, count=1)


def normalize_artifacts(names: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in sorted(names):
        if name.startswith(".") or not name.lower().endswith(".json"):
            continue
        norm = normalize_artifact_name(name)
        if norm in out:
            raise StructuringError(
                f"colisión al normalizar: {out[norm]!r} y {name!r} -> {norm!r}")
        out[norm] = name
    return out


def build_consolidated_marker(artifacts: list[str], source: str, run_id: str) -> dict:
    by_code: dict[str, list[str]] = {}
    for name in sorted(artifacts):
        by_code.setdefault(name.split("_", 1)[0], []).append(name)
    return {"run_id": run_id, "generated_by": GENERATED_BY, "source": source,
            "documents": {c: {"artifact": v[0], "artifacts": v} for c, v in by_code.items()}}


def _write_marker(derived_dir: Path, folder: str, marker: dict, consolidated: str) -> SeedItem:
    path = Path(derived_dir) / folder / "consolidated.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    return SeedItem("put", str(path), f"{consolidated}consolidated.json", "application/json")


def _list_keys(s3: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    return keys


def _exists(s3: Any, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def plan_structuring(decision: Decision, folder: str, fields: dict, live: LivePaths,
                     run_id: str, derived_dir: Path, *, s3: Any = None, env: str = "dev",
                     bucket: str = "") -> StructuringPlan:
    if decision.kind == "none":
        return StructuringPlan([], 0, "none")
    source = decision.label()
    marker_run = f"{GENERATED_BY}-{run_id}"
    items: list[SeedItem] = []
    existing_consolidated: str | None = None

    if decision.kind == "local":
        src = Path(decision.ref)
        if not src.is_dir():
            raise StructuringError(f"la carpeta {src} no existe")
        names = normalize_artifacts(os.listdir(src))
        items = [SeedItem("put", str(src / orig), f"{live.structured}{norm}", "application/json")
                 for norm, orig in names.items()]
    else:
        if decision.kind == "mai":
            src_bucket = MAI_BUCKETS[env]
            prefix = f"runs/{decision.ref}/{folder}/{STRUCTURED_DIR}/"
        else:
            src_bucket = bucket
            base = f"{live.base_prefix}/{decision.ref}/"
            _assert_same_claim(s3, bucket, f"{base}{live.intake}request.json", fields, decision.ref)
            prefix = f"{base}{live.structured}"
            consolidated_key = f"{base}{live.consolidated}consolidated.json"
            if _exists(s3, bucket, consolidated_key):
                existing_consolidated = f"s3://{bucket}/{consolidated_key}"
        keys = [k for k in _list_keys(s3, src_bucket, prefix)
                if not k.endswith("/") and k.startswith(prefix)]
        names = normalize_artifacts([k[len(prefix):] for k in keys if "/" not in k[len(prefix):]])
        items = [SeedItem("copy", f"s3://{src_bucket}/{prefix}{orig}", f"{live.structured}{norm}",
                          "application/json") for norm, orig in names.items()]

    if not names:
        raise StructuringError(f"{source}: la fuente no tiene ningún artefacto .json")
    if existing_consolidated:
        items.append(SeedItem("copy", existing_consolidated,
                              f"{live.consolidated}consolidated.json", "application/json"))
    else:
        marker = build_consolidated_marker(list(names), source, marker_run)
        items.append(_write_marker(derived_dir, folder, marker, live.consolidated))
    return StructuringPlan(items, len(names), source)


def _assert_same_claim(s3: Any, bucket: str, key: str, fields: dict, pid: str) -> None:
    """Falla cerrado: sin request.json no se puede probar que el pid es del mismo radicado."""
    try:
        body = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        raise StructuringError(
            f"workarea:{pid} no tiene request.json; no se puede verificar el radicado") from None
    if body.get("idReclamacion") != fields.get("idReclamacion"):
        raise StructuringError(
            f"workarea:{pid} es del radicado {body.get('idReclamacion')}, no del claim "
            f"{fields.get('idReclamacion')}")

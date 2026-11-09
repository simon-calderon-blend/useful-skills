"""Reutilización de claims completos desde un ``process_index.csv`` de una corrida previa.

No hay carpetas locales: todo sale del pid previo en el MISMO workarea del ambiente
(``raw/*``, artefactos estructurados y ``consolidated.json``), vía copia server-side.
"""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from .live import LivePaths

HEADER = ["radicado", "pid", "descargado", "s3uri"]
INVOICE_NAME = "claim_invoice_details.json"
REQUEST_NAME = "request.json"


class SourceIndexError(ValueError):
    pass


@dataclass(frozen=True)
class IndexRow:
    radicado: str
    pid: str
    bucket: str
    prefix: str  # <base>/<pid>/


def read_index(path: Path, bucket: str, base_prefix: str, only: list[str] | None = None) -> list[IndexRow]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != HEADER:
            raise SourceIndexError(f"cabecera del índice {reader.fieldnames} != {HEADER}")
        raw_rows = list(reader)
    if not raw_rows:
        raise SourceIndexError("el índice está vacío")
    rows: list[IndexRow] = []
    for r in raw_rows:
        try:
            uuid.UUID(r["pid"])
        except ValueError:
            raise SourceIndexError(f"{r['radicado']}: el pid {r['pid']!r} no es un UUID") from None
        want_prefix = f"{base_prefix}/{r['pid']}/"
        uri = r["s3uri"]
        if not uri.startswith("s3://"):
            raise SourceIndexError(f"{r['radicado']}: s3uri inválido {uri!r}")
        u_bucket, _, u_key = uri[5:].partition("/")
        if u_bucket != bucket:
            raise SourceIndexError(f"{r['radicado']}: el bucket {u_bucket} es de otro ambiente "
                                   f"(el workarea de este ambiente es {bucket})")
        if u_key != want_prefix:
            raise SourceIndexError(f"{r['radicado']}: la key {u_key!r} no coincide con {want_prefix!r}")
        rows.append(IndexRow(r["radicado"], r["pid"], bucket, want_prefix))
    if only:
        missing = [c for c in only if c not in {r.radicado for r in rows}]
        if missing:
            raise SourceIndexError(f"claims no presentes en el índice: {', '.join(missing)}")
        rows = [r for r in rows if r.radicado in only]
    return rows


def ser_cups_of(doc: Any) -> set[str]:
    """CUPS de un SER: formato viejo (RIPS) o nuevo (``detalles``)."""
    if isinstance(doc, dict) and "detalles" in doc:
        return {d["codigo_cups"] for d in doc["detalles"] if d.get("codigo_cups")}
    try:
        servicios = doc[0]["Datos_servicios_reclamacion"]["Servicios"]
    except (KeyError, IndexError, TypeError):
        return set()
    return {s["Codificacion_CUPS"] for s in servicios if s.get("Codificacion_CUPS")}


def extract_id_paquete(ruta: str) -> str | None:
    """Réplica de ``_extract_id_paquete`` del CDK (lambda-build-audit-response/index.py:798-828).

    Verificado: URL con host con punto -> usa el path; si no, host+path. idPaquete = 3.er
    segmento, numérico. Ej.: https://x.y/outputs/890981726/1072/archivos/... -> "1072".
    """
    if not ruta:
        return None
    if "://" in ruta:
        parsed = urlparse(ruta)
        path = parsed.path if "." in parsed.netloc else f"{parsed.netloc}/{parsed.path.lstrip('/')}"
    else:
        path = ruta
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or not parts[2].isdigit():
        return None
    return parts[2]


def delivery_problem(body: dict) -> str | None:
    """Por qué NO habría entrega a SIA con este request, o None si es entregable.

    El payload de entrega (build-audit-response/index.py:938-941) toma ``nit`` de
    ``request.nitEntidad`` e ``idPaquete`` de ``soportes.rutaArchivosSoportes`` (3.er
    segmento). SIA responde 422 si falta alguno.
    """
    problems = []
    if not str(body.get("nitEntidad") or "").strip():
        problems.append("nitEntidad vacío")
    ruta = (body.get("soportes") or {}).get("rutaArchivosSoportes") or ""
    if extract_id_paquete(ruta) is None:
        problems.append(f"idPaquete no derivable de rutaArchivosSoportes={ruta!r}")
    return "; ".join(problems) or None


def _received(item: dict) -> datetime | None:
    for ev in item.get("events") or []:
        if ev.get("description") == "received" and ev.get("timestamp"):
            return datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
    raw = item.get("created_at")
    return datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None


def tracker_pids(ddb: Any, env: str, claim_id: int) -> list[str]:
    """Todos los process_id del claim en el tracker, el más antiguo primero.

    GSI ``claim_id_created_date_index`` (docs/data-catalog/dynamo-tracker.md:49): el sort key es
    el día; el orden fino sale del evento ``received``.
    """
    deser = TypeDeserializer()
    kwargs: dict = dict(TableName=f"adr-{env}-medicalaudit-tracker-data", IndexName="claim_id_created_date_index",
                        KeyConditionExpression="claim_id = :c",
                        ExpressionAttributeValues={":c": {"S": str(claim_id)}},
                        ProjectionExpression="process_id, created_at, events", ScanIndexForward=True)
    items: list[dict] = []
    while True:
        resp = ddb.query(**kwargs)
        items += [{k: deser.deserialize(v) for k, v in i.items()} for i in resp["Items"]]
        if not resp.get("LastEvaluatedKey"):
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    epoch = datetime.fromtimestamp(0).astimezone()
    items.sort(key=lambda i: _received(i) or epoch)
    return [i["process_id"] for i in items]


@dataclass
class SourceClaim:
    row: IndexRow
    raw: list[tuple[str, int]]          # (nombre relativo a <intake>, tamaño)
    artifacts: list[tuple[str, int]]
    consolidated: bool
    request_bytes: bytes
    request_body: dict
    invoice: dict | None = None
    ser_cups: set[str] = field(default_factory=set)
    request_pid: str = ""               # pid de cuyo raw/request.json salen el body y la copia
    inspected: list[tuple[str, str]] = field(default_factory=list)  # (pid, motivo) descartados

    def invoice_cups(self) -> set[str]:
        return {d["codigo_cups"] for d in (self.invoice or {}).get("detalles", []) if d.get("codigo_cups")}

    def cups_mismatch(self) -> str | None:
        if not (self.invoice or {}).get("detalles"):
            return "claim_invoice_details de origen vacío o ausente (suprimiría la consulta a SIA)"
        inv, ser = self.invoice_cups(), self.ser_cups
        if inv != ser:
            return (f"CUPS de la factura != CUPS del SER: solo en factura {sorted(inv - ser)}, "
                    f"solo en SER {sorted(ser - inv)}")
        return None


def _list(s3: Any, bucket: str, prefix: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        out += [(o["Key"][len(prefix):], o["Size"]) for o in page.get("Contents", [])
                if not o["Key"].endswith("/")]
    return out


def _exists(s3: Any, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _read(s3: Any, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def _read_request(s3: Any, bucket: str, live: LivePaths, base_prefix: str, pid: str) -> bytes | None:
    key = f"{base_prefix}/{pid}/{live.intake}{REQUEST_NAME}"
    return _read(s3, bucket, key) if _exists(s3, bucket, key) else None


def _pick_request(s3: Any, ddb: Any, env: str, bucket: str, live: LivePaths, row: IndexRow,
                  row_body: dict, mode: str, require_deliverable: bool):
    """(pid, bytes, body, descartados) del request.json a reutilizar.

    ``source``: el request del pid del índice puede ser el que FABRICÓ pipeline_runner (nit y
    factura nulos, ruta inventada) y la entrega a SIA falla con 422. El original es la primera
    llegada real del radicador: el pid MÁS ANTIGUO del claim en el tracker cuyo request.json
    exista (el más viejo del tracker puede no tener objetos en S3) y sea entregable.
    ``source:<pid>``: ese pid exacto (mismo workarea).
    """
    base = row.prefix.split("/")[0]
    if mode.startswith("source:"):
        pid = mode.split(":", 1)[1]
        try:
            uuid.UUID(pid)
        except ValueError:
            raise SourceIndexError(f"--request source:<pid>: {pid!r} no es un UUID") from None
        data = _read_request(s3, bucket, live, base, pid)
        if data is None:
            raise SourceIndexError(f"{row.radicado}: el pid {pid} no tiene {live.intake}{REQUEST_NAME} en {bucket}")
        return pid, data, json.loads(data), []
    inspected: list[tuple[str, str]] = []
    for pid in tracker_pids(ddb, env, row_body["idReclamacion"]):
        data = _read_request(s3, bucket, live, base, pid)
        if data is None:
            inspected.append((pid, "sin request.json en S3"))
            continue
        body = json.loads(data)
        problem = delivery_problem(body)
        if problem and require_deliverable:
            inspected.append((pid, f"no entregable: {problem}"))
            continue
        return pid, data, body, inspected
    listing = "; ".join(f"{p}: {why}" for p, why in inspected) or "(el tracker no tiene pids)"
    raise SourceIndexError(f"{row.radicado}: ningún pid del tracker tiene un request.json original "
                           f"entregable. Inspeccionados: {listing}")


def load_source(s3: Any, bucket: str, live: LivePaths, row: IndexRow, *, want_invoice: bool,
                ddb: Any = None, env: str = "", request_mode: str = "row",
                require_deliverable: bool = True) -> SourceClaim:
    raw_prefix = f"{row.prefix}{live.intake}"
    raw = _list(s3, bucket, raw_prefix)
    artifacts = _list(s3, bucket, f"{row.prefix}{live.structured}")
    consolidated = _exists(s3, bucket, f"{row.prefix}{live.consolidated}consolidated.json")
    names = {n for n, _ in raw}
    if REQUEST_NAME not in names:
        raise SourceIndexError(f"{row.radicado}: el pid {row.pid} no tiene {live.intake}{REQUEST_NAME}")
    row_bytes = _read(s3, bucket, raw_prefix + REQUEST_NAME)
    row_body = json.loads(row_bytes)
    if request_mode == "row":
        pid, request_bytes, body, inspected = row.pid, row_bytes, row_body, []
    else:
        pid, request_bytes, body, inspected = _pick_request(
            s3, ddb, env, bucket, live, row, row_body, request_mode, require_deliverable)
    sc = SourceClaim(row, raw, artifacts, consolidated, request_bytes, body, request_pid=pid,
                     inspected=inspected)
    if want_invoice:
        if INVOICE_NAME not in names:
            raise SourceIndexError(f"{row.radicado}: el pid {row.pid} no tiene {INVOICE_NAME}")
        sc.invoice = json.loads(_read(s3, bucket, raw_prefix + INVOICE_NAME))
        for n in sorted(n for n in names if n.startswith("SER_") and n.endswith(".json")):
            sc.ser_cups |= ser_cups_of(json.loads(_read(s3, bucket, raw_prefix + n)))
    return sc

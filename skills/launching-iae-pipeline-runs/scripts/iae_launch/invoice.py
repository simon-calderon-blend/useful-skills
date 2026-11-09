"""``claim_invoice_details.json``: archivo local o derivado de ``SER_*.json``.

Port de IntelligentAuditEngine/scripts/claim_invoice.py:58-81. Diferencia clave:
JAMÁS se fabrica ``{"detalles": []}`` (suprime la consulta a SIA); vacío es error.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .claims import RAW_DIR

FILENAME = "claim_invoice_details.json"


class InvoiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class InvoiceResult:
    details: dict
    count: int
    origin: str  # archivo de origen


def _from_ser(raw) -> dict:
    if isinstance(raw, dict) and "detalles" in raw:
        return raw
    try:
        servicios = raw[0]["Datos_servicios_reclamacion"]["Servicios"]
        detalles = [{
            "id_servicio_factura": s.get("Clave_registro") or i,
            "codigo_servicio": s.get("Codigo_del_servicio"),
            "codigo_cups": s.get("Codificacion_CUPS") or None,
            "cantidad_servicio": int(float(s["Cantidad_de_servicios"])),
            "valor_unitario_fact": float(s["Valor_unitario_facturado"]),
            "consecutivo_procedimiento_qui": None,
            "codigo_procedimiento_qui": None,
        } for i, s in enumerate(servicios, start=1)]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise InvoiceError(f"formato de SER no reconocido ({type(exc).__name__}: {exc})") from None
    return {"detalles": detalles}


def resolve_invoice(claim_dir: Path, mode: str) -> InvoiceResult:
    raw_dir = claim_dir / RAW_DIR
    if mode == "local":
        path = raw_dir / FILENAME
        if not path.is_file():
            raise InvoiceError(f"falta {RAW_DIR}/{FILENAME}")
        details = json.loads(path.read_text(encoding="utf-8"))
    elif mode == "ser":
        sers = sorted(n for n in os.listdir(raw_dir) if n.startswith("SER_") and n.endswith(".json"))
        if not sers:
            raise InvoiceError(f"no hay SER_*.json en {RAW_DIR}")
        path = raw_dir / sers[0]
        details = _from_ser(json.loads(path.read_text(encoding="utf-8")))
    else:
        raise InvoiceError(f"modo de factura {mode!r} desconocido (local|ser)")
    items = details.get("detalles") if isinstance(details, dict) else None
    if not items:
        raise InvoiceError(f"{path.name}: 'detalles' vacío o ausente (suprimiría la consulta a SIA)")
    return InvoiceResult(details, len(items), path.name)

"""Cuerpo de POST /iniciar y su validación contra el esquema del API."""

from __future__ import annotations

import json
from importlib import resources

from jsonschema import Draft4Validator

SCHEMA_FILE = "iniciar_request.schema.json"


def _set_path(body: dict, dotted: str, value) -> None:
    obj = body
    *head, last = dotted.split(".")
    for k in head:
        obj = obj[k]
    obj[last] = value


def build_iniciar_body(fields: dict, folder: str, today: str, env: str,
                       skip_delivery: bool = False) -> dict:
    """Port de cli.py:452-503. ``idSoporte`` es entero o None (esquema integer|null).

    ``skipDelivery`` solo existe en test: el init handler lo rechaza fuera de test.
    """
    if skip_delivery and env != "test":
        raise ValueError("skipDelivery solo en test (el servidor lo rechaza en otros ambientes)")
    body: dict = {
        "idReclamacion": None, "idSolicitud": None, "numeroSolicitud": None,
        "numeroRadicado": None, "fechaRadicacion": today, "numero_factura": None,
        "nitEntidad": None, "nombreEntidad": None,
        "soportes": {
            "rutaArchivosObligatorios": f"{folder}/obligatorios",
            "rutaArchivosSoportes": f"{folder}/soportes",
            "idSoporte": None,
            "nombreFUR": None, "rutaFUR": None, "nombreRIPS": None, "rutaRIPS": None,
            "nombreFEV": None, "rutaFEV": None, "nombreCUV": None, "rutaCUV": None,
            "nombreFURRG": None, "rutaFURRG": None,
        },
    }
    for key, value in fields.items():
        _set_path(body, key, value)
    if skip_delivery:
        body["skipDelivery"] = True
    return body


def load_schema() -> dict:
    return json.loads(resources.files("iae_launch").joinpath(SCHEMA_FILE).read_text("utf-8"))


def validate_body(body: dict) -> list[str]:
    validator = Draft4Validator(load_schema())
    return [f"{'/'.join(map(str, e.absolute_path)) or '<raíz>'}: {e.message}"
            for e in sorted(validator.iter_errors(body), key=lambda e: list(map(str, e.path)))]

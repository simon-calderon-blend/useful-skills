"""POST /iniciar y sondeo GET /proceso/<uuid> sobre una fábrica de conexiones."""

from __future__ import annotations

import json
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .auth import Token

TIMEOUT = 30
ConnFactory = Callable[[str, int, float], Any]


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body or '(cuerpo vacío)'}")
        self.status, self.body = status, body


@dataclass(frozen=True)
class IniciarResult:
    accepted: bool
    process_id: str | None
    estado: str | None
    mensaje: str
    bad_response: bool = False


def _request(factory: ConnFactory, method: str, url: str, token: Token,
             body: dict | None = None, timeout: float = TIMEOUT) -> tuple[int, bytes]:
    parts = urllib.parse.urlsplit(url)
    headers = {"Authorization": f"Bearer {token.value}"}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn = factory(parts.hostname, parts.port or 443, timeout)
    try:
        conn.request(method, parts.path or "/", body=payload, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return False
    return isinstance(value, str)


def post_iniciar(factory: ConnFactory, base_url: str, token: Token, body: dict) -> IniciarResult:
    status, raw = _request(factory, "POST", base_url.rstrip("/") + "/iniciar", token, body)
    if not 200 <= status < 300:
        raise ApiError(status, raw.decode("utf-8", "replace").strip()[:500])
    try:
        doc = json.loads(raw)
    except ValueError:
        raise ApiError(status, "respuesta no es JSON") from None
    estado = doc.get("estado")
    pid = doc.get("idProcessIA")
    if estado == "RECIBIDO" and not _is_uuid(pid):
        # Un RECIBIDO sin pid válido no sirve para sembrar: sembraría bajo una clave inventada.
        return IniciarResult(False, pid if isinstance(pid, str) else None, estado,
                             f"idProcessIA inválido en la respuesta: {pid!r}", bad_response=True)
    return IniciarResult(estado == "RECIBIDO", pid, estado, doc.get("mensaje", ""))


def probe_proceso(factory: ConnFactory, base_url: str, token: Token, probe_id: str) -> int:
    status, _ = _request(factory, "GET", f"{base_url.rstrip('/')}/proceso/{probe_id}", token)
    return status

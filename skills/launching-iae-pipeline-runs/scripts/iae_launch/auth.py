"""Keycloak client_credentials. El secreto llega solo por IAE_CLIENT_SECRET.

Nunca se imprime ni se loguea el secreto ni el token (``Token`` oculta su repr).
Port de pipeline_runner/api_client.py:get_token (131-176), sin leer Secrets Manager.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .envs import EnvSpec

TIMEOUT = 15


class AuthError(RuntimeError):
    pass


class Token:
    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Token(***)"

    __str__ = __repr__


def get_token(spec: EnvSpec, client_secret: str, *,
              opener: Callable[..., Any] = urllib.request.urlopen, timeout: int = TIMEOUT) -> Token:
    form = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "client_id": spec.client_id,
                                   "client_secret": client_secret}).encode()
    if not spec.token_url.startswith("https://"):
        raise AuthError("token_url debe ser https")
    req = urllib.request.Request(spec.token_url, data=form, method="POST",  # noqa: S310 - https verificado arriba
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(req, timeout=timeout) as resp:  # noqa: S310 - esquema https verificado arriba
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise AuthError(f"Keycloak respondió HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AuthError(f"error de red al pedir token ({type(exc).__name__})") from None
    except ValueError:
        raise AuthError("respuesta de Keycloak no es JSON") from None
    if not payload.get("access_token"):
        raise AuthError("la respuesta de Keycloak no trae access_token")
    return Token(payload["access_token"])


def decode_claims(token: Token) -> dict:
    """Payload del JWT (base64url, SIN verificar firma). Solo para inspeccionar aud/exp."""
    try:
        seg = token.value.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
    except (IndexError, ValueError):
        raise AuthError("el token no es un JWT decodificable") from None


def audiences(claims: dict) -> list[str]:
    aud = claims.get("aud")
    if aud is None:
        return []
    return [aud] if isinstance(aud, str) else list(aud)

"""Tabla estática por ambiente (solo dev y test) y guarda de perfiles sensibles."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REGION = "us-east-1"
TOKEN_URL = "https://iam.test.ia.adres.gov.co/realms/master/protocol/openid-connect/token"  # noqa: S105 - URL pública
SECRET_ENV_VAR = "IAE_CLIENT_SECRET"  # noqa: S105 - nombre de variable, no un secreto


@dataclass(frozen=True)
class EnvSpec:
    name: str
    account_id: str
    profile: str
    secret_name: str
    secret_key: str
    client_id: str
    token_url: str
    bastion_instance_id: str
    # test cierra el dispatch al terminar el lote (el runner lo hace igual).
    leave_dispatch_closed_after: bool


ENVS: dict[str, EnvSpec] = {
    "dev": EnvSpec("dev", "072055531089", "ADR-DEV-MEDICALAUDIT",
                   "adr-dev-medicalaudit-scriptconnection", "secretapi",
                   "adr-dev-medicalaudit-radicador", TOKEN_URL, "i-068050b46fe0feabb", False),
    # El runner trae el perfil viejo ADRES-TEST-MEDICAL-AUDIT-1 (ya no existe en
    # ~/.aws/config): el vigente es ADR-TEST-MEDICALAUDIT.
    "test": EnvSpec("test", "276553701208", "ADR-TEST-MEDICALAUDIT",
                    "adr-test-medicalaudit-scriptconnection", "secretapi",
                    "adr-test-medicalaudit-radicador", TOKEN_URL, "i-07eb9e02496576639", True),
}

_SENSITIVE_RE = re.compile(r"PROD|MASTER|SECURITY|SENSITIVE", re.IGNORECASE)
_SENSITIVE_EXACT = {"civileza-prod", "civileza-mpa"}


def get_env(name: str) -> EnvSpec:
    try:
        return ENVS[name]
    except KeyError:
        raise ValueError(f"ambiente {name!r} no soportado (solo {', '.join(ENVS)})") from None


def is_sensitive_profile(name: str) -> bool:
    return name in _SENSITIVE_EXACT or bool(_SENSITIVE_RE.search(name))


def expected_audience(env_name: str) -> str:
    return f"adr-{env_name}-medicalaudit-intelligent-audit-engine-api"


_ASM_MARKER = "aws___run_script"  # los asm-exec viejos llaman a la tool aws___call_aws, ya eliminada
_PLUGIN_GLOB = (".claude/plugins/cache/agent-toolkit-for-aws/aws-core/*/skills/"
                "aws-secrets-manager/references/asm-exec")


def _works(path: Path) -> bool:
    try:
        return _ASM_MARKER in path.read_text(errors="replace")
    except OSError:
        return False


def _version_key(path: Path) -> tuple:
    version = path.parts[-5]  # .../aws-core/<version>/skills/aws-secrets-manager/references/asm-exec
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", version))


def find_asm_exec(which: Callable[[str], str | None] = shutil.which,
                  home: Path | None = None) -> list[str] | None:
    """Invocación de un asm-exec FUNCIONAL, o None. Nunca se resuelve el secreto de otra forma."""
    found = which("asm-exec")
    if found and _works(Path(found)):
        return [found]
    plugin = sorted((p for p in (home or Path.home()).glob(_PLUGIN_GLOB) if _works(p)),
                    key=_version_key, reverse=True)
    return ["python3", str(plugin[0])] if plugin else None


def resolve_asm_exec() -> list[str] | None:
    return find_asm_exec()


def asm_exec_command(env: EnvSpec, argv: list[str], asm: list[str] | None = None) -> list[str]:
    """Comando exacto para correr ``argv`` con el secreto inyectado por asm-exec.

    El secreto nunca pasa por el contexto: ``{{resolve:...}}`` lo resuelve asm-exec
    en tiempo de ejecución.
    """
    asm = asm or resolve_asm_exec() or ["asm-exec"]
    ref = f"{{{{resolve:secretsmanager:{env.secret_name}:SecretString:{env.secret_key}}}}}"
    return ["env", f"AWS_PROFILE={env.profile}", f"AWS_REGION={REGION}",
            *asm, "--", "env", f"{SECRET_ENV_VAR}={ref}", *argv]

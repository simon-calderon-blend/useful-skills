"""Carpetas de claims: listado, parseo del nombre, prerequisitos y PDFs grandes.

Port de pipeline_runner/cli.py:221-236 (plantilla -> regex) y 332-341, SIN el
fallback ``abs(hash(nombre)) % 10**9`` de cli.py:341: un id basura enviado al API
es peor que un error.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path

RAW_DIR = "000_reclamacion_cruda"
DEFAULT_NAME_TEMPLATE = "<ignore>_<numero>"
IGNORED = {"ignore", "null", "_", "x"}
REQUIRED_INT_IDS = ("idReclamacion", "idSolicitud")

# placeholder -> (rutas dotted del body, cast). cli.py FIELD_TARGETS.
FIELD_TARGETS: dict[str, tuple[list[str], type]] = {
    "numero": (["idReclamacion", "idSolicitud", "numeroSolicitud", "numeroRadicado"], int),
    "id_reclamacion": (["idReclamacion"], int),
    "id_solicitud": (["idSolicitud"], int),
    "numero_solicitud": (["numeroSolicitud"], int),
    "numero_radicado": (["numeroRadicado"], int),
    "numero_factura": (["numero_factura"], str),
    "nit_entidad": (["nitEntidad"], str),
    "nombre_entidad": (["nombreEntidad"], str),
    "id_soporte": (["soportes.idSoporte"], int),
}
_PLACEHOLDER = re.compile(r"<(\w+)>")


class ClaimNameError(ValueError):
    """El nombre de la carpeta no produce ids válidos."""


def compile_name_template(template: str) -> re.Pattern:
    parts, pos = ["^"], 0
    for m in _PLACEHOLDER.finditer(template):
        parts.append(re.escape(template[pos:m.start()]))
        name = m.group(1)
        parts.append(r"[^_]+" if name in IGNORED else rf"(?P<{name}>[^_]+)")
        pos = m.end()
    parts += [re.escape(template[pos:]), "$"]
    try:
        return re.compile("".join(parts))
    except re.error as exc:
        raise ClaimNameError(f"plantilla inválida {template!r}: {exc}") from None


def build_name_pattern(template: str | None = None, regex: str | None = None) -> re.Pattern:
    if regex:
        try:
            return re.compile(regex)
        except re.error as exc:
            raise ClaimNameError(f"regex inválida: {exc}") from None
    return compile_name_template(template or DEFAULT_NAME_TEMPLATE)


def parse_folder(folder: str, pattern: re.Pattern) -> dict:
    """``{ruta dotted del body: valor tipado}``. Lanza ClaimNameError, nunca inventa ids."""
    m = pattern.match(folder)
    if not m:
        raise ClaimNameError(f"{folder!r}: el nombre no coincide con el patrón {pattern.pattern!r}")
    out: dict = {}
    numero: int | None = None
    for name, raw in m.groupdict().items():
        if raw is None or name in IGNORED or name not in FIELD_TARGETS:
            continue
        keys, cast = FIELD_TARGETS[name]
        try:
            value = cast(raw)
        except ValueError:
            raise ClaimNameError(f"{folder!r}: <{name}>={raw!r} debe ser un entero") from None
        if name == "numero":
            numero = value
        for key in keys:
            out[key] = value
    # Red de seguridad por campo (cli.py:477-503): lo no capturado hereda <numero>.
    for key in (*REQUIRED_INT_IDS, "numeroSolicitud", "numeroRadicado"):
        if key not in out and numero is not None:
            out[key] = numero
    for key in REQUIRED_INT_IDS:
        if key not in out:
            raise ClaimNameError(f"{folder!r}: no se pudo obtener {key} (entero) del nombre")
    return out


def list_claim_dirs(source_dir: Path | str) -> list[str]:
    """``os.listdir``, nunca ``ls`` (alias con decoraciones)."""
    root = Path(source_dir)
    if not root.is_dir():
        raise ClaimNameError(f"el directorio de claims no existe: {root}")
    return sorted(n for n in os.listdir(root)
                  if not n.startswith(".") and (root / n).is_dir())


def raw_files(claim_dir: Path) -> list[str]:
    raw = claim_dir / RAW_DIR
    return sorted(n for n in os.listdir(raw) if not n.startswith(".") and (raw / n).is_file())


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    status: str  # ok | warn | FAILED
    detail: str


def evaluate_rules(rules: list[dict], filenames: list[str]) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in rules:
        rid, kind = rule.get("id", "?"), rule.get("type")
        if kind == "document_exists":
            globs = rule["glob"] if isinstance(rule["glob"], list) else [rule["glob"]]
            present = any(fnmatch.fnmatch(f, g) for f in filenames for g in globs)
            expect_present = rule.get("expect", "present") == "present"
            if present == expect_present:
                results.append(RuleResult(rid, "ok", ""))
            else:
                word = "falta" if expect_present else "sobra"
                results.append(RuleResult(
                    rid, "FAILED", f"{rid}: {word} un archivo que cumpla {' | '.join(globs)}"))
        elif kind == "json_jsonata":
            results.append(RuleResult(rid, "warn", f"{rid}: json_jsonata no evaluada localmente"))
        else:
            results.append(RuleResult(rid, "warn", f"{rid}: tipo de regla {kind!r} desconocido"))
    return results


def large_pdfs(claim_dir: Path, limit_bytes: int = 25 * 1024 * 1024) -> list[tuple[str, int]]:
    raw = claim_dir / RAW_DIR
    sized = [(n, (raw / n).stat().st_size) for n in raw_files(claim_dir) if n.lower().endswith(".pdf")]
    return [(n, s) for n, s in sized if s > limit_bytes]

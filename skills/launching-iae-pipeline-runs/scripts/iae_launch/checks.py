"""Checks de preflight. Cada check es independiente y devuelve un ``Check``.

``prevents`` cita el error real que cada check evita (para que el operador entienda
por qué importa). Ninguna excepción dentro de un check sale de ``guarded``.
"""

from __future__ import annotations

import configparser
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from . import auth, dispatch, envs, jumphost
from . import claims as claims_mod
from . import invoice as invoice_mod
from . import live as live_mod
from . import request as request_mod
from . import sourceindex as sourceindex_mod
from .envs import EnvSpec, is_sensitive_profile

PREVENTS: dict[str, str] = {
    "profile_not_sensitive": "AWS.md: perfiles PROD/MASTER/SECURITY/SENSITIVE son solo lectura",
    "profile_in_aws_config": "ProfileNotFound: The config profile (ADRES-TEST-MEDICAL-AUDIT-1) could not be found",
    "aws_identity": "Token has expired and refresh failed / perfil de otra cuenta",
    "sso_session_remaining": "poll_failed a mitad de corrida por SSO expirado",
    "appconfig_live": "ResourceNotFoundException: DeploymentStrategy/Hosted Configuration Version/Environment Id ... could not be found (IDs copiados entre cuentas)",  # noqa: E501
    "ingest_mapping_consistency": "estructuración sembrada en staging/structured, prefijo que el motor no lee",
    "dispatch_flag": "24/24 claims en execution_not_started: dispatch=False y nadie lo abrió",
    "runtime_qualifier": "qualifier del repo != vivo (DEFAULT vs v4_x)",
    "dispatch_strategy": "deployment con bake que excede el timeout de 120 s",
    "foreign_breadcrumb": "pausa huérfana de otro run: el dispatch quedaría en un estado ajeno",
    "running_executions": "lote compartido: 117 records vs 94 esperados por procesos ajenos",
    "conveyor_depth": "gate de Bedrock < 100 registros",
    "bastion_online": "transporte SSM sin plugin o bastión offline",
    "client_secret_present": "Consulta a FUCTAS fallida: HTTPError (HTTP 401)",
    "token_audience": "401 Token audience does not match (mapper de Keycloak vacío)",
    "api_probe": "API privada inalcanzable / token rechazado",
    "claims_exist": "Radicados not found in ../../runs/e2e_test_input: Permissions, Size, User, Date… (alias de ls) / ground_truth directory not found",  # noqa: E501
    "claim_id_parses": "idReclamacion 909656568 basura por fallback a hash() (cli.py:341)",
    "prerequisite_globs": "ClaimNotEligibleError factura-obligatoria FAC_*.pdf (FACT_ vs FAC_)",
    "large_pdfs": "413 Input is too long (PDF de 317 MB)",
    "tracker_duplicates": "POST /iniciar rechazado: estado != RECIBIDO (duplicado < 48 h)",
    "request_json_override": "request.json local pisó al generado por la API (radicado 3123)",
    "invoice_details": 'SER ausente (RuntimeError) / {"detalles": []} suprime SIA',
    "structuring_source": "re-extracción completa: artefactos sin consolidated.json",
    "invoice_matches_ser": "CUPS de claim_invoice_details != CUPS del SER: auditoría con servicios distintos",
    "request_deliverable": "SIA HTTP 422 al entregar: nit/idPaquete vacíos (request fabricado por pipeline_runner)",
    "count_throttle": "ThrottlingException → wait: failed para 25-47 claims",
    "batch_gate_estimate": "Ejecuciones 1.5 h en DocExtraction: gate queue has 82 < 100",
}

SSO_MSG = "Sesión SSO expirada: pide al usuario correr 'awsl' (no lo ejecutes)."
_SSO_RE = re.compile(r"ExpiredToken|Token has expired|LoginRefreshRequired|UnauthorizedSSOToken|"
                     r"SSOTokenLoadError")
SSO_WARN_MINUTES = 90
LARGE_PDF_BYTES = 25 * 1024 * 1024
THROTTLE_CLAIMS = 20
RECORDS_PER_CLAIM = 8
TERMINAL_TRACKER = {"SF_SUCCEEDED", "SF_FAILED", "SF_TIMED_OUT", "SF_ABORTED"}


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | warn | FAILED | skipped
    detail: str
    prevents: str


@dataclass(frozen=True)
class Report:
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return not any(c.status == "FAILED" for c in self.checks)

    def to_json(self) -> str:
        return json.dumps({"ok": self.ok, "checks": [asdict(c) for c in self.checks]},
                          ensure_ascii=False, indent=2)


def guarded(name: str, fn: Callable[[], tuple[str, str]]) -> Check:
    prevents = PREVENTS.get(name, "")
    try:
        status, detail = fn()
    except Exception as exc:  # noqa: BLE001 - un check nunca tumba al resto
        text = f"{type(exc).__name__}: {exc}"
        if _SSO_RE.search(text):
            return Check(name, "FAILED", SSO_MSG, prevents)
        if isinstance(exc, ClientError) and str(
                exc.response.get("Error", {}).get("Code", "")).startswith("AccessDenied"):
            return Check(name, "skipped", f"sin permisos (AccessDenied): {exc}", prevents)
        return Check(name, "FAILED", text, prevents)
    return Check(name, status, detail, prevents)


# ---------------------------------------------------------------- perfil / sesión
def check_profile_not_sensitive(profile: str) -> Check:
    def run():
        if is_sensitive_profile(profile):
            return "FAILED", f"el perfil {profile} es sensible: solo lectura, no se lanza con él"
        return "ok", profile
    return guarded("profile_not_sensitive", run)


def _read_config(path: Path) -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser()
    if not cp.read(path):
        raise FileNotFoundError(f"no se pudo leer {path}")
    return cp


def check_profile_in_config(profile: str, config_path: Path) -> Check:
    def run():
        if f"profile {profile}" not in _read_config(config_path):
            return "FAILED", f"el perfil {profile} no está en {config_path}"
        return "ok", f"[profile {profile}] presente"
    return guarded("profile_in_aws_config", run)


def check_aws_identity(sts: Any, spec: EnvSpec) -> Check:
    def run():
        account = sts.get_caller_identity()["Account"]
        if account != spec.account_id:
            return "FAILED", f"cuenta {account}, se esperaba {spec.account_id} ({spec.name})"
        return "ok", f"cuenta {account}"
    return guarded("aws_identity", run)


def _parse_ts(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_sso_remaining(profile: str, config_path: Path, cache_dir: Path, now: datetime) -> Check:
    def run():
        cp = _read_config(config_path)
        section = f"profile {profile}"
        session = cp.get(section, "sso_session", fallback=None) if cp.has_section(section) else None
        if not session:
            return "skipped", "el perfil no usa sso_session"
        cache = Path(cache_dir) / f"{hashlib.sha1(session.encode(), usedforsecurity=False).hexdigest()}.json"
        if not cache.is_file():
            return "skipped", f"sin caché SSO para la sesión {session}"
        # SOLO expiresAt: el archivo también contiene tokens que jamás se leen.
        expires = _parse_ts(json.loads(cache.read_text())["expiresAt"])
        left = expires - now
        mins = int(left.total_seconds() // 60)
        if left <= timedelta(0):
            return "FAILED", SSO_MSG
        if mins < SSO_WARN_MINUTES:
            return "warn", f"quedan {mins} min de sesión SSO (< {SSO_WARN_MINUTES}): puede vencer a mitad de corrida"
        return "ok", f"quedan {mins // 60} h {mins % 60} min de sesión SSO"
    return guarded("sso_session_remaining", run)


# ---------------------------------------------------------------- configuración viva
def check_appconfig_live(gather: Callable[[], live_mod.LivePaths]):
    holder: dict[str, live_mod.LivePaths] = {}

    def run():
        lp = gather()
        holder["lp"] = lp
        if lp.in_progress:
            pend = ", ".join(f"{k}={v}" for k, v in lp.in_progress.items())
            return "FAILED", f"hay deployments en curso: {pend}"
        vers = ", ".join(f"{k}=v{v}" for k, v in lp.versions.items())
        return "ok", vers
    check = guarded("appconfig_live", run)
    return check, holder.get("lp")


def _needs_live(name: str, lp, fn: Callable[[], tuple[str, str]]) -> Check:
    if lp is None:
        return Check(name, "skipped", "depende de appconfig_live", PREVENTS[name])
    return guarded(name, fn)


def check_ingest_mapping(lp) -> Check:
    def run():
        missing = live_mod.ingest_mismatches(lp)
        if missing:
            return "FAILED", f"el motor no lee estos prefijos sembrados: {', '.join(missing)}"
        return "ok", f"intake {lp.intake} y structured {lp.structured} están en engine_ingest_mappings"
    return _needs_live("ingest_mapping_consistency", lp, run)


def _vkey(name: str) -> tuple:
    m = re.fullmatch(r"v(\d+)_(\d+)_(\d+)", name)
    return tuple(int(x) for x in m.groups()) if m else ()


def check_runtime_qualifier(lp, agentcore: Any = None, env: str = "") -> Check:
    """Qualifier vivo + (si hay cliente) que exista y esté READY en AgentCore.

    La skill NO cambia el qualifier: es una decisión explícita aparte (perfil
    adr-<env>-medicalaudit-intelligent-audit-engine-appconfig/runtime; la extensión
    del invoker sondea cada 5 min: esperar >= 5 min antes de despachar).
    """
    def run():
        detail = f"qualifier vivo: {lp.qualifier}"
        if agentcore is None:
            return "ok", detail
        name = f"adr_{env}_medicalaudit_intelligent_audit_engine"
        runtimes = [r for page in agentcore.get_paginator("list_agent_runtimes").paginate()
                    for r in page["agentRuntimes"] if r["agentRuntimeName"] == name]
        if not runtimes:
            return "warn", f"{detail}; runtime AgentCore {name} no encontrado"
        endpoints = [e for page in agentcore.get_paginator("list_agent_runtime_endpoints").paginate(
            agentRuntimeId=runtimes[0]["agentRuntimeId"]) for e in page["runtimeEndpoints"]]
        mine = next((e for e in endpoints if e["name"] == lp.qualifier), None)
        if mine is None:
            return "FAILED", f"{detail}: el endpoint {lp.qualifier} no existe en AgentCore"
        if mine["status"] != "READY":
            return "FAILED", f"{detail}: el endpoint está {mine['status']}, no READY"
        newest = max((e["name"] for e in endpoints if _vkey(e["name"])), key=_vkey, default=None)
        if newest and _vkey(newest) > _vkey(lp.qualifier):
            return "warn", f"{detail} (READY) pero existe un endpoint más nuevo: {newest}"
        return "ok", f"{detail} (endpoint READY)"
    return _needs_live("runtime_qualifier", lp, run)


def max_messages_note(lp, n_claims: int) -> str:
    """maxMessagesPerCycle: con más claims que el tope, el despacho se reparte en ciclos de 2 min."""
    cap = lp.dispatch.content.get("values", {}).get("dispatch", {}).get("maxMessagesPerCycle")
    if not cap:
        return ""
    note = f"; maxMessagesPerCycle={cap}"
    if n_claims > cap:
        note += f": {n_claims} claims se despacharán en {-(-n_claims // cap)} ciclos de 2 min"
    return note


def check_dispatch_flag(appconfig: Any, lp, allow_open: bool, n_claims: int = 0) -> Check:
    def run():
        status, detail = _dispatch_state(appconfig, lp, allow_open)
        return status, detail + max_messages_note(lp, n_claims)
    return _needs_live("dispatch_flag", lp, run)


def _dispatch_state(appconfig: Any, lp, allow_open: bool) -> tuple[str, str]:
    if live_mod.read_dispatch_enabled(lp.dispatch):
        return "ok", "dispatch habilitado"
    if dispatch.closed_by_marker(appconfig, lp.dispatch):
        return "warn", "dispatch cerrado por un lote previo; el lanzamiento lo reabrirá"
    if allow_open:
        return "warn", "dispatch cerrado (no por un lote previo); --allow-open-dispatch lo reabrirá"
    return "FAILED", ("dispatch cerrado y no por un lote previo (¿un operador?). "
                      "Usa --allow-open-dispatch solo si es seguro abrirlo")


def check_dispatch_strategy(appconfig: Any) -> Check:
    def run():
        found = dispatch.resolve_strategy(appconfig)
        if found is None:
            return "FAILED", "no hay estrategia de deployment con duración 0 y bake 0"
        return "ok", f"estrategia {found[1]} ({found[0]})"
    return guarded("dispatch_strategy", run)


def check_foreign_breadcrumb(env: str, home: Path) -> Check:
    def run():
        found = dispatch.existing_breadcrumbs(env, home)
        if found:
            return "FAILED", "migas de pausa existentes: " + ", ".join(str(p) for p in found)
        return "ok", "sin pausas huérfanas"
    return guarded("foreign_breadcrumb", run)


# ---------------------------------------------------------------- estado vivo
def check_running_executions(sfn: Any, arn: str) -> Check:
    def run():
        n = len(sfn.list_executions(stateMachineArn=arn, statusFilter="RUNNING")["executions"])
        if n:
            return "warn", f"{n} ejecuciones RUNNING ajenas: pueden mezclarse con el lote"
        return "ok", "sin ejecuciones RUNNING"
    return guarded("running_executions", run)


def check_conveyor_depth(sqs: Any, url: str) -> tuple[Check, int | None]:
    depth: dict[str, int] = {}

    def run():
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=[
            "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
        depth["n"] = (int(attrs.get("ApproximateNumberOfMessages", 0))
                      + int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)))
        return "ok", f"{depth['n']} mensajes en la cola conveyor"
    return guarded("conveyor_depth", run), depth.get("n")


def check_bastion_online(ssm: Any, ec2: Any, spec: EnvSpec,
                         which: Callable[[str], str | None]):
    holder: dict[str, jumphost.JumpHost] = {}

    def run():
        try:
            host = jumphost.resolve(ssm, ec2, spec)
        except jumphost.JumpHostError as exc:
            return "FAILED", str(exc)
        missing = [b for b in ("session-manager-plugin", "aws") if not which(b)]
        if missing:
            return "FAILED", f"faltan binarios en PATH: {', '.join(missing)}"
        holder["h"] = host
        label = f"{host.instance_id} {host.name}".strip()
        return "ok", f"jump host {label} ({host.how}); aws y session-manager-plugin presentes"
    return guarded("bastion_online", run), holder.get("h")


# ---------------------------------------------------------------- secreto / token
def check_client_secret_present(spec: EnvSpec, environ: Mapping[str, str]) -> Check:
    def run():
        if environ.get(envs.SECRET_ENV_VAR):
            return "ok", f"{envs.SECRET_ENV_VAR} presente"
        asm = envs.resolve_asm_exec()
        if asm is None:
            return "skipped", (f"{envs.SECRET_ENV_VAR} ausente y no hay un asm-exec funcional "
                               "(ninguno contiene aws___run_script); no se resuelve el secreto de otra forma")
        cmd = " ".join(envs.asm_exec_command(spec, ["<comando>"], asm))
        return "skipped", f"{envs.SECRET_ENV_VAR} ausente; corre con: {cmd}"
    return guarded("client_secret_present", run)


def check_token_audience(spec: EnvSpec, environ: Mapping[str, str],
                         token_fn: Callable[[EnvSpec, str], auth.Token]):
    holder: dict[str, auth.Token] = {}

    def run():
        secret = environ.get(envs.SECRET_ENV_VAR)
        if not secret:
            return "skipped", f"{envs.SECRET_ENV_VAR} ausente"
        token = token_fn(spec, secret)
        claims = auth.decode_claims(token)
        auds = auth.audiences(claims)
        want = envs.expected_audience(spec.name)
        if want not in auds:
            return "FAILED", f"aud={auds} no contiene {want}"
        holder["t"] = token
        return "ok", f"aud={auds} exp={claims.get('exp')}"
    return guarded("token_audience", run), holder.get("t")


def check_api_probe(probe: Callable[[], int] | None) -> Check:
    if probe is None:
        return Check("api_probe", "skipped", "no solicitado (--probe-api)", PREVENTS["api_probe"])

    def run():
        status = probe()
        if status == 404:
            return "ok", "GET /proceso/<uuid> -> 404 (API alcanzable, token aceptado)"
        if status in (401, 403):
            return "FAILED", f"GET /proceso/<uuid> -> {status}: token rechazado"
        return "warn", f"GET /proceso/<uuid> -> {status} (inesperado)"
    return guarded("api_probe", run)


# ================================================================ claim-level
def _claim_dir(source_dir: Path, claim: str) -> Path:
    return Path(source_dir) / claim


def check_claims_exist(source_dir: Path, claim_names: list[str]) -> Check:
    def run():
        available = set(claims_mod.list_claim_dirs(source_dir))  # os.listdir, nunca ls
        bad = [c for c in claim_names
               if c not in available or not (_claim_dir(source_dir, c) / claims_mod.RAW_DIR).is_dir()]
        if bad:
            return "FAILED", f"sin carpeta o sin {claims_mod.RAW_DIR}/: {', '.join(bad)}"
        return "ok", f"{len(claim_names)} claims encontrados en {source_dir}"
    return guarded("claims_exist", run)


def check_claim_id_parses(claim_names: list[str], pattern) -> Check:
    def run():
        errors = []
        for c in claim_names:
            try:
                claims_mod.parse_folder(c, pattern)
            except claims_mod.ClaimNameError as exc:
                errors.append(str(exc))
        if errors:
            return "FAILED", "; ".join(errors)
        return "ok", f"ids enteros para {len(claim_names)} claims"
    return guarded("claim_id_parses", run)


def check_prerequisite_files(lp, files_by_claim: dict[str, list[str]]) -> Check:
    def run():
        failed, warned = [], set()
        for c, files in files_by_claim.items():
            for r in claims_mod.evaluate_rules(lp.rules, files):
                if r.status == "FAILED":
                    failed.append(f"{c}: {r.detail}")
                elif r.status == "warn":
                    warned.add(r.detail)
        if failed:
            return "FAILED", "; ".join(failed)
        if warned:
            return "warn", "; ".join(sorted(warned))
        return "ok", "reglas document_exists cumplidas"
    return _needs_live("prerequisite_globs", lp, run)


def check_prerequisite_globs(lp, source_dir: Path, claim_names: list[str]) -> Check:
    if lp is None:
        return _needs_live("prerequisite_globs", None, lambda: ("ok", ""))
    try:
        files = {c: claims_mod.raw_files(_claim_dir(source_dir, c)) for c in claim_names}
    except OSError as exc:
        return Check("prerequisite_globs", "FAILED", str(exc), PREVENTS["prerequisite_globs"])
    return check_prerequisite_files(lp, files)


def check_large_pdf_sizes(sizes_by_claim: dict[str, list[tuple[str, int]]],
                          limit_bytes: int = LARGE_PDF_BYTES) -> Check:
    def run():
        big = [f"{c}/{n} ({s / 1024 / 1024:.0f} MB)" for c, files in sizes_by_claim.items()
               for n, s in files if n.lower().endswith(".pdf") and s > limit_bytes]
        if big:
            return "warn", "PDFs sobre el límite: " + ", ".join(big)
        return "ok", "sin PDFs grandes"
    return guarded("large_pdfs", run)


def check_large_pdfs(source_dir: Path, claim_names: list[str],
                     limit_bytes: int = LARGE_PDF_BYTES) -> Check:
    def run():
        big = [f"{c}/{n} ({s / 1024 / 1024:.0f} MB)" for c in claim_names
               for n, s in claims_mod.large_pdfs(_claim_dir(source_dir, c), limit_bytes)]
        if big:
            return "warn", "PDFs sobre el límite: " + ", ".join(big)
        return "ok", "sin PDFs grandes"
    return guarded("large_pdfs", run)


def check_count_throttle(n: int) -> Check:
    def run():
        if n > THROTTLE_CLAIMS:
            return "warn", f"{n} claims > {THROTTLE_CLAIMS}: riesgo de ThrottlingException al esperar; divide el lote"
        return "ok", f"{n} claims"
    return guarded("count_throttle", run)


def check_batch_gate_estimate(n: int, conveyor_depth: int | None, min_records: int,
                              structuring_reuse: bool) -> Check:
    def run():
        if structuring_reuse:
            return "ok", "se reutiliza estructuración: no pasa por el gate de Bedrock"
        if conveyor_depth is None:
            return "warn", "profundidad del conveyor desconocida; no se puede estimar el gate"
        estimate = n * RECORDS_PER_CLAIM + conveyor_depth
        if estimate < min_records:
            return "warn", (f"~{estimate} registros < {min_records} (min_records_per_job): la corrida "
                            "esperará horas; usa la skill padding-bedrock-batch-gate")
        return "ok", f"~{estimate} registros >= {min_records}"
    return guarded("batch_gate_estimate", run)


def check_invoice_details(source_dir: Path, claim_names: list[str], mode: str) -> Check:
    def run():
        if mode == "lambda":
            return "warn", ("claim_invoice_details NO se siembra: la Lambda fetch-claim-invoice-details "
                            "consulta a SIA; 'SER ausente' es parada dura si SIA no tiene datos")
        errors = []
        for c in claim_names:
            try:
                invoice_mod.resolve_invoice(_claim_dir(source_dir, c), mode)
            except (invoice_mod.InvoiceError, ValueError, OSError) as exc:
                errors.append(f"{c}: {exc}")
        if errors:
            return "FAILED", "; ".join(errors)
        return "ok", f"claim_invoice_details resuelto ({mode}) para {len(claim_names)} claims"
    return guarded("invoice_details", run)


def check_request_json_override(source_dir: Path, claim_names: list[str], decision: str,
                                fields_by_claim: dict[str, dict]) -> Check:
    def run():
        warn, failed = [], []
        for c in claim_names:
            path = _claim_dir(source_dir, c) / claims_mod.RAW_DIR / "request.json"
            if decision == "api":
                if path.is_file():
                    warn.append(c)
                continue
            if not path.is_file():
                failed.append(f"{c}: --request local pero falta request.json")
                continue
            body = json.loads(path.read_text(encoding="utf-8"))
            errors = request_mod.validate_body(body)
            expected = fields_by_claim.get(c, {}).get("idReclamacion")
            if body.get("idReclamacion") != expected:
                errors.append(f"idReclamacion {body.get('idReclamacion')} != {expected}")
            if errors:
                failed.append(f"{c}: {'; '.join(errors)}")
        if failed:
            return "FAILED", "; ".join(failed)
        if warn:
            return "warn", "request.json local no se sembrará (lo genera el API): " + ", ".join(warn)
        return "ok", f"request: {decision}"
    return guarded("request_json_override", run)


def check_structuring_source(claim_names: list[str], plan_fn: Callable[[str], Any]) -> Check:
    def run():
        errors, total = [], 0
        for c in claim_names:
            try:
                total += plan_fn(c).artifacts
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{c}: {exc}")
        if errors:
            return "FAILED", "; ".join(errors)
        return "ok", f"{total} artefactos en total"
    return guarded("structuring_source", run)


def check_tracker_duplicates(ddb: Any, spec: EnvSpec, claim_ids: dict[str, int],
                             now: datetime) -> Check:
    """Réplica de lambda-tracker-query CHECK_DUPLICATE (index.py:139-169)."""
    deser = TypeDeserializer()

    def received(item: dict) -> datetime | None:
        for ev in item.get("events") or []:
            if ev.get("description") == "received" and ev.get("timestamp"):
                return _parse_ts(ev["timestamp"])
        return _parse_ts(item["created_at"]) if item.get("created_at") else None

    def run():
        if spec.name == "dev":
            return "skipped", "el servidor no valida duplicados en dev (check_duplicate deshabilitado)"
        since = now - timedelta(hours=48)
        dupes = []
        for folder, claim_id in claim_ids.items():
            kwargs = dict(
                TableName=f"adr-{spec.name}-medicalaudit-tracker-data",
                IndexName="claim_id_created_date_index",
                KeyConditionExpression="claim_id = :c AND created_date >= :d",
                ExpressionAttributeValues={":c": {"S": str(claim_id)},
                                           ":d": {"S": since.strftime("%Y-%m-%d")}},
                ProjectionExpression="process_id, #s, created_at, events",
                ExpressionAttributeNames={"#s": "status"})
            items = []
            while True:
                resp = ddb.query(**kwargs)
                items += [{k: deser.deserialize(v) for k, v in i.items()} for i in resp["Items"]]
                if not resp.get("LastEvaluatedKey"):
                    break
                kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            recent = [(ts, i) for i in items if (ts := received(i)) and ts >= since]
            if not recent:
                continue
            _, newest = max(recent, key=lambda p: p[0])
            if newest["status"] not in TERMINAL_TRACKER:
                dupes.append(f"{folder} (pid {newest['process_id']}, {newest['status']})")
        if dupes:
            return "FAILED", "duplicados activos < 48 h: " + ", ".join(dupes)
        return "ok", f"sin duplicados activos para {len(claim_ids)} claims"
    return guarded("tracker_duplicates", run)



# ================================================================ modo --source-index
def check_source_claims_exist(sources: dict, errors: dict[str, str]) -> Check:
    def run():
        if errors:
            return "FAILED", "; ".join(f"{c}: {m}" for c, m in errors.items())
        empty = [c for c, sc in sources.items() if not sc.raw]
        if empty or not sources:
            return "FAILED", f"el prefijo de origen no tiene objetos: {', '.join(empty) or '(ninguno)'}"
        return "ok", f"{len(sources)} claims de origen con objetos en S3"
    return guarded("claims_exist", run)


def check_source_ids(sources: dict) -> Check:
    def run():
        errors = []
        for c, sc in sources.items():
            errs = request_mod.validate_body(sc.request_body)
            if errs:
                errors.append(f"{c}: {'; '.join(errs)}")
        if errors:
            return "FAILED", "; ".join(errors)
        return "ok", f"ids tomados del request.json de origen ({len(sources)} claims), válidos contra el esquema"
    return guarded("claim_id_parses", run)


def _top_level(sc) -> list[str]:
    return [n for n, _ in sc.raw if "/" not in n and not n.startswith(".")]


def check_source_prerequisites(lp, sources: dict) -> Check:
    return check_prerequisite_files(lp, {c: _top_level(sc) for c, sc in sources.items()})


def check_source_request_skipped() -> Check:
    return Check("request_json_override", "skipped", "request de origen", PREVENTS["request_json_override"])


def check_source_invoice(sources: dict, mode: str) -> Check:
    def run():
        if mode == "lambda":
            return "ok", ("claim_invoice_details NO se siembra: la Lambda fetch-claim-invoice-details lo "
                          "genera consultando a SIA")
        bad = [c for c, sc in sources.items() if not (sc.invoice or {}).get("detalles")]
        if bad:
            return "FAILED", f"claim_invoice_details de origen vacío o ausente: {', '.join(bad)}"
        return "ok", f"claim_invoice_details de origen con detalles ({len(sources)} claims)"
    return guarded("invoice_details", run)


def check_invoice_matches_ser(sources: dict, mode: str) -> Check:
    if mode != "source":
        return Check("invoice_matches_ser", "skipped", "solo aplica con --invoice source",
                     PREVENTS["invoice_matches_ser"])

    def run():
        bad = [f"{c}: {m}" for c, sc in sources.items() if (m := sc.cups_mismatch())]
        if bad:
            return "FAILED", "; ".join(bad)
        return "ok", "los CUPS de la factura coinciden con los del SER"
    return guarded("invoice_matches_ser", run)


def check_source_structuring(sources: dict, decision: str) -> Check:
    def run():
        if decision == "none":
            return "ok", "sin reutilizar estructuración"
        empty = [c for c, sc in sources.items() if not sc.artifacts]
        if empty:
            return "FAILED", f"sin artefactos estructurados en el origen: {', '.join(empty)}"
        lost = [c for c, sc in sources.items() if not sc.consolidated]
        if lost:
            return "warn", ("consolidated.json ausente en el origen (lifecycle expirado, 7 días): "
                            "se genera un marcador para " + ", ".join(lost))
        return "ok", f"artefactos y consolidated.json presentes ({len(sources)} claims)"
    return guarded("structuring_source", run)


def check_request_deliverable(bodies: dict[str, dict], skip_delivery: bool, mode: str) -> Check:
    """¿Se podrá ENTREGAR a SIA con este request? (misma derivación que build-audit-response).

    build-audit-response/lambda-build-audit-response/index.py:938-941 arma ``nit`` desde
    ``request.nitEntidad`` e ``idPaquete`` desde el 3.er segmento de
    ``soportes.rutaArchivosSoportes`` (_extract_id_paquete, index.py:798-828). Sin ellos SIA
    responde 422 (visto en el lanzamiento real: 10/11 claims).
    """
    def run():
        bad = {c: p for c, b in bodies.items() if (p := sourceindex_mod.delivery_problem(b))}
        if not bad:
            return "ok", f"nit e idPaquete derivables en {len(bodies)} claims"
        text = "; ".join(f"{c}: {p}" for c, p in bad.items())
        if mode == "api":
            text += (". --request api (cuerpo derivado del nombre de carpeta) SIEMPRE falla esta "
                     "verificación: usa --request source (o local con un request real) o --skip-delivery")
        if skip_delivery:
            return "warn", f"no habrá entrega a SIA (skipDelivery, solo test): {text}"
        return "FAILED", f"la entrega a SIA fallaría con 422: {text}"
    return guarded("request_deliverable", run)

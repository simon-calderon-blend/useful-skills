"""Orquestación del preflight: ejecuta cada check, resuelve recursos vivos una vez."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from botocore.exceptions import ClientError

from . import auth, checks, claims, envs, sourceindex, structuring
from . import live as live_mod
from . import request as request_mod
from .checks import Check, Report
from .envs import REGION


class _LazyClient:
    """Proxy que crea el cliente solo si se usa (p. ej. ec2 únicamente si el bastión configurado falla)."""

    def __init__(self, clients: "Clients", name: str):
        self._clients, self._name = clients, name

    def __getattr__(self, attr: str):
        return getattr(self._clients[self._name], attr)


class Clients:
    """Clientes boto3 perezosos (uno por servicio). ``preset`` inyecta Stubbers en tests."""

    def __init__(self, session: Any = None, **preset: Any):
        self.session, self._cache = session, dict(preset)

    def lazy(self, name: str) -> _LazyClient:
        return _LazyClient(self, name)

    def __getitem__(self, name: str) -> Any:
        if name not in self._cache:
            self._cache[name] = self.session.client(name, region_name=REGION)
        return self._cache[name]


@dataclass
class Inputs:
    env: str
    profile: str
    source_dir: Path | None = None
    claims: list[str] = field(default_factory=list)
    name_template: str | None = None
    name_regex: str | None = None
    structuring: str = "none"
    request: str = "api"
    invoice: str = "local"
    probe_api: bool = False
    allow_open_dispatch: bool = False
    run_id: str = "preflight"
    source_index: Path | str | None = None
    skip_delivery: bool = False


def validate_inputs(inp: "Inputs") -> None:
    """Coherencia de decisiones: source/workarea solo con --source-index; lambda en ambos."""
    if inp.source_index:
        if inp.source_dir:
            raise ValueError("--source-index y --source-dir son excluyentes")
        if inp.structuring not in ("workarea", "none"):
            raise ValueError("con --source-index, --structuring es workarea | none")
        if inp.request != "source" and not re.fullmatch(r"source:[0-9a-fA-F-]{36}", inp.request):
            raise ValueError("con --source-index, --request es source | source:<pid UUID>")
        if inp.invoice not in ("source", "lambda"):
            raise ValueError("con --source-index, --invoice es source | lambda")
        return
    if inp.request.startswith("source"):
        raise ValueError("--request source requiere --source-index")
    if inp.invoice == "source":
        raise ValueError("--invoice source requiere --source-index")
    if inp.structuring == "workarea":
        raise ValueError("--structuring workarea (sin pid) requiere --source-index; usa workarea:<pid>")


@dataclass
class Resolved:
    live: live_mod.LivePaths | None = None
    api_base_url: str | None = None
    state_machine_arn: str | None = None
    bucket: str | None = None
    conveyor_url: str | None = None
    conveyor_depth: int | None = None
    jump_host: Any = None


@dataclass
class PreflightResult:
    report: Report
    resolved: Resolved
    fields_by_claim: dict[str, dict]
    pattern: Any = None
    sources: dict = field(default_factory=dict)


PREVENTS_EXTRA = {"live_resources": "recurso no encontrado: nombre exacto distinto (copias e1-adr-dev-*) "
                                     "o ambiente equivocado"}
checks.PREVENTS.update(PREVENTS_EXTRA)


def _resolve_resources(clients: Clients, env: str, resolved: Resolved) -> Check:
    def run():
        resolved.api_base_url = live_mod.api_base_url(clients["apigateway"], env)
        resolved.state_machine_arn = live_mod.state_machine_arn(clients["stepfunctions"], env)
        resolved.bucket = live_mod.workarea_bucket(clients["s3"], env)
        resolved.conveyor_url = live_mod.conveyor_queue_url(clients["sqs"], env)
        return "ok", f"API {resolved.api_base_url}; bucket {resolved.bucket}"
    return checks.guarded("live_resources", run)


def run_preflight(inp: Inputs, clients: Clients, *, environ: Mapping[str, str], config_path: Path,
                  sso_cache: Path, state_home: Path, now: datetime,
                  which: Callable[[str], str | None] = shutil.which,
                  loader: Callable[[str, str], live_mod.Deployed] | None = None,
                  token_fn: Callable[..., auth.Token] | None = None,
                  probe_factory: Callable[[Resolved, auth.Token], Callable[[], int]] | None = None,
                  agentcore: bool = False) -> PreflightResult:
    spec = envs.get_env(inp.env)
    out: list[Check] = []
    resolved = Resolved()
    fields_by_claim: dict[str, dict] = {}

    out.append(checks.check_profile_not_sensitive(inp.profile))
    if out[-1].status == "FAILED":
        return PreflightResult(Report(out), resolved, fields_by_claim)
    out.append(checks.check_profile_in_config(inp.profile, config_path))
    if out[-1].status == "FAILED":
        return PreflightResult(Report(out), resolved, fields_by_claim)

    out.append(checks.check_aws_identity(clients["sts"], spec))
    out.append(checks.check_sso_remaining(inp.profile, config_path, sso_cache, now))

    load = loader or live_mod.appconfig_loader(clients["appconfig"], inp.env)
    check, resolved.live = checks.check_appconfig_live(lambda: live_mod.gather_live_paths(load))
    out.append(check)
    out.append(checks.check_ingest_mapping(resolved.live))
    out.append(checks.check_dispatch_flag(clients["appconfig"], resolved.live, inp.allow_open_dispatch,
                                          len(inp.claims)))
    out.append(checks.check_runtime_qualifier(
        resolved.live, clients.lazy("bedrock-agentcore-control") if agentcore else None, inp.env))
    out.append(checks.check_dispatch_strategy(clients["appconfig"]))
    out.append(checks.check_foreign_breadcrumb(inp.env, state_home))

    out.append(_resolve_resources(clients, inp.env, resolved))
    if resolved.state_machine_arn:
        out.append(checks.check_running_executions(clients["stepfunctions"], resolved.state_machine_arn))
    if resolved.conveyor_url:
        check, resolved.conveyor_depth = checks.check_conveyor_depth(clients["sqs"], resolved.conveyor_url)
        out.append(check)
    check, resolved.jump_host = checks.check_bastion_online(clients["ssm"], clients.lazy("ec2"), spec, which)
    out.append(check)
    out.append(checks.check_client_secret_present(spec, environ))
    check, token = checks.check_token_audience(spec, environ, token_fn or auth.get_token)
    out.append(check)

    probe = None
    if inp.probe_api and token is not None and probe_factory and resolved.api_base_url:
        probe = probe_factory(resolved, token)
    api_check = checks.check_api_probe(probe)
    if inp.probe_api and probe is None:
        api_check = Check("api_probe", "skipped",
                          "se pidió --probe-api pero falta token o API resuelta (token_audience)",
                          api_check.prevents)
    out.append(api_check)

    pattern, sources = None, {}
    if inp.source_index:
        sources = _source_checks(inp, clients, spec, resolved, out, fields_by_claim, now)
    elif inp.source_dir and inp.claims:
        pattern = _claim_checks(inp, clients, spec, resolved, out, fields_by_claim, now)
    return PreflightResult(Report(out), resolved, fields_by_claim, pattern, sources)


def _claim_checks(inp: Inputs, clients: Clients, spec: envs.EnvSpec, resolved: Resolved,
                  out: list[Check], fields_by_claim: dict[str, dict], now: datetime):
    src, names = Path(inp.source_dir), list(inp.claims)
    exists = checks.check_claims_exist(src, names)
    out.append(exists)
    if exists.status == "FAILED":
        names = [c for c in names if (src / c / claims.RAW_DIR).is_dir()]
    try:
        pattern = claims.build_name_pattern(inp.name_template, inp.name_regex)
    except claims.ClaimNameError as exc:
        out.append(Check("claim_id_parses", "FAILED", str(exc), checks.PREVENTS["claim_id_parses"]))
        return None
    out.append(checks.check_claim_id_parses(names, pattern))
    for c in names:
        try:
            fields_by_claim[c] = claims.parse_folder(c, pattern)
        except claims.ClaimNameError:
            pass
    if not names:
        return pattern
    out.append(checks.check_prerequisite_globs(resolved.live, src, names))
    out.append(checks.check_large_pdfs(src, names))
    ids = {c: f["idReclamacion"] for c, f in fields_by_claim.items()}
    out.append(checks.check_tracker_duplicates(clients["dynamodb"] if spec.name != "dev"
                                               else None, spec, ids, now))
    out.append(checks.check_request_json_override(src, names, inp.request, fields_by_claim))
    out.append(checks.check_request_deliverable(_dir_bodies(inp, src, names, fields_by_claim, now),
                                                inp.skip_delivery, inp.request))
    out.append(checks.check_invoice_details(src, names, inp.invoice))
    out.append(_structuring_check(inp, clients, resolved, src, names, fields_by_claim))
    out.append(checks.check_count_throttle(len(names)))
    reuse = inp.structuring != "none"
    out.append(checks.check_batch_gate_estimate(
        len(names), resolved.conveyor_depth,
        resolved.live.min_records_per_job if resolved.live else live_mod.DEFAULT_MIN_RECORDS_PER_JOB,
        reuse))
    return pattern


def _structuring_check(inp, clients, resolved, src, names, fields_by_claim) -> Check:
    if resolved.live is None:
        return Check("structuring_source", "skipped", "depende de appconfig_live",
                     checks.PREVENTS["structuring_source"])
    with tempfile.TemporaryDirectory(prefix="iae-preflight-") as tmp:
        def plan_fn(claim: str):
            decision = structuring.parse_decision(inp.structuring, src / claim)
            if decision.kind == "workarea" and len(names) > 1:
                raise structuring.StructuringError("workarea:<pid> solo vale para un claim")
            needs_s3 = decision.kind in ("workarea", "mai")
            return structuring.plan_structuring(
                decision, claim, fields_by_claim.get(claim, {}), resolved.live, inp.run_id, Path(tmp),
                s3=clients["s3"] if needs_s3 else None, env=inp.env, bucket=resolved.bucket or "")
        return checks.check_structuring_source(names, plan_fn)


def _source_checks(inp: Inputs, clients: Clients, spec: envs.EnvSpec, resolved: Resolved,
                   out: list[Check], fields_by_claim: dict[str, dict], now: datetime) -> dict:
    def fail(msg: str) -> dict:
        out.append(Check("claims_exist", "FAILED", msg, checks.PREVENTS["claims_exist"]))
        return {}
    if resolved.live is None or not resolved.bucket:
        return fail("depende de appconfig_live y live_resources")
    try:
        rows = sourceindex.read_index(Path(inp.source_index), resolved.bucket, resolved.live.base_prefix,
                                      only=inp.claims or None)
    except (sourceindex.SourceIndexError, OSError) as exc:
        return fail(str(exc))
    sources, errors = {}, {}
    for row in rows:
        try:
            sources[row.radicado] = sourceindex.load_source(
                clients["s3"], resolved.bucket, resolved.live, row, want_invoice=inp.invoice == "source",
                ddb=clients["dynamodb"] if inp.request == "source" else None, env=spec.name,
                request_mode=inp.request, require_deliverable=not inp.skip_delivery)
        except (sourceindex.SourceIndexError, ClientError, ValueError) as exc:
            errors[row.radicado] = f"{type(exc).__name__}: {exc}"
    out.append(checks.check_source_claims_exist(sources, errors))
    out.append(checks.check_source_ids(sources))
    for rad, sc in sources.items():
        rid = sc.request_body.get("idReclamacion")
        if isinstance(rid, int):
            fields_by_claim[rad] = {"idReclamacion": rid}
    out.append(checks.check_source_prerequisites(resolved.live, sources))
    out.append(checks.check_large_pdf_sizes({c: sc.raw for c, sc in sources.items()}))
    out.append(checks.check_tracker_duplicates(clients["dynamodb"] if spec.name != "dev" else None, spec,
                                               {c: f["idReclamacion"] for c, f in fields_by_claim.items()}, now))
    out.append(checks.check_source_request_skipped())
    out.append(checks.check_request_deliverable({c: sc.request_body for c, sc in sources.items()},
                                                inp.skip_delivery, inp.request))
    out.append(checks.check_source_invoice(sources, inp.invoice))
    out.append(checks.check_invoice_matches_ser(sources, inp.invoice))
    out.append(checks.check_source_structuring(sources, inp.structuring))
    out.append(checks.check_count_throttle(len(rows)))
    out.append(checks.check_batch_gate_estimate(
        len(rows), resolved.conveyor_depth, resolved.live.min_records_per_job, inp.structuring != "none"))
    return sources


def _dir_bodies(inp: Inputs, src: Path, names: list[str], fields_by_claim: dict, now: datetime) -> dict[str, dict]:
    """Request que se usaría en modo carpeta: el del archivo local o el derivado del nombre."""
    bodies: dict[str, dict] = {}
    for c in names:
        local = src / c / claims.RAW_DIR / "request.json"
        if inp.request == "local" and local.is_file():
            try:
                bodies[c] = json.loads(local.read_text(encoding="utf-8"))
            except ValueError:
                bodies[c] = {}
        elif c in fields_by_claim:
            bodies[c] = request_mod.build_iniciar_body(fields_by_claim[c], c, now.date().isoformat(),
                                                        inp.env)
    return bodies

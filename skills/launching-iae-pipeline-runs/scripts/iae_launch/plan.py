"""plan.json: lo que launch.py ejecutará, sellado con un plan_id (hash canónico)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import claims as claims_mod
from . import dispatch, envs, invoice, request, seed, sourceindex, structuring
from .runner import Inputs, PreflightResult
from .seed import SeedItem, content_type_for

SCRIPTS_DIR = Path(__file__).resolve().parent.parent


class PlanError(RuntimeError):
    pass


def compute_plan_id(plan: dict) -> str:
    body = {k: v for k, v in plan.items() if k != "plan_id"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()[:12]


def _item_dict(item: SeedItem) -> dict:
    d = asdict(item)
    if item.kind == "put":
        d["size"] = Path(item.source).stat().st_size
    return d


def _claim_items(inp: Inputs, folder: str, claim_dir: Path, lp, derived: Path) -> list[SeedItem]:
    raw = claim_dir / claims_mod.RAW_DIR
    items: list[SeedItem] = []
    for name in claims_mod.raw_files(claim_dir):
        if name == invoice.FILENAME:
            continue  # va por la decisión de invoice
        if name == "request.json" and inp.request == "api":
            continue  # el API lo genera; sembrarlo lo pisaría
        items.append(SeedItem("put", str(raw / name), f"{lp.intake}{name}", content_type_for(name)))
    if inp.invoice == "lambda":
        return items  # la Lambda fetch-claim-invoice-details lo genera (SIA)
    inv = invoice.resolve_invoice(claim_dir, inp.invoice)
    if inp.invoice == "local":
        inv_src = raw / invoice.FILENAME
    else:
        inv_src = derived / folder / invoice.FILENAME
        inv_src.parent.mkdir(parents=True, exist_ok=True)
        inv_src.write_text(json.dumps(inv.details, ensure_ascii=False, indent=2), encoding="utf-8")
    items.append(SeedItem("put", str(inv_src), f"{lp.invoice_output}{invoice.FILENAME}",
                          "application/json"))
    return items


def _dir_claims(inp, result, lp, res, derived, run_id, skip_delivery, now, s3, src) -> list[dict]:
    plan_claims = []
    for folder in inp.claims:
        fields = result.fields_by_claim[folder]
        body = request.build_iniciar_body(fields, folder, today=now.date().isoformat(), env=inp.env,
                                          skip_delivery=skip_delivery)
        errors = request.validate_body(body)
        if errors:
            raise PlanError(f"{folder}: cuerpo inválido: {'; '.join(errors)}")
        items = _claim_items(inp, folder, src / folder, lp, derived)
        decision = structuring.parse_decision(inp.structuring, src / folder)
        items += structuring.plan_structuring(decision, folder, fields, lp, run_id, derived, s3=s3,
                                              env=inp.env, bucket=res.bucket or "").items
        _assert_unique(folder, [i.dest_suffix for i in items])
        plan_claims.append({"folder": folder, "body": body,
                            "seed_items": [_item_dict(i) for i in items]})
    return plan_claims


def _assert_unique(folder: str, dests: list[str]) -> None:
    dupes = sorted({d for d in dests if dests.count(d) > 1})
    if dupes:
        raise PlanError(f"{folder}: destinos duplicados en la siembra: {', '.join(dupes)}")


def _source_claims(inp, result, lp, res, derived, run_id, skip_delivery) -> list[dict]:
    """Todo es copia server-side desde el pid previo; el body del POST es el request original exacto."""
    if skip_delivery and inp.env != "test":
        raise ValueError("skipDelivery solo en test (el servidor lo rechaza en otros ambientes)")
    plan_claims = []
    for folder, sc in result.sources.items():
        body = dict(sc.request_body)
        if skip_delivery:
            body["skipDelivery"] = True
        errors = request.validate_body(body)
        if errors:
            raise PlanError(f"{folder}: cuerpo inválido: {'; '.join(errors)}")
        base = f"s3://{sc.row.bucket}/{sc.row.prefix}"
        special = {sourceindex.REQUEST_NAME, sourceindex.INVOICE_NAME}
        entries: list[tuple[str, str, int]] = []  # (origen relativo al pid del índice, destino, tamaño)
        entries += [(f"{lp.intake}{n}", f"{lp.intake}{n}", sz) for n, sz in sc.raw if n not in special]
        req_pid = sc.request_pid or sc.row.pid  # puede ser OTRO pid (el request original, no el fabricado)
        req_src = f"s3://{sc.row.bucket}/{sc.row.prefix.rsplit(sc.row.pid, 1)[0]}{req_pid}/"
        request_entry = (req_src + f"{lp.intake}{sourceindex.REQUEST_NAME}",
                         f"{lp.intake}{sourceindex.REQUEST_NAME}", len(sc.request_bytes))
        if inp.invoice == "source":
            size = dict(sc.raw)[sourceindex.INVOICE_NAME]
            entries.append((f"{lp.intake}{sourceindex.INVOICE_NAME}",
                            f"{lp.invoice_output}{sourceindex.INVOICE_NAME}", size))
        items: list[dict] = []
        if inp.structuring == "workarea":
            entries += [(f"{lp.structured}{n}", f"{lp.structured}{n}", sz) for n, sz in sc.artifacts]
            if sc.consolidated:
                entries.append((f"{lp.consolidated}consolidated.json", f"{lp.consolidated}consolidated.json", 0))
            else:
                marker = structuring.build_consolidated_marker(
                    [n for n, _ in sc.artifacts], f"workarea:{sc.row.pid}",
                    f"{structuring.GENERATED_BY}-{run_id}")
                item = structuring._write_marker(derived, folder, marker, lp.consolidated)
                items.append(_item_dict(item))
        entries = [(base + rel, dest, size) for rel, dest, size in entries] + [request_entry]
        for src_uri, dest, size in entries:
            try:
                seed.check_copy_size(src_uri, size)
            except ValueError as exc:
                raise PlanError(f"{folder}: {exc}") from None
            items.append({"kind": "copy", "source": src_uri, "dest_suffix": dest,
                          "content_type": "", "size": size})
        _assert_unique(folder, [i["dest_suffix"] for i in items])
        plan_claims.append({"folder": folder, "body": body, "source_pid": sc.row.pid,
                            "request_source_pid": req_pid, "source_uri": base, "seed_items": items})
    return plan_claims


def build_plan(inp: Inputs, result: PreflightResult, *, run_id: str, out_dir: Path, now: datetime,
               closed_by_marker: bool, skip_delivery: bool = False, s3=None) -> dict:
    spec = envs.get_env(inp.env)
    res, lp = result.resolved, result.resolved.live
    derived = Path(out_dir) / run_id / "derived"
    src = Path(inp.source_dir) if inp.source_dir else None
    if inp.source_index:
        plan_claims = _source_claims(inp, result, lp, res, derived, run_id, skip_delivery)
    else:
        plan_claims = _dir_claims(inp, result, lp, res, derived, run_id, skip_delivery, now, s3, src)
    was_enabled = dispatch.read_enabled(lp.dispatch)
    plan = {
        "env": inp.env, "profile": inp.profile, "account_id": spec.account_id, "run_id": run_id,
        "created_at": now.isoformat(),
        "live": {"paths": lp.to_plan_dict(), "versions": lp.versions,
                 "api_base_url": res.api_base_url, "state_machine_arn": res.state_machine_arn,
                 "workarea_bucket": res.bucket, "base_prefix": lp.base_prefix},
        "decisions": {"structuring": inp.structuring, "request": inp.request, "invoice": inp.invoice,
                      "skip_delivery": skip_delivery, "allow_open_dispatch": inp.allow_open_dispatch,
                      "name_template": inp.name_template, "name_regex": inp.name_regex,
                      "source_index": str(inp.source_index) if inp.source_index else None,
                      "source_dir": str(Path(inp.source_dir).resolve()) if inp.source_dir else None},
        "claims": plan_claims,
        "dispatch": {"was_enabled": was_enabled, "closed_by_marker": closed_by_marker,
                     "restore_to": dispatch.compute_restore_to(was_enabled, closed_by_marker,
                                                               inp.allow_open_dispatch),
                     "max_messages_per_cycle": lp.dispatch.content.get("values", {}).get(
                         "dispatch", {}).get("maxMessagesPerCycle")},
    }
    plan["plan_id"] = compute_plan_id(plan)
    return plan


def write_plan(plan: dict, out_dir: Path) -> Path:
    path = Path(out_dir) / plan["run_id"] / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_plan(path: Path) -> dict:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if compute_plan_id(plan) != plan.get("plan_id"):
        raise PlanError("el plan_id no coincide con el contenido de plan.json (¿editado a mano?)")
    return plan


def launch_command(env: str, plan_path: Path, plan_id: str) -> list[str]:
    argv = ["uv", "run", "--project", str(SCRIPTS_DIR), str(SCRIPTS_DIR / "launch.py"),
            "--env", env, "--plan", str(Path(plan_path).resolve()), "--execute", "--plan-id", plan_id]
    return envs.asm_exec_command(envs.get_env(env), argv)


def summarize(plan: dict, command: list[str]) -> str:
    lines = [f"plan {plan['plan_id']}  env={plan['env']}  run_id={plan['run_id']}",
             f"claims ({len(plan['claims'])}):"]
    for c in plan["claims"]:
        origin = f", request de {c['request_source_pid']}" if c.get("request_source_pid") else ""
        lines.append(f"  - {c['folder']}: {len(c['seed_items'])} objetos a sembrar{origin}")
    d = plan["dispatch"]
    lines += [f"dispatch: estaba {'abierto' if d['was_enabled'] else 'cerrado'}; "
              f"se restaurará a {'abierto' if d['restore_to'] else 'cerrado'}",
              "Para lanzar (único comando que escribe en AWS):", "  " + " ".join(command)]
    return "\n".join(lines)

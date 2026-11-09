"""Modo --source-index: checks, plan, y decisión invoice=lambda."""
import json
from datetime import datetime, timezone

import pytest

from iae_launch import checks, claims, runner
from iae_launch import plan as plan_mod
from iae_launch import sourceindex as si
from iae_launch.live import Deployed, LivePaths

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
BUCKET = "adr-test-medicalaudit-workarea"
PID = "11111111-1111-4111-8111-111111111111"
REQ = {"idReclamacion": 5, "idSolicitud": 5, "fechaRadicacion": "2026-01-01",
       "soportes": {"rutaArchivosObligatorios": "a", "rutaArchivosSoportes": "b"}}
INV = {"detalles": [{"codigo_cups": "890201"}]}


def live(rules=()):
    d = Deployed("a", "e", "p", 1, 1, {"values": {"dispatch": {"enabled": True}}})
    return LivePaths("audit-processes", "raw/", "staging/s/", "staging/c/", "raw/", {}, "q", list(rules), 100, d,
                     versions={"x": 1})


def source(*, consolidated=True, invoice=INV, ser=("890201",), raw_extra=(), artifacts=(("FAC_x.json", 3),),
           req=REQ):
    row = si.IndexRow("0001_5", PID, BUCKET, f"audit-processes/{PID}/")
    raw = [("FAC_1.pdf", 10), (".ingestion-meta.json", 2), ("request.json", 4), ("claim_invoice_details.json", 5),
           ("SER_1.json", 7), *raw_extra]
    return si.SourceClaim(row, raw, list(artifacts), consolidated, json.dumps(req).encode(), req, invoice,
                          set(ser))


# ---- checks -----------------------------------------------------------------------------
def test_source_claims_exist():
    assert checks.check_source_claims_exist({"a": source()}, {}).status == "ok"
    c = checks.check_source_claims_exist({}, {"a": "sin request.json"})
    assert c.status == "FAILED" and "a" in c.detail and "sin request.json" in c.detail


def test_source_ids_validated_with_schema():
    assert checks.check_source_ids({"a": source()}).status == "ok"
    bad = dict(REQ, idReclamacion="x")
    c = checks.check_source_ids({"a": source(req=bad)})
    assert c.status == "FAILED" and "idReclamacion" in c.detail


def test_source_prereq_and_large_pdfs():
    rules = [{"id": "fac", "type": "document_exists", "glob": "FAC_*.pdf", "expect": "present"}]
    assert checks.check_source_prerequisites(live(rules), {"a": source()}).status == "ok"
    s = source()
    s.raw = [("FACT_1.pdf", 1)]
    assert checks.check_source_prerequisites(live(rules), {"a": s}).status == "FAILED"
    big = source(raw_extra=[("big.pdf", 30 * 1024 * 1024)])
    c = checks.check_large_pdf_sizes({"a": big.raw})
    assert c.status == "warn" and "big.pdf" in c.detail
    assert checks.check_large_pdf_sizes({"a": source().raw}).status == "ok"


def test_source_request_check_is_skipped():
    c = checks.check_source_request_skipped()
    assert c.name == "request_json_override" and c.status == "skipped" and "request de origen" in c.detail


def test_source_invoice_modes():
    assert checks.check_source_invoice({"a": source()}, "lambda").status == "ok"
    assert "Lambda" in checks.check_source_invoice({"a": source()}, "lambda").detail
    assert checks.check_source_invoice({"a": source()}, "source").status == "ok"
    assert checks.check_source_invoice({"a": source(invoice={"detalles": []})}, "source").status == "FAILED"


def test_invoice_matches_ser():
    assert checks.check_invoice_matches_ser({"a": source()}, "source").status == "ok"
    c = checks.check_invoice_matches_ser({"a": source(ser=("111",))}, "source")
    assert c.status == "FAILED" and "111" in c.detail and c.name == "invoice_matches_ser"
    assert checks.check_invoice_matches_ser({"a": source()}, "lambda").status == "skipped"


def test_source_structuring():
    assert checks.check_source_structuring({"a": source()}, "workarea").status == "ok"
    c = checks.check_source_structuring({"a": source(consolidated=False)}, "workarea")
    assert c.status == "warn" and "lifecycle" in c.detail
    c = checks.check_source_structuring({"a": source(artifacts=())}, "workarea")
    assert c.status == "FAILED"
    assert checks.check_source_structuring({"a": source(artifacts=())}, "none").status == "ok"


def test_dir_mode_invoice_lambda_warns(tmp_path):
    c = checks.check_invoice_details(tmp_path, ["x"], "lambda")
    assert c.status == "warn" and "SER ausente" in c.detail


# ---- validate_inputs -----------------------------------------------------------------------
def test_validate_inputs():
    ok = runner.Inputs(env="test", profile="p", source_index="x.csv", structuring="workarea", request="source",
                       invoice="lambda")
    runner.validate_inputs(ok)
    for bad in (dict(source_dir="d"), dict(structuring="none", request="api"), dict(invoice="local"),
                dict(structuring="local")):
        inp = runner.Inputs(env="test", profile="p", source_index="x.csv", structuring="workarea",
                            request="source", invoice="source")
        for k, v in bad.items():
            setattr(inp, k, v)
        with pytest.raises(ValueError):
            runner.validate_inputs(inp)
    with pytest.raises(ValueError, match="source"):
        runner.validate_inputs(runner.Inputs(env="test", profile="p", source_dir="d", claims=["a"],
                                             request="source"))
    with pytest.raises(ValueError, match="workarea"):
        runner.validate_inputs(runner.Inputs(env="test", profile="p", source_dir="d", claims=["a"],
                                             structuring="workarea"))
    runner.validate_inputs(runner.Inputs(env="test", profile="p", source_dir="d", claims=["a"], invoice="lambda"))


# ---- plan --------------------------------------------------------------------------------
def result(sources, env="test"):
    res = runner.Resolved(live(), "https://x.execute-api.us-east-1.amazonaws.com/v1", "arn:sm", BUCKET, "q", 0)
    r = runner.PreflightResult(None, res, {k: {"idReclamacion": 5} for k in sources})
    r.sources = sources
    return r


def index_inputs(**kw):
    base = dict(env="test", profile="ADR-TEST-MEDICALAUDIT", source_index="x.csv", claims=["0001_5"],
                structuring="workarea", request="source", invoice="lambda")
    base.update(kw)
    return runner.Inputs(**base)


def build(tmp_path, sources=None, **kw):
    inp = index_inputs(**kw.pop("inp", {}))
    return plan_mod.build_plan(inp, result(sources or {"0001_5": source()}), run_id="skill-1",
                               out_dir=tmp_path, now=NOW, closed_by_marker=False, **kw)


def items_of(p):
    return {i["dest_suffix"]: i for i in p["claims"][0]["seed_items"]}


def test_plan_source_all_copies_and_exact_body(tmp_path):
    p = build(tmp_path)
    claim = p["claims"][0]
    assert claim["body"] == REQ                       # exacto, sin reconstruir
    assert claim["source_pid"] == PID and claim["source_uri"] == f"s3://{BUCKET}/audit-processes/{PID}/"
    items = items_of(p)
    assert all(i["kind"] == "copy" and i["content_type"] == "" for i in items.values())
    assert set(items) == {"raw/FAC_1.pdf", "raw/.ingestion-meta.json", "raw/SER_1.json", "raw/request.json",
                          "staging/s/FAC_x.json", "staging/c/consolidated.json"}
    assert items["raw/request.json"]["source"] == f"s3://{BUCKET}/audit-processes/{PID}/raw/request.json"
    assert items["raw/FAC_1.pdf"]["size"] == 10
    assert "raw/claim_invoice_details.json" not in items   # invoice=lambda
    assert p["decisions"]["invoice"] == "lambda"


def test_plan_invoice_source_copies_invoice(tmp_path):
    p = build(tmp_path, inp={"invoice": "source"})
    assert items_of(p)["raw/claim_invoice_details.json"]["source"].endswith("raw/claim_invoice_details.json")


def test_plan_missing_consolidated_generates_marker(tmp_path):
    p = build(tmp_path, sources={"0001_5": source(consolidated=False)})
    marker = items_of(p)["staging/c/consolidated.json"]
    assert marker["kind"] == "put"
    doc = json.loads(open(marker["source"]).read())
    assert doc["documents"]["FAC"]["artifact"] == "FAC_x.json" and doc["generated_by"]


def test_plan_structuring_none_has_no_artifacts(tmp_path):
    p = build(tmp_path, inp={"structuring": "none"})
    assert not any(k.startswith("staging/") for k in items_of(p))


def test_plan_rejects_oversized_copy(tmp_path):
    big = source(raw_extra=[("huge.pdf", 6 * 1024 ** 3)])
    with pytest.raises(plan_mod.PlanError, match="5 GB"):
        build(tmp_path, sources={"0001_5": big})


def test_plan_skip_delivery_only_test(tmp_path):
    p = build(tmp_path, skip_delivery=True)
    assert p["claims"][0]["body"]["skipDelivery"] is True
    with pytest.raises(ValueError, match="solo en test"):
        plan_mod.build_plan(index_inputs(env="dev"), result({"0001_5": source()}), run_id="r", out_dir=tmp_path,
                            now=NOW, closed_by_marker=False, skip_delivery=True)


def test_plan_invalid_source_request_rejected(tmp_path):
    with pytest.raises(plan_mod.PlanError, match="idReclamacion"):
        build(tmp_path, sources={"0001_5": source(req=dict(REQ, idReclamacion="x"))})


def test_plan_records_max_messages_and_valid_hash(tmp_path):
    d = Deployed("a", "e", "p", 1, 1, {"values": {"dispatch": {"enabled": True, "maxMessagesPerCycle": 10}}})
    r = result({"0001_5": source()})
    r.resolved.live = LivePaths("audit-processes", "raw/", "staging/s/", "staging/c/", "raw/", {}, "q", [], 100, d,
                                versions={"x": 1})
    p = plan_mod.build_plan(index_inputs(), r, run_id="r", out_dir=tmp_path, now=NOW, closed_by_marker=False)
    assert p["dispatch"]["max_messages_per_cycle"] == 10 and plan_mod.compute_plan_id(p) == p["plan_id"]


def test_dir_mode_plan_invoice_lambda_skips_invoice(tmp_path):
    src = tmp_path / "src"
    raw = src / "1_100" / claims.RAW_DIR
    raw.mkdir(parents=True)
    (raw / "FAC_1.pdf").write_text("x")
    (raw / "claim_invoice_details.json").write_text(json.dumps(INV))
    inp = runner.Inputs(env="test", profile="ADR-TEST-MEDICALAUDIT", source_dir=src, claims=["1_100"],
                        invoice="lambda")
    res = result({})
    res.fields_by_claim = {"1_100": {"idReclamacion": 100, "idSolicitud": 100}}
    p = plan_mod.build_plan(inp, res, run_id="r", out_dir=tmp_path / "o", now=NOW, closed_by_marker=False)
    assert "raw/claim_invoice_details.json" not in items_of(p)


# ---- R2: request_deliverable --------------------------------------------------------------
GOOD = {"nitEntidad": "890981726", "soportes": {"rutaArchivosSoportes": "https://h.example.com/o/890981726/1072/a/"}}
BAD = {"nitEntidad": None, "soportes": {"rutaArchivosSoportes": "0001_5/soportes"}}


def test_request_deliverable_ok_failed_and_skip():
    assert checks.check_request_deliverable({"a": GOOD}, False, "source").status == "ok"
    c = checks.check_request_deliverable({"a": BAD}, False, "source")
    assert c.status == "FAILED" and "422" in c.detail and "nitEntidad" in c.detail and "idPaquete" in c.detail
    c = checks.check_request_deliverable({"a": BAD}, True, "source")
    assert c.status == "warn" and "no habrá entrega a SIA" in c.detail


def test_request_deliverable_api_mode_says_it_always_fails():
    c = checks.check_request_deliverable({"a": BAD}, False, "api")
    assert c.status == "FAILED" and "SIEMPRE falla" in c.detail and "--request source" in c.detail \
        and "--skip-delivery" in c.detail


def test_validate_inputs_request_source_pid():
    ok = runner.Inputs(env="test", profile="p", source_index="x.csv", structuring="workarea",
                       request=f"source:{PID}", invoice="lambda")
    runner.validate_inputs(ok)
    ok.request = "source:nope"
    with pytest.raises(ValueError, match="source"):
        runner.validate_inputs(ok)
    with pytest.raises(ValueError, match="source"):
        runner.validate_inputs(runner.Inputs(env="test", profile="p", source_dir="d", claims=["a"],
                                             request=f"source:{PID}"))


def test_plan_copies_request_from_the_chosen_pid(tmp_path):
    other = "22222222-2222-4222-8222-222222222222"
    sc = source()
    sc.request_pid = other
    sc.request_body = dict(REQ, nitEntidad="890981726")
    sc.request_bytes = json.dumps(sc.request_body).encode()
    p = build(tmp_path, sources={"0001_5": sc})
    item = items_of(p)["raw/request.json"]
    assert item["source"] == f"s3://{BUCKET}/audit-processes/{other}/raw/request.json"
    assert item["size"] == len(sc.request_bytes)
    assert p["claims"][0]["request_source_pid"] == other and p["claims"][0]["source_pid"] == PID
    assert p["claims"][0]["body"] == sc.request_body

import json
from datetime import datetime, timedelta, timezone

from iae_launch import checks, claims, envs, structuring
from iae_launch.live import Deployed, LivePaths

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
PAT = claims.build_name_pattern()


def mk(root, name, files=None):
    raw = root / name / claims.RAW_DIR
    raw.mkdir(parents=True)
    for fname, content in (files or {}).items():
        (raw / fname).write_text(content if isinstance(content, str) else json.dumps(content))
    return root / name


def test_claims_exist(tmp_path):
    mk(tmp_path, "1_100")
    (tmp_path / "2_200").mkdir()  # sin 000_
    assert checks.check_claims_exist(tmp_path, ["1_100"]).status == "ok"
    c = checks.check_claims_exist(tmp_path, ["1_100", "2_200", "3_300"])
    assert c.status == "FAILED" and "2_200" in c.detail and "3_300" in c.detail
    assert checks.check_claims_exist(tmp_path / "nope", ["x"]).status == "FAILED"


def test_claim_id_parses():
    assert checks.check_claim_id_parses(["1_100", "2_200"], PAT).status == "ok"
    c = checks.check_claim_id_parses(["1_100", "basura"], PAT)
    assert c.status == "FAILED" and "basura" in c.detail


def live_with(rules):
    return LivePaths("audit-processes", "raw/", "s/", "c/", "raw/", {}, "q", rules, 100,
                     Deployed("a", "e", "p", 1, 1, {}))


RULES = [{"id": "fac", "type": "document_exists", "glob": "FAC_*.pdf", "expect": "present"},
         {"id": "acc", "type": "json_jsonata", "glob": "FUR_*.json", "expression": "x"}]


def test_prerequisite_globs_ok_warn_failed(tmp_path):
    mk(tmp_path, "1_100", {"FAC_1.pdf": "x"})
    mk(tmp_path, "2_200", {"FACT_1.pdf": "x"})
    c = checks.check_prerequisite_globs(live_with(RULES), tmp_path, ["1_100"])
    assert c.status == "warn" and "no evaluada localmente" in c.detail
    c = checks.check_prerequisite_globs(live_with(RULES), tmp_path, ["1_100", "2_200"])
    assert c.status == "FAILED" and "2_200" in c.detail and "FAC_*.pdf" in c.detail
    assert checks.check_prerequisite_globs(live_with(RULES[:1]), tmp_path, ["1_100"]).status == "ok"
    assert checks.check_prerequisite_globs(None, tmp_path, ["1_100"]).status == "skipped"


def test_large_pdfs(tmp_path):
    c1 = mk(tmp_path, "1_100", {"a.pdf": "x"})
    mk(tmp_path, "2_200", {"b.pdf": "x"})
    (c1 / claims.RAW_DIR / "a.pdf").write_bytes(b"0" * 2000)
    assert checks.check_large_pdfs(tmp_path, ["2_200"], limit_bytes=1000).status == "ok"
    c = checks.check_large_pdfs(tmp_path, ["1_100", "2_200"], limit_bytes=1000)
    assert c.status == "warn" and "a.pdf" in c.detail


def test_count_throttle():
    assert checks.check_count_throttle(20).status == "ok"
    assert checks.check_count_throttle(21).status == "warn"


def test_batch_gate_estimate():
    assert checks.check_batch_gate_estimate(5, 0, 100, False).status == "warn"
    assert "padding-bedrock-batch-gate" in checks.check_batch_gate_estimate(5, 0, 100, False).detail
    assert checks.check_batch_gate_estimate(13, 0, 100, False).status == "ok"  # 104 >= 100
    assert checks.check_batch_gate_estimate(5, 80, 100, False).status == "ok"
    assert checks.check_batch_gate_estimate(1, 0, 100, True).status == "ok"
    assert checks.check_batch_gate_estimate(1, None, 100, False).status == "warn"


def test_invoice_details(tmp_path):
    mk(tmp_path, "1_100", {"claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    mk(tmp_path, "2_200", {"claim_invoice_details.json": {"detalles": []}})
    assert checks.check_invoice_details(tmp_path, ["1_100"], "local").status == "ok"
    c = checks.check_invoice_details(tmp_path, ["1_100", "2_200"], "local")
    assert c.status == "FAILED" and "2_200" in c.detail
    assert checks.check_invoice_details(tmp_path, ["1_100"], "ser").status == "FAILED"


def body_for(rid):
    return {"idReclamacion": rid, "idSolicitud": rid,
            "soportes": {"rutaArchivosObligatorios": "a", "rutaArchivosSoportes": "b"}}


def test_request_json_override(tmp_path):
    mk(tmp_path, "1_100", {"request.json": body_for(100)})
    mk(tmp_path, "2_200")
    fields = {"1_100": {"idReclamacion": 100}, "2_200": {"idReclamacion": 200}}
    c = checks.check_request_json_override(tmp_path, ["1_100", "2_200"], "api", fields)
    assert c.status == "warn" and "no se sembrará" in c.detail and "1_100" in c.detail
    assert checks.check_request_json_override(tmp_path, ["2_200"], "api", fields).status == "ok"
    assert checks.check_request_json_override(tmp_path, ["1_100"], "local", fields).status == "ok"
    c = checks.check_request_json_override(tmp_path, ["2_200"], "local", fields)
    assert c.status == "FAILED" and "request.json" in c.detail


def test_request_json_local_invalid_and_mismatch(tmp_path):
    mk(tmp_path, "1_100", {"request.json": {"idReclamacion": "x"}})
    mk(tmp_path, "2_200", {"request.json": body_for(999)})
    fields = {"1_100": {"idReclamacion": 100}, "2_200": {"idReclamacion": 200}}
    c = checks.check_request_json_override(tmp_path, ["1_100", "2_200"], "local", fields)
    assert c.status == "FAILED" and "1_100" in c.detail and "2_200" in c.detail


def test_structuring_source():
    plans = {"1_1": structuring.StructuringPlan([], 3, "local:/x")}

    def plan_fn(claim):
        if claim == "bad":
            raise structuring.StructuringError("vacío")
        return plans["1_1"]
    assert checks.check_structuring_source(["1_1"], plan_fn).status == "ok"
    assert checks.check_structuring_source(["1_1", "bad"], plan_fn).status == "FAILED"


# ---- tracker duplicates -----------------------------------------------------------
def tracker_item(status, received, pid="p"):
    return {"process_id": {"S": pid}, "status": {"S": status},
            "events": {"L": [{"M": {"description": {"S": "received"},
                                    "timestamp": {"S": received.isoformat()}}}]}}


def q_params(claim_id):
    since = (NOW - timedelta(hours=48)).strftime("%Y-%m-%d")
    return dict(TableName="adr-test-medicalaudit-tracker-data", IndexName="claim_id_created_date_index",
                KeyConditionExpression="claim_id = :c AND created_date >= :d",
                ExpressionAttributeValues={":c": {"S": claim_id}, ":d": {"S": since}},
                ProjectionExpression="process_id, #s, created_at, events",
                ExpressionAttributeNames={"#s": "status"})


def test_tracker_dev_is_skipped(stubbed):
    c = checks.check_tracker_duplicates(stubbed("dynamodb").client, envs.get_env("dev"),
                                        {"1_100": 100}, NOW)
    assert c.status == "skipped" and "dev" in c.detail


def test_tracker_ok_when_terminal_or_old(stubbed):
    ddb = stubbed("dynamodb")
    ddb.ok("query", {"Items": [tracker_item("SF_SUCCEEDED", NOW - timedelta(hours=1))]}, **q_params("100"))
    ddb.ok("query", {"Items": [tracker_item("SF_RUNNING", NOW - timedelta(hours=60))]}, **q_params("200"))
    ddb.ok("query", {"Items": []}, **q_params("300"))
    c = checks.check_tracker_duplicates(ddb.client, envs.get_env("test"),
                                        {"a": 100, "b": 200, "c": 300}, NOW)
    assert c.status == "ok"


def test_tracker_newest_non_terminal_fails(stubbed):
    ddb = stubbed("dynamodb")
    ddb.ok("query", {"Items": [tracker_item("SF_SUCCEEDED", NOW - timedelta(hours=10), "old"),
                               tracker_item("SF_RUNNING", NOW - timedelta(hours=1), "new")]},
           **q_params("100"))
    c = checks.check_tracker_duplicates(ddb.client, envs.get_env("test"), {"a": 100}, NOW)
    assert c.status == "FAILED" and "new" in c.detail and "SF_RUNNING" in c.detail


def test_tracker_paginates(stubbed):
    ddb = stubbed("dynamodb")
    ddb.ok("query", {"Items": [], "LastEvaluatedKey": {"process_id": {"S": "z"}}}, **q_params("100"))
    ddb.ok("query", {"Items": [tracker_item("SF_RUNNING", NOW - timedelta(hours=1))]},
           ExclusiveStartKey={"process_id": {"S": "z"}}, **q_params("100"))
    assert checks.check_tracker_duplicates(ddb.client, envs.get_env("test"), {"a": 100},
                                           NOW).status == "FAILED"

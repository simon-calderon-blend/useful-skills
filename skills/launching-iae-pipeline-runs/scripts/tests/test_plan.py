import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from iae_launch import claims, plan, runner
from iae_launch.live import Deployed, LivePaths

NOW = datetime(2026, 11, 9, 12, 0, 5, tzinfo=timezone.utc)


def live():
    d = Deployed("a", "e", "p", 9, 1, {"values": {"dispatch": {"enabled": False}}})
    return LivePaths("audit-processes", "raw/", "staging/s/", "staging/c/", "raw/", {}, "v4_16_0", [], 100, d,
                     versions={"api/storage": 6})


def result(fields):
    r = runner.Resolved(live(), "https://x.execute-api.us-east-1.amazonaws.com/v1", "arn:sm", "bucket", "q", 0)
    return runner.PreflightResult(None, r, fields)


def make_claim(root, name, files):
    raw = root / name / claims.RAW_DIR
    raw.mkdir(parents=True)
    for f, content in files.items():
        (raw / f).write_text(content if isinstance(content, str) else json.dumps(content))
    return root / name


def inputs(src, claim_list, **kw):
    return runner.Inputs(env="test", profile="ADR-TEST-MEDICALAUDIT", source_dir=src, claims=claim_list, **kw)


FIELDS = {"1_100": {"idReclamacion": 100, "idSolicitud": 100, "numeroSolicitud": 100, "numeroRadicado": 100}}


def build(tmp_path, files=None, **kw):
    src = tmp_path / "src"
    make_claim(src, "1_100", files or {"FAC_1.pdf": "pdf", "FUR_1.json": "{}",
                                         "claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    return plan.build_plan(inputs(src, ["1_100"], **kw.pop("inp", {})), result(FIELDS),
                           run_id="skill-1", out_dir=tmp_path / "runs", now=NOW, closed_by_marker=True,
                           **kw), src


def test_plan_shape_and_id(tmp_path):
    p, _ = build(tmp_path)
    assert p["env"] == "test" and p["account_id"] == "276553701208" and p["run_id"] == "skill-1"
    assert p["live"]["workarea_bucket"] == "bucket" and p["live"]["versions"] == {"api/storage": 6}
    assert p["dispatch"] == {"was_enabled": False, "closed_by_marker": True, "restore_to": True,
                          "max_messages_per_cycle": None}
    assert len(p["plan_id"]) == 12
    assert plan.compute_plan_id(p) == p["plan_id"]


def test_seed_items_raw_flat_and_invoice(tmp_path):
    p, src = build(tmp_path)
    items = {i["dest_suffix"]: i for i in p["claims"][0]["seed_items"]}
    assert set(items) == {"raw/FAC_1.pdf", "raw/FUR_1.json", "raw/claim_invoice_details.json"}
    assert items["raw/FAC_1.pdf"]["content_type"] == "application/pdf"
    assert items["raw/FAC_1.pdf"]["source"] == str(src / "1_100" / claims.RAW_DIR / "FAC_1.pdf")
    assert items["raw/FAC_1.pdf"]["size"] == 3
    assert p["claims"][0]["body"]["idReclamacion"] == 100


def test_request_api_excludes_local_request_json_local_includes(tmp_path):
    files = {"FAC_1.pdf": "x", "request.json": {"idReclamacion": 100, "idSolicitud": 100,
                                                  "soportes": {"rutaArchivosObligatorios": "a",
                                                               "rutaArchivosSoportes": "b"}},
             "claim_invoice_details.json": {"detalles": [{"a": 1}]}}
    p, _ = build(tmp_path, files)
    assert "raw/request.json" not in {i["dest_suffix"] for i in p["claims"][0]["seed_items"]}
    p2, _ = build(tmp_path / "b", files, inp={"request": "local"})
    assert "raw/request.json" in {i["dest_suffix"] for i in p2["claims"][0]["seed_items"]}


def test_invoice_from_ser_is_derived_file(tmp_path):
    ser = [{"Datos_servicios_reclamacion": {"Servicios": [
        {"Codigo_del_servicio": "S", "Cantidad_de_servicios": 1, "Valor_unitario_facturado": 2}]}}]
    p, _ = build(tmp_path, {"SER_1.json": ser, "FAC_1.pdf": "x"}, inp={"invoice": "ser"})
    items = {i["dest_suffix"]: i for i in p["claims"][0]["seed_items"]}
    src = Path(items["raw/claim_invoice_details.json"]["source"])
    assert "derived" in src.parts and json.loads(src.read_text())["detalles"][0]["codigo_servicio"] == "S"
    assert "raw/SER_1.json" in items  # el SER crudo también viaja a raw/


def test_structuring_local_adds_items(tmp_path):
    s200 = tmp_path / "s200"
    s200.mkdir()
    (s200 / "083_FAC_x.json").write_text("{}")
    p, _ = build(tmp_path, inp={"structuring": f"local:{s200}"})
    dests = {i["dest_suffix"] for i in p["claims"][0]["seed_items"]}
    assert {"staging/s/FAC_x.json", "staging/c/consolidated.json"} <= dests
    assert p["decisions"]["structuring"] == f"local:{s200}"


def test_skip_delivery_only_test_env(tmp_path):
    p, _ = build(tmp_path, skip_delivery=True)
    assert p["claims"][0]["body"]["skipDelivery"] is True
    src = tmp_path / "src"
    with pytest.raises(ValueError, match="solo en test"):
        plan.build_plan(runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_dir=src,
                                      claims=["1_100"]), result(FIELDS), run_id="r",
                        out_dir=tmp_path / "runs2", now=NOW, closed_by_marker=False, skip_delivery=True)


def test_invalid_body_rejected(tmp_path):
    src = tmp_path / "src"
    make_claim(src, "1_100", {"FAC_1.pdf": "x", "claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    bad = {"1_100": {"idReclamacion": "x", "idSolicitud": 1}}
    with pytest.raises(plan.PlanError, match="idReclamacion"):
        plan.build_plan(inputs(src, ["1_100"]), result(bad), run_id="r", out_dir=tmp_path / "o", now=NOW,
                        closed_by_marker=False)


def test_restore_to_variants(tmp_path):
    src = tmp_path / "src"
    make_claim(src, "1_100", {"FAC_1.pdf": "x", "claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    kw = dict(run_id="r", out_dir=tmp_path / "o", now=NOW)
    p = plan.build_plan(inputs(src, ["1_100"]), result(FIELDS), closed_by_marker=False, **kw)
    assert p["dispatch"]["restore_to"] is False
    p = plan.build_plan(inputs(src, ["1_100"], allow_open_dispatch=True), result(FIELDS),
                        closed_by_marker=False, **kw)
    assert p["dispatch"]["restore_to"] is True


def test_write_and_load_verify(tmp_path):
    p, _ = build(tmp_path)
    path = plan.write_plan(p, tmp_path / "runs")
    assert path == tmp_path / "runs" / "skill-1" / "plan.json"
    loaded = plan.load_plan(path)
    assert loaded["plan_id"] == p["plan_id"]


def test_load_detects_tampering(tmp_path):
    p, _ = build(tmp_path)
    path = plan.write_plan(p, tmp_path / "runs")
    data = json.loads(path.read_text())
    data["claims"][0]["body"]["idReclamacion"] = 1
    path.write_text(json.dumps(data))
    with pytest.raises(plan.PlanError, match="plan_id"):
        plan.load_plan(path)


def test_launch_command_wraps_asm_exec(tmp_path):
    cmd = plan.launch_command("dev", tmp_path / "plan.json", "abc123def456")
    s = " ".join(cmd)
    assert "asm-exec" in s and "--execute" in s and "--plan-id abc123def456" in s
    assert "IAE_CLIENT_SECRET={{resolve:secretsmanager:adr-dev-medicalaudit-scriptconnection" in s


def test_summary_mentions_claims_and_command(tmp_path):
    p, _ = build(tmp_path)
    text = plan.summarize(p, ["echo", "x"])
    assert "1_100" in text and p["plan_id"] in text and "echo x" in text

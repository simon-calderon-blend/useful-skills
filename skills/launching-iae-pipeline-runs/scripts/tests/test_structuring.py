import json

import pytest

from iae_launch import structuring as st
from iae_launch.live import Deployed, LivePaths


def lp():
    d = Deployed("a", "e", "p", 1, 1, {})
    return LivePaths("audit-processes", "raw/", "staging/document-extraction/artifacts/",
                     "staging/document-extraction/consolidated/", "raw/", {}, "q", [], 100, d)


def test_normalize_strips_code_prefix():
    assert st.normalize_artifact_name("083_FAC_x.json") == "FAC_x.json"
    assert st.normalize_artifact_name("FAC_x.json") == "FAC_x.json"
    assert st.normalize_artifact_name("12_FAC.json") == "12_FAC.json"  # solo 3 dígitos


def test_normalize_set_rejects_collisions_non_json_and_hidden():
    out = st.normalize_artifacts(["083_FAC_x.json", ".hid.json", "notes.txt", "HEV_1.json"])
    assert out == {"FAC_x.json": "083_FAC_x.json", "HEV_1.json": "HEV_1.json"}
    with pytest.raises(st.StructuringError, match="colisión"):
        st.normalize_artifacts(["083_FAC_x.json", "FAC_x.json"])


def test_marker_shape():
    m = st.build_consolidated_marker(["FAC_x.json", "HEV_1.json", "HEV_2.json"],
                                     "local:/d", "launching-iae-pipeline-runs-20260101")
    assert m["run_id"] == "launching-iae-pipeline-runs-20260101"
    assert m["generated_by"] == "launching-iae-pipeline-runs"
    assert m["source"] == "local:/d"
    assert m["documents"]["FAC"] == {"artifact": "FAC_x.json", "artifacts": ["FAC_x.json"]}
    assert m["documents"]["HEV"]["artifacts"] == ["HEV_1.json", "HEV_2.json"]


def test_parse_decision(tmp_path):
    assert st.parse_decision("none", tmp_path / "c").kind == "none"
    d = st.parse_decision("local", tmp_path / "c")
    assert d.kind == "local" and d.ref == str(tmp_path / "c" / "200_soportes_estructurados")
    assert st.parse_decision("local:/x/y", tmp_path).ref == "/x/y"
    assert st.parse_decision("workarea:11111111-1111-4111-8111-111111111111", tmp_path).ref.startswith("1111")
    assert st.parse_decision("mai:run1", tmp_path).ref == "run1"
    with pytest.raises(st.StructuringError):
        st.parse_decision("weird", tmp_path)


def test_plan_none(tmp_path):
    p = st.plan_structuring(st.parse_decision("none", tmp_path), "1_1", {}, lp(), "r", tmp_path)
    assert p.items == [] and p.artifacts == 0


def test_plan_local(tmp_path):
    src = tmp_path / "200"
    src.mkdir()
    (src / "083_FAC_x.json").write_text("{}")
    (src / ".hid").write_text("x")
    dec = st.parse_decision(f"local:{src}", tmp_path)
    p = st.plan_structuring(dec, "1_1", {}, lp(), "run1", tmp_path / "derived")
    dests = {i.dest_suffix: i for i in p.items}
    assert set(dests) == {"staging/document-extraction/artifacts/FAC_x.json",
                          "staging/document-extraction/consolidated/consolidated.json"}
    assert dests["staging/document-extraction/artifacts/FAC_x.json"].kind == "put"
    marker = json.loads(open(dests["staging/document-extraction/consolidated/consolidated.json"].source).read())
    assert marker["documents"]["FAC"]["artifact"] == "FAC_x.json" and marker["run_id"].startswith(
        "launching-iae-pipeline-runs-")
    assert p.artifacts == 1


def test_plan_local_empty_is_error(tmp_path):
    (tmp_path / "200").mkdir()
    with pytest.raises(st.StructuringError, match="ningún artefacto"):
        st.plan_structuring(st.parse_decision(f"local:{tmp_path / '200'}", tmp_path), "1_1", {},
                            lp(), "r", tmp_path)


def test_plan_local_missing_dir(tmp_path):
    with pytest.raises(st.StructuringError, match="no existe"):
        st.plan_structuring(st.parse_decision("local:/nope/zzz", tmp_path), "1_1", {}, lp(), "r", tmp_path)


def listing(keys):
    return {"Contents": [{"Key": k, "Size": 1} for k in keys], "KeyCount": len(keys)}


def test_plan_mai(stubbed, tmp_path):
    s3 = stubbed("s3")
    pre = "runs/run9/1_1/200_soportes_estructurados/"
    s3.ok("list_objects_v2", listing([pre + "083_FAC_x.json", pre + "x.txt"]),
          Bucket="adr-medical-audit-executions-local-mai", Prefix=pre)
    p = st.plan_structuring(st.parse_decision("mai:run9", tmp_path), "1_1", {"idReclamacion": 1},
                            lp(), "r", tmp_path, s3=s3.client, env="dev", bucket="wb")
    copy = [i for i in p.items if i.kind == "copy"]
    assert [(c.source, c.dest_suffix) for c in copy] == [
        (f"s3://adr-medical-audit-executions-local-mai/{pre}083_FAC_x.json",
         "staging/document-extraction/artifacts/FAC_x.json")]
    assert any(i.dest_suffix.endswith("consolidated.json") and i.kind == "put" for i in p.items)


def test_mai_bucket_test_env(stubbed, tmp_path):
    s3 = stubbed("s3")
    pre = "runs/run9/1_1/200_soportes_estructurados/"
    s3.ok("list_objects_v2", listing([pre + "FAC_x.json"]),
          Bucket="adr-test-medical-audit-executions-local-mai", Prefix=pre)
    st.plan_structuring(st.parse_decision("mai:run9", tmp_path), "1_1", {}, lp(), "r", tmp_path,
                        s3=s3.client, env="test", bucket="wb")


def test_plan_workarea_copies_existing_consolidated(stubbed, tmp_path):
    s3 = stubbed("s3")
    base = "audit-processes/11111111-1111-4111-8111-111111111111/"
    s3.ok("get_object", {"Body": __import__("tests.conftest", fromlist=["stream"]).stream({"idReclamacion": 5})},
          Bucket="wb", Key=base + "raw/request.json")
    s3.ok("head_object", {}, Bucket="wb", Key=base + "staging/document-extraction/consolidated/consolidated.json")
    s3.ok("list_objects_v2", listing([base + "staging/document-extraction/artifacts/FAC_x.json"]),
          Bucket="wb", Prefix=base + "staging/document-extraction/artifacts/")
    p = st.plan_structuring(st.parse_decision("workarea:11111111-1111-4111-8111-111111111111", tmp_path), "1_5", {"idReclamacion": 5},
                            lp(), "r", tmp_path, s3=s3.client, env="dev", bucket="wb")
    kinds = {i.dest_suffix: i.kind for i in p.items}
    assert kinds["staging/document-extraction/consolidated/consolidated.json"] == "copy"


def test_plan_workarea_generates_marker_when_absent(stubbed, tmp_path):
    from tests.conftest import stream
    s3 = stubbed("s3")
    base = "audit-processes/11111111-1111-4111-8111-111111111111/"
    s3.ok("get_object", {"Body": stream({"idReclamacion": 5})}, Bucket="wb", Key=base + "raw/request.json")
    s3.err("head_object", "404", Bucket="wb",
           Key=base + "staging/document-extraction/consolidated/consolidated.json")
    s3.ok("list_objects_v2", listing([base + "staging/document-extraction/artifacts/FAC_x.json"]),
          Bucket="wb", Prefix=base + "staging/document-extraction/artifacts/")
    p = st.plan_structuring(st.parse_decision("workarea:11111111-1111-4111-8111-111111111111", tmp_path), "1_5", {"idReclamacion": 5},
                            lp(), "r", tmp_path, s3=s3.client, env="dev", bucket="wb")
    assert {i.dest_suffix: i.kind for i in p.items}[
        "staging/document-extraction/consolidated/consolidated.json"] == "put"


def test_plan_workarea_radicado_mismatch(stubbed, tmp_path):
    from tests.conftest import stream
    s3 = stubbed("s3")
    s3.ok("get_object", {"Body": stream({"idReclamacion": 99})}, Bucket="wb",
          Key="audit-processes/11111111-1111-4111-8111-111111111111/raw/request.json")
    with pytest.raises(st.StructuringError, match="radicado"):
        st.plan_structuring(st.parse_decision("workarea:11111111-1111-4111-8111-111111111111", tmp_path), "1_5", {"idReclamacion": 5},
                            lp(), "r", tmp_path, s3=s3.client, env="dev", bucket="wb")


@pytest.mark.parametrize("bad", ["workarea:abc", "workarea:", "mai:", "mai:../x", "mai:a/b", "mai:-x"])
def test_parse_decision_validates_refs(bad, tmp_path):
    with pytest.raises(st.StructuringError):
        st.parse_decision(bad, tmp_path)

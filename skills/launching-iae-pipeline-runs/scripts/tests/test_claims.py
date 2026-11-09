import pytest

from iae_launch import claims


def test_default_template_numero_fills_four_ids():
    pat = claims.build_name_pattern()
    f = claims.parse_folder("000001_19350541", pat)
    assert f["idReclamacion"] == f["idSolicitud"] == f["numeroSolicitud"] == f["numeroRadicado"] == 19350541
    assert all(isinstance(f[k], int) for k in ("idReclamacion", "idSolicitud"))


def test_no_hash_fallback_on_garbage_name():
    with pytest.raises(claims.ClaimNameError, match="no coincide"):
        claims.parse_folder("garbage", claims.build_name_pattern())


def test_non_numeric_ids_rejected():
    with pytest.raises(claims.ClaimNameError, match="entero"):
        claims.parse_folder("0001_abc", claims.build_name_pattern())


def test_template_with_explicit_ids_and_extras():
    pat = claims.build_name_pattern(template="<ignore>_<id_reclamacion>_<id_solicitud>_<nit_entidad>_<id_soporte>")
    f = claims.parse_folder("1_909_808_900123_55", pat)
    assert f["idReclamacion"] == 909 and f["idSolicitud"] == 808
    assert f["nitEntidad"] == "900123"
    assert f["soportes.idSoporte"] == 55


def test_missing_required_id_without_numero_fails():
    pat = claims.build_name_pattern(template="<ignore>_<id_reclamacion>")
    with pytest.raises(claims.ClaimNameError, match="idSolicitud"):
        claims.parse_folder("1_909", pat)


def test_id_reclamacion_only_template_falls_back_per_field_to_numero_if_present():
    pat = claims.build_name_pattern(template="<numero>_<numero_factura>")
    f = claims.parse_folder("55_FE99", pat)
    assert f["idSolicitud"] == 55 and f["numero_factura"] == "FE99"


def test_regex_named_groups():
    pat = claims.build_name_pattern(regex=r"^(?P<ignore>\d+)_(?P<id_reclamacion>\d+)-(?P<id_solicitud>\d+)$")
    f = claims.parse_folder("1_10-20", pat)
    assert (f["idReclamacion"], f["idSolicitud"]) == (10, 20)


def test_unknown_placeholder_ignored_not_crash():
    pat = claims.build_name_pattern(template="<numero>_<whatever>")
    assert claims.parse_folder("9_zzz", pat)["idReclamacion"] == 9


def test_list_claim_dirs_skips_hidden_and_files(tmp_path):
    (tmp_path / "a_1").mkdir()
    (tmp_path / ".hid").mkdir()
    (tmp_path / "f.txt").write_text("x")
    assert claims.list_claim_dirs(tmp_path) == ["a_1"]


def test_list_claim_dirs_missing_dir(tmp_path):
    with pytest.raises(claims.ClaimNameError, match="no existe"):
        claims.list_claim_dirs(tmp_path / "nope")


def make_claim(root, name, files=("FAC_1.pdf",)):
    d = root / name / claims.RAW_DIR
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_bytes(b"x")
    return root / name


def test_raw_files_excludes_hidden_and_subdirs(tmp_path):
    c = make_claim(tmp_path, "1_1", ("a.pdf", ".DS_Store"))
    (c / claims.RAW_DIR / "sub").mkdir()
    assert claims.raw_files(c) == ["a.pdf"]


RULES = [
    {"id": "fur", "type": "document_exists", "glob": "FUR_*.json", "expect": "present"},
    {"id": "clin", "type": "document_exists", "glob": ["HEV_*.pdf", "EPI_*.pdf"], "expect": "present"},
    {"id": "fac", "type": "document_exists", "glob": "FAC_*.pdf", "expect": "present"},
    {"id": "acc", "type": "json_jsonata", "glob": "FUR_*.json", "expression": "x"},
]


def test_prereq_ok_and_jsonata_warn():
    res = claims.evaluate_rules(RULES, ["FUR_1.json", "HEV_9.pdf", "FAC_1.pdf"])
    assert [(r.rule_id, r.status) for r in res] == [
        ("fur", "ok"), ("clin", "ok"), ("fac", "ok"), ("acc", "warn")]
    assert "no evaluada localmente" in res[-1].detail


def test_prereq_fails_with_fact_typo():
    res = claims.evaluate_rules(RULES, ["FUR_1.json", "HEV_9.pdf", "FACT_1.pdf"])
    bad = [r for r in res if r.status == "FAILED"]
    assert [r.rule_id for r in bad] == ["fac"]
    assert "FAC_*.pdf" in bad[0].detail


def test_prereq_expect_absent():
    rules = [{"id": "no", "type": "document_exists", "glob": "X_*", "expect": "absent"}]
    assert claims.evaluate_rules(rules, ["X_1"])[0].status == "FAILED"
    assert claims.evaluate_rules(rules, ["Y_1"])[0].status == "ok"


def test_large_pdfs(tmp_path):
    c = make_claim(tmp_path, "1_1", ("big.pdf", "small.pdf", "big.json"))
    raw = c / claims.RAW_DIR
    (raw / "big.pdf").write_bytes(b"0" * 2048)
    (raw / "big.json").write_bytes(b"0" * 4096)
    assert claims.large_pdfs(c, limit_bytes=1024) == [("big.pdf", 2048)]

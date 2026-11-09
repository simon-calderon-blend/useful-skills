import pytest

from iae_launch import request

FIELDS = {"idReclamacion": 909, "idSolicitud": 909, "numeroSolicitud": 909, "numeroRadicado": 909}


def body(**kw):
    return request.build_iniciar_body(FIELDS, "000001_909", today="2026-11-09", **kw)


def test_body_shape():
    b = body(env="dev")
    assert b["idReclamacion"] == 909 and b["fechaRadicacion"] == "2026-11-09"
    assert b["soportes"]["rutaArchivosObligatorios"] == "000001_909/obligatorios"
    assert b["soportes"]["rutaArchivosSoportes"] == "000001_909/soportes"
    assert b["soportes"]["idSoporte"] is None
    assert "skipDelivery" not in b
    assert request.validate_body(b) == []


def test_id_soporte_is_int_or_none():
    b = request.build_iniciar_body({**FIELDS, "soportes.idSoporte": 55}, "f", today="d", env="dev")
    assert b["soportes"]["idSoporte"] == 55 and request.validate_body(b) == []


def test_skip_delivery_only_in_test():
    assert body(env="test", skip_delivery=True)["skipDelivery"] is True
    assert "skipDelivery" not in body(env="dev", skip_delivery=False)
    with pytest.raises(ValueError, match="solo en test"):
        body(env="dev", skip_delivery=True)


def test_schema_rejects_string_ids_and_missing_soportes_paths():
    b = body(env="dev")
    b["idReclamacion"] = "909"
    del b["soportes"]["rutaArchivosSoportes"]
    errs = request.validate_body(b)
    assert any("idReclamacion" in e for e in errs)
    assert any("rutaArchivosSoportes" in e for e in errs)


def test_schema_requires_ids():
    errs = request.validate_body({})
    assert any("idReclamacion" in e for e in errs) and any("idSolicitud" in e for e in errs)


def test_schema_nullable_fields():
    b = body(env="dev")
    b["nitEntidad"] = 5
    assert request.validate_body(b)

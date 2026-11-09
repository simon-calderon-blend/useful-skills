import json

import pytest

from iae_launch import claims, invoice

SER_OLD = [{"Datos_servicios_reclamacion": {"Servicios": [
    {"Clave_registro": 7, "Codigo_del_servicio": "S1", "Codificacion_CUPS": "890201",
     "Cantidad_de_servicios": "2.0", "Valor_unitario_facturado": "100.5"},
    {"Codigo_del_servicio": "S2", "Codificacion_CUPS": "", "Cantidad_de_servicios": 1,
     "Valor_unitario_facturado": 3}]}}]


def claim(tmp_path, files):
    raw = tmp_path / "c" / claims.RAW_DIR
    raw.mkdir(parents=True)
    for name, doc in files.items():
        (raw / name).write_text(json.dumps(doc))
    return tmp_path / "c"


def test_local_ok(tmp_path):
    c = claim(tmp_path, {"claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    r = invoice.resolve_invoice(c, "local")
    assert r.details == {"detalles": [{"a": 1}]} and r.count == 1


def test_local_missing(tmp_path):
    with pytest.raises(invoice.InvoiceError, match="claim_invoice_details.json"):
        invoice.resolve_invoice(claim(tmp_path, {}), "local")


def test_local_empty_detalles_is_error_never_fabricated(tmp_path):
    c = claim(tmp_path, {"claim_invoice_details.json": {"detalles": []}})
    with pytest.raises(invoice.InvoiceError, match="vacío"):
        invoice.resolve_invoice(c, "local")


def test_ser_old_format(tmp_path):
    c = claim(tmp_path, {"SER_1.json": SER_OLD})
    r = invoice.resolve_invoice(c, "ser")
    d = r.details["detalles"]
    assert d[0] == {"id_servicio_factura": 7, "codigo_servicio": "S1", "codigo_cups": "890201",
                    "cantidad_servicio": 2, "valor_unitario_fact": 100.5,
                    "consecutivo_procedimiento_qui": None, "codigo_procedimiento_qui": None}
    assert d[1]["id_servicio_factura"] == 2 and d[1]["codigo_cups"] is None


def test_ser_new_format_passthrough(tmp_path):
    c = claim(tmp_path, {"SER_1.json": {"id_reclamacion": 1, "detalles": [{"x": 1}]}})
    assert invoice.resolve_invoice(c, "ser").details["detalles"] == [{"x": 1}]


def test_ser_missing(tmp_path):
    with pytest.raises(invoice.InvoiceError, match="SER_"):
        invoice.resolve_invoice(claim(tmp_path, {}), "ser")


def test_ser_empty_services(tmp_path):
    c = claim(tmp_path, {"SER_1.json": [{"Datos_servicios_reclamacion": {"Servicios": []}}]})
    with pytest.raises(invoice.InvoiceError, match="vacío"):
        invoice.resolve_invoice(c, "ser")


def test_ser_bad_shape(tmp_path):
    c = claim(tmp_path, {"SER_1.json": {"otra": 1}})
    with pytest.raises(invoice.InvoiceError, match="formato"):
        invoice.resolve_invoice(c, "ser")


def test_unknown_mode(tmp_path):
    with pytest.raises(invoice.InvoiceError):
        invoice.resolve_invoice(claim(tmp_path, {}), "magic")

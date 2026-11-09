import json

import pytest

from iae_launch import sourceindex as si
from iae_launch.live import Deployed, LivePaths
from tests.conftest import stream

BUCKET = "adr-test-medicalaudit-workarea"
PID1, PID2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


def lp():
    d = Deployed("a", "e", "p", 1, 1, {})
    return LivePaths("audit-processes", "raw/", "staging/document-extraction/artifacts/",
                     "staging/document-extraction/consolidated/", "raw/", {}, "q", [], 100, d)


def write_csv(tmp_path, rows, header="radicado,pid,descargado,s3uri"):
    p = tmp_path / "process_index.csv"
    p.write_text(header + "\n" + "\n".join(rows) + "\n")
    return p


def row(rad, pid, bucket=BUCKET):
    return f"{rad},{pid},true,s3://{bucket}/audit-processes/{pid}/"


def test_read_index_ok_and_filter(tmp_path):
    p = write_csv(tmp_path, [row("0001_1", PID1), row("0002_2", PID2)])
    rows = si.read_index(p, BUCKET, "audit-processes")
    assert [(r.radicado, r.pid, r.prefix) for r in rows] == [
        ("0001_1", PID1, f"audit-processes/{PID1}/"), ("0002_2", PID2, f"audit-processes/{PID2}/")]
    only = si.read_index(p, BUCKET, "audit-processes", only=["0002_2"])
    assert [r.radicado for r in only] == ["0002_2"]


def test_read_index_unknown_claim_filter(tmp_path):
    p = write_csv(tmp_path, [row("0001_1", PID1)])
    with pytest.raises(si.SourceIndexError, match="9999"):
        si.read_index(p, BUCKET, "audit-processes", only=["9999"])


def test_header_must_match_exactly(tmp_path):
    p = write_csv(tmp_path, [row("0001_1", PID1)], header="radicado,pid,s3uri")
    with pytest.raises(si.SourceIndexError, match="cabecera"):
        si.read_index(p, BUCKET, "audit-processes")


def test_cross_env_refused(tmp_path):
    p = write_csv(tmp_path, [row("0001_1", PID1, bucket="adr-dev-medicalaudit-workarea")])
    with pytest.raises(si.SourceIndexError, match="otro ambiente"):
        si.read_index(p, BUCKET, "audit-processes")


def test_bad_pid_and_key(tmp_path):
    with pytest.raises(si.SourceIndexError, match="UUID"):
        si.read_index(write_csv(tmp_path, [row("0001_1", "not-a-uuid")]), BUCKET, "audit-processes")
    bad = f"0001_1,{PID1},true,s3://{BUCKET}/audit-processes/{PID2}/"
    with pytest.raises(si.SourceIndexError, match="no coincide"):
        si.read_index(write_csv(tmp_path, [bad]), BUCKET, "audit-processes")


def test_empty_index(tmp_path):
    with pytest.raises(si.SourceIndexError, match="vacío"):
        si.read_index(write_csv(tmp_path, []), BUCKET, "audit-processes")


REQ = {"idReclamacion": 5, "idSolicitud": 5, "fechaRadicacion": "2026-01-01",
       "soportes": {"rutaArchivosObligatorios": "a", "rutaArchivosSoportes": "b"}}
SER = [{"Datos_servicios_reclamacion": {"Servicios": [
    {"Codificacion_CUPS": "890201"}, {"Codificacion_CUPS": ""}, {"Codificacion_CUPS": "S1234"}]}}]
INV = {"detalles": [{"codigo_cups": "890201"}, {"codigo_cups": "S1234"}]}


def queue_source(s3, *, with_invoice=True, consolidated=True, inv=INV, req_bytes=None):
    base = f"audit-processes/{PID1}/"
    raw = [base + "raw/FAC_1.pdf", base + "raw/.ingestion-meta.json", base + "raw/request.json",
           base + "raw/claim_invoice_details.json", base + "raw/SER_1.json"]
    s3.ok("list_objects_v2", {"Contents": [{"Key": k, "Size": 10} for k in raw]},
          Bucket=BUCKET, Prefix=base + "raw/")
    s3.ok("list_objects_v2", {"Contents": [{"Key": base + "staging/document-extraction/artifacts/FAC_x.json",
                                            "Size": 3}]},
          Bucket=BUCKET, Prefix=base + "staging/document-extraction/artifacts/")
    if consolidated:
        s3.ok("head_object", {}, Bucket=BUCKET, Key=base + "staging/document-extraction/consolidated/consolidated.json")
    else:
        s3.err("head_object", "404", Bucket=BUCKET,
               Key=base + "staging/document-extraction/consolidated/consolidated.json")
    s3.ok("get_object", {"Body": stream(req_bytes or json.dumps(REQ).encode())}, Bucket=BUCKET,
          Key=base + "raw/request.json")
    if with_invoice:
        s3.ok("get_object", {"Body": stream(inv)}, Bucket=BUCKET, Key=base + "raw/claim_invoice_details.json")
        s3.ok("get_object", {"Body": stream(SER)}, Bucket=BUCKET, Key=base + "raw/SER_1.json")


def one_row(tmp_path):
    return si.read_index(write_csv(tmp_path, [row("0001_1", PID1)]), BUCKET, "audit-processes")[0]


def test_load_source_collects_everything(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_source(s3)
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=True)
    assert sc.request_body == REQ and sc.request_bytes == json.dumps(REQ).encode()
    assert sorted(n for n, _ in sc.raw) == [".ingestion-meta.json", "FAC_1.pdf", "SER_1.json",
                                            "claim_invoice_details.json", "request.json"]
    assert [n for n, _ in sc.artifacts] == ["FAC_x.json"] and sc.consolidated is True
    assert sc.invoice == INV and sc.invoice_cups() == {"890201", "S1234"} and sc.ser_cups == {"890201", "S1234"}
    assert sc.cups_mismatch() is None


def test_load_source_without_invoice_skips_reads(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_source(s3, with_invoice=False, consolidated=False)
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False)
    assert sc.consolidated is False and sc.invoice is None


def test_cups_mismatch_detected(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_source(s3, inv={"detalles": [{"codigo_cups": "890201"}, {"codigo_cups": "ZZZ"}]})
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=True)
    msg = sc.cups_mismatch()
    assert "ZZZ" in msg and "S1234" in msg


def test_empty_detalles_is_mismatch(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_source(s3, inv={"detalles": []})
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=True)
    assert "vacío" in sc.cups_mismatch()


def test_missing_request_json(stubbed, tmp_path):
    s3 = stubbed("s3")
    base = f"audit-processes/{PID1}/"
    s3.ok("list_objects_v2", {"Contents": [{"Key": base + "raw/FAC_1.pdf", "Size": 1}]},
          Bucket=BUCKET, Prefix=base + "raw/")
    s3.ok("list_objects_v2", {}, Bucket=BUCKET, Prefix=base + "staging/document-extraction/artifacts/")
    s3.err("head_object", "404", Bucket=BUCKET,
           Key=base + "staging/document-extraction/consolidated/consolidated.json")
    with pytest.raises(si.SourceIndexError, match="request.json"):
        si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False)


def test_new_format_ser_cups():
    assert si.ser_cups_of({"detalles": [{"codigo_cups": "A"}, {"codigo_cups": None}]}) == {"A"}
    assert si.ser_cups_of([{"Datos_servicios_reclamacion": {"Servicios": [{"Codificacion_CUPS": "B"}]}}]) == {"B"}
    assert si.ser_cups_of({"otra": 1}) == set()


# ---- R1/R2: request original desde el tracker --------------------------------------------
PID_OLD = "00000000-0000-4000-8000-000000000001"
PID_MID = "00000000-0000-4000-8000-000000000002"
REAL = {"idReclamacion": 5, "idSolicitud": 319, "nitEntidad": "890981726", "fechaRadicacion": "2026-10-21",
        "soportes": {"rutaArchivosObligatorios": "https://h.example.com/outputs/890981726/1072/archivos/1/obl/",
                     "rutaArchivosSoportes": "https://h.example.com/outputs/890981726/1072/archivos/4249/soportes/"}}
FAKE = {"idReclamacion": 5, "idSolicitud": 5, "nitEntidad": None,
        "soportes": {"rutaArchivosObligatorios": "0001_5/obligatorios", "rutaArchivosSoportes": "0001_5/soportes"}}


def test_extract_id_paquete():
    assert si.extract_id_paquete(REAL["soportes"]["rutaArchivosSoportes"]) == "1072"
    assert si.extract_id_paquete("outputs/890/77/x") == "77"
    assert si.extract_id_paquete("0001_5/soportes") is None
    assert si.extract_id_paquete("a/b/c") is None
    assert si.extract_id_paquete("") is None
    assert si.extract_id_paquete("s3://bucket-sin-punto/a/55/x") == "55"  # host sin punto: host+path


def test_delivery_problem():
    assert si.delivery_problem(REAL) is None
    p = si.delivery_problem(FAKE)
    assert "nitEntidad" in p and "idPaquete" in p
    assert "nitEntidad" in si.delivery_problem(dict(REAL, nitEntidad="  "))


def tracker_item(pid, ts):
    return {"process_id": {"S": pid}, "events": {"L": [{"M": {"description": {"S": "received"},
                                                             "timestamp": {"S": ts}}}]}}


def tracker_query(ddb, items, claim_id="5"):
    ddb.ok("query", {"Items": items}, TableName="adr-test-medicalaudit-tracker-data",
           IndexName="claim_id_created_date_index", KeyConditionExpression="claim_id = :c",
           ExpressionAttributeValues={":c": {"S": claim_id}},
           ProjectionExpression="process_id, created_at, events", ScanIndexForward=True)


def test_tracker_pids_oldest_first_and_paginated(stubbed):
    ddb = stubbed("dynamodb")
    ddb.ok("query", {"Items": [tracker_item(PID2, "2026-10-21T10:00:00+00:00")],
                     "LastEvaluatedKey": {"process_id": {"S": "z"}}},
           TableName="adr-test-medicalaudit-tracker-data", IndexName="claim_id_created_date_index",
           KeyConditionExpression="claim_id = :c", ExpressionAttributeValues={":c": {"S": "5"}},
           ProjectionExpression="process_id, created_at, events", ScanIndexForward=True)
    ddb.ok("query", {"Items": [tracker_item(PID_OLD, "2026-05-15T10:00:00+00:00")]},
           TableName="adr-test-medicalaudit-tracker-data", IndexName="claim_id_created_date_index",
           KeyConditionExpression="claim_id = :c", ExpressionAttributeValues={":c": {"S": "5"}},
           ProjectionExpression="process_id, created_at, events", ScanIndexForward=True,
           ExclusiveStartKey={"process_id": {"S": "z"}})
    assert si.tracker_pids(ddb.client, "test", 5) == [PID_OLD, PID2]


def queue_row_pid(s3):
    """Lo que load_source lee del pid del índice antes de elegir el request."""
    base = f"audit-processes/{PID1}/"
    s3.ok("list_objects_v2", {"Contents": [{"Key": base + "raw/request.json", "Size": 4}]},
          Bucket=BUCKET, Prefix=base + "raw/")
    s3.ok("list_objects_v2", {}, Bucket=BUCKET, Prefix=base + "staging/document-extraction/artifacts/")
    s3.err("head_object", "404", Bucket=BUCKET,
           Key=base + "staging/document-extraction/consolidated/consolidated.json")
    s3.ok("get_object", {"Body": stream(json.dumps(FAKE).encode())}, Bucket=BUCKET, Key=base + "raw/request.json")


def req_key(pid):
    return f"audit-processes/{pid}/raw/request.json"


def test_source_picks_oldest_existing_deliverable_request(stubbed, tmp_path):
    s3, ddb = stubbed("s3"), stubbed("dynamodb")
    queue_row_pid(s3)
    tracker_query(ddb, [tracker_item(PID1, "2026-11-05T10:00:00+00:00"),
                        tracker_item(PID_MID, "2026-10-21T10:00:00+00:00"),
                        tracker_item(PID_OLD, "2026-05-15T10:00:00+00:00")])
    s3.err("head_object", "404", Bucket=BUCKET, Key=req_key(PID_OLD))          # el más viejo: sin objetos
    s3.ok("head_object", {}, Bucket=BUCKET, Key=req_key(PID_MID))
    s3.ok("get_object", {"Body": stream(json.dumps(REAL).encode())}, Bucket=BUCKET, Key=req_key(PID_MID))
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False, ddb=ddb.client,
                        env="test", request_mode="source")
    assert sc.request_pid == PID_MID and sc.request_body == REAL
    assert sc.inspected == [(PID_OLD, "sin request.json en S3")]
    assert sc.row.pid == PID1  # los documentos siguen saliendo del pid del índice


def test_source_skips_fabricated_requests(stubbed, tmp_path):
    s3, ddb = stubbed("s3"), stubbed("dynamodb")
    queue_row_pid(s3)
    tracker_query(ddb, [tracker_item(PID_OLD, "2026-05-15T10:00:00+00:00"),
                        tracker_item(PID_MID, "2026-10-21T10:00:00+00:00")])
    s3.ok("head_object", {}, Bucket=BUCKET, Key=req_key(PID_OLD))
    s3.ok("get_object", {"Body": stream(json.dumps(FAKE).encode())}, Bucket=BUCKET, Key=req_key(PID_OLD))
    s3.ok("head_object", {}, Bucket=BUCKET, Key=req_key(PID_MID))
    s3.ok("get_object", {"Body": stream(json.dumps(REAL).encode())}, Bucket=BUCKET, Key=req_key(PID_MID))
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False, ddb=ddb.client,
                        env="test", request_mode="source")
    assert sc.request_pid == PID_MID and "no entregable" in sc.inspected[0][1]


def test_source_none_qualifies_lists_inspected(stubbed, tmp_path):
    s3, ddb = stubbed("s3"), stubbed("dynamodb")
    queue_row_pid(s3)
    tracker_query(ddb, [tracker_item(PID_OLD, "2026-05-15T10:00:00+00:00")])
    s3.err("head_object", "404", Bucket=BUCKET, Key=req_key(PID_OLD))
    with pytest.raises(si.SourceIndexError, match=PID_OLD):
        si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False, ddb=ddb.client,
                       env="test", request_mode="source")


def test_source_accepts_fabricated_when_deliverability_not_required(stubbed, tmp_path):
    s3, ddb = stubbed("s3"), stubbed("dynamodb")
    queue_row_pid(s3)
    tracker_query(ddb, [tracker_item(PID_OLD, "2026-05-15T10:00:00+00:00")])
    s3.ok("head_object", {}, Bucket=BUCKET, Key=req_key(PID_OLD))
    s3.ok("get_object", {"Body": stream(json.dumps(FAKE).encode())}, Bucket=BUCKET, Key=req_key(PID_OLD))
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False, ddb=ddb.client,
                        env="test", request_mode="source", require_deliverable=False)
    assert sc.request_pid == PID_OLD


def test_source_explicit_pid_override(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_row_pid(s3)
    s3.ok("head_object", {}, Bucket=BUCKET, Key=req_key(PID_MID))
    s3.ok("get_object", {"Body": stream(json.dumps(REAL).encode())}, Bucket=BUCKET, Key=req_key(PID_MID))
    sc = si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False,
                        request_mode=f"source:{PID_MID}")
    assert sc.request_pid == PID_MID and sc.inspected == []


def test_source_explicit_pid_validated(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_row_pid(s3)
    with pytest.raises(si.SourceIndexError, match="UUID"):
        si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False,
                       request_mode="source:nope")


def test_source_explicit_pid_without_request(stubbed, tmp_path):
    s3 = stubbed("s3")
    queue_row_pid(s3)
    s3.err("head_object", "404", Bucket=BUCKET, Key=req_key(PID_MID))
    with pytest.raises(si.SourceIndexError, match="no tiene"):
        si.load_source(s3.client, BUCKET, lp(), one_row(tmp_path), want_invoice=False,
                       request_mode=f"source:{PID_MID}")

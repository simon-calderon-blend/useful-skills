import pytest
from botocore.stub import ANY

from padding_gate.conveyor import (
    PendingChunk,
    QueueDepth,
    RunConfigResolver,
    group_by_model,
    needed_count,
    queue_depth,
    scan_pending,
)
from tests.conftest import body

TABLE = "adr-dev-medicalaudit-doc-extraction-chunks"
BUCKET = "adr-dev-medicalaudit-workarea"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
MODEL_A = "arn:aws:bedrock:us-east-1:1:application-inference-profile/aaa"
MODEL_B = "arn:aws:bedrock:us-east-1:1:application-inference-profile/bbb"


def _row(chunk_id, process_id, run_id, spuria_run_id=None):
    item = {
        "chunk_id": {"S": chunk_id},
        "pdf_id": {"S": f"{process_id}-pdf"},
        "process_id": {"S": process_id},
        "run_id": {"S": run_id},
        "doc_code": {"S": "ADM"},
    }
    if spuria_run_id:
        item["spuria_run_id"] = {"S": spuria_run_id}
    return item


def _resolver(s3):
    return RunConfigResolver(
        s3,
        bucket=BUCKET,
        base_prefix="audit-processes",
        pointers_prefix="staging/document-extraction/run-config/",
        run_configs_prefix="_global/run-configs/",
    )


def test_queue_depth_reads_visible_and_inflight(stubbed):
    sqs, stub = stubbed("sqs")
    stub.add_response(
        "get_queue_attributes",
        {"Attributes": {"ApproximateNumberOfMessages": "42", "ApproximateNumberOfMessagesNotVisible": "3"}},
        {"QueueUrl": "https://q", "AttributeNames": ANY},
    )
    assert queue_depth(sqs, "https://q") == QueueDepth(visible=42, inflight=3)


def test_scan_pending_pages_and_flags_spuria(stubbed):
    ddb, stub = stubbed("dynamodb")
    params = {
        "TableName": TABLE,
        "FilterExpression": ANY,
        "ProjectionExpression": ANY,
        "ExpressionAttributeNames": ANY,
        "ExpressionAttributeValues": {":pending": {"S": "PENDING"}},
    }
    stub.add_response(
        "scan",
        {"Items": [_row("01JREAL", "proc-1", "proc-1-1")], "LastEvaluatedKey": {"chunk_id": {"S": "01JREAL"}}},
        params,
    )
    stub.add_response(
        "scan",
        {"Items": [_row("spuriaabc", "spuria-abc", "spuria-abc-1", spuria_run_id="abc")]},
        {**params, "ExclusiveStartKey": {"chunk_id": {"S": "01JREAL"}}},
    )

    chunks = scan_pending(ddb, TABLE)

    assert [c.chunk_id for c in chunks] == ["01JREAL", "spuriaabc"]
    assert [c.is_spuria for c in chunks] == [False, True]


def test_resolver_follows_pointer_and_caches_the_body(stubbed):
    s3, stub = stubbed("s3")
    stub.add_response(
        "get_object",
        {"Body": body({"config_digest": DIGEST_A})},
        {"Bucket": BUCKET, "Key": "audit-processes/proc-1/staging/document-extraction/run-config/proc-1-1.json"},
    )
    stub.add_response(
        "get_object",
        {"Body": body({"model": {"model_id": MODEL_A}, "documents": {"ADM": {}}})},
        {"Bucket": BUCKET, "Key": f"audit-processes/_global/run-configs/{DIGEST_A}.json"},
    )
    stub.add_response(
        "get_object",
        {"Body": body({"config_digest": DIGEST_A})},
        {"Bucket": BUCKET, "Key": "audit-processes/proc-2/staging/document-extraction/run-config/proc-2-1.json"},
    )
    resolver = _resolver(s3)

    assert resolver.model_of("proc-1", "proc-1-1") == (DIGEST_A, MODEL_A)
    # Second run, same digest: no second body read (the stub would fail on it).
    assert resolver.model_of("proc-2", "proc-2-1") == (DIGEST_A, MODEL_A)
    assert resolver.documents(DIGEST_A) == {"ADM"}


def test_resolver_returns_none_for_a_missing_pointer(stubbed):
    s3, stub = stubbed("s3")
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    assert _resolver(s3).model_of("proc-1", "proc-1-1") is None


def test_group_by_model_counts_real_and_spuria_per_model(stubbed):
    s3, stub = stubbed("s3")
    pointers = {"proc-1": DIGEST_A, "proc-2": DIGEST_B, "spuria-abc": DIGEST_A}
    for process_id, digest in pointers.items():
        stub.add_response("get_object", {"Body": body({"config_digest": digest})})
        model = MODEL_A if digest == DIGEST_A else MODEL_B
        if process_id != "spuria-abc":  # body A is cached by then
            stub.add_response("get_object", {"Body": body({"model": {"model_id": model}})})
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    chunks = [
        PendingChunk("c1", "p", "proc-1", "proc-1-1", "ADM", None),
        PendingChunk("c2", "p", "proc-1", "proc-1-1", "ADM", None),
        PendingChunk("c3", "p", "proc-2", "proc-2-1", "PDX", None),
        PendingChunk("spuriaabc1", "p", "spuria-abc", "spuria-abc-1", "ADM", "abc"),
        PendingChunk("c4", "p", "proc-9", "proc-9-1", "ADM", None),
    ]

    groups, unresolved = group_by_model(chunks, _resolver(s3))

    by_model = {g.model_id: g for g in groups}
    assert (by_model[MODEL_A].real, by_model[MODEL_A].spuria, by_model[MODEL_A].digest) == (2, 1, DIGEST_A)
    assert (by_model[MODEL_B].real, by_model[MODEL_B].spuria) == (1, 0)
    assert groups[0].model_id == MODEL_A  # largest real group first
    assert unresolved == 1


@pytest.mark.parametrize(
    ("min_records", "visible", "group_total", "expected"),
    [
        (100, 20, 20, 90),   # gap 80 + buffer 10
        (100, 99, 99, 11),
        (100, 120, 120, 0),  # already over the gate
        (100, 130, 60, 50),  # queue is full but this model's group is short
        (100, 0, 0, 110),
    ],
)
def test_needed_count_is_gap_plus_buffer(min_records, visible, group_total, expected):
    assert needed_count(min_records, visible, group_total) == expected


def test_corrupt_pointer_reads_as_unresolved(stubbed):
    s3, stub = stubbed("s3")
    stub.add_response("get_object", {"Body": body(b"{not json")})
    assert _resolver(s3).model_of("proc-1", "proc-1-1") is None

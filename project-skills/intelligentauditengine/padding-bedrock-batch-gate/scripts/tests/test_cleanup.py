from datetime import datetime, timezone

import pytest
from botocore.stub import ANY

from padding_gate.cleanup import (
    CleanupFailed,
    CleanupRefused,
    SpuriaRow,
    assess_run,
    delete_run,
    scan_spuria_rows,
)

TABLE = "adr-test-medicalaudit-doc-extraction-chunks"
BUCKET = "adr-test-medicalaudit-workarea"
RUN = "0123456789ab"
JOB = "arn:aws:bedrock:us-east-1:276553701208:model-invocation-job/abc123"


def _job(status):
    return {
        "jobArn": JOB,
        "modelId": "m",
        "roleArn": "arn:aws:iam::276553701208:role/r",
        "submitTime": datetime(2026, 11, 9, tzinfo=timezone.utc),
        "inputDataConfig": {"s3InputDataConfig": {"s3Uri": "s3://b/in/"}},
        "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": "s3://b/out/"}},
        "status": status,
    }


def _rows(*statuses, job=JOB):
    return [
        SpuriaRow(f"spuria{RUN}{i:032x}", RUN, status, job if status == "IN_BATCH" else None)
        for i, status in enumerate(statuses)
    ]


def _stub_real_in_flight(stub, count):
    stub.add_response(
        "scan",
        {"Count": count, "ScannedCount": 500},
        {
            "TableName": TABLE,
            "Select": "COUNT",
            "ConsistentRead": True,
            "FilterExpression": "batch_job_id = :j AND #s = :ib AND attribute_not_exists(spuria_run_id)",
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": {":j": {"S": JOB}, ":ib": {"S": "IN_BATCH"}},
        },
    )


def test_scan_spuria_rows_for_one_run(stubbed):
    ddb, stub = stubbed("dynamodb")
    stub.add_response(
        "scan",
        {
            "Items": [
                {"chunk_id": {"S": "spuriaX"}, "spuria_run_id": {"S": RUN}, "status": {"S": "IN_BATCH"},
                 "batch_job_id": {"S": JOB}},
                {"chunk_id": {"S": "spuriaY"}, "spuria_run_id": {"S": RUN}, "status": {"S": "DONE"}},
            ]
        },
        {
            "TableName": TABLE,
            "ConsistentRead": True,
            "FilterExpression": "spuria_run_id = :r",
            "ProjectionExpression": ANY,
            "ExpressionAttributeNames": ANY,
            "ExpressionAttributeValues": {":r": {"S": RUN}},
        },
    )
    rows = scan_spuria_rows(ddb, TABLE, RUN)
    assert rows == [SpuriaRow("spuriaX", RUN, "IN_BATCH", JOB), SpuriaRow("spuriaY", RUN, "DONE", None)]


def test_reconciled_rows_are_safe_without_any_aws_call(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, _ = stubbed("bedrock")
    verdict = assess_run(RUN, _rows("DONE", "FAILED", "NEEDS_ONDEMAND"), ddb, bedrock, TABLE)
    assert verdict.safe
    assert verdict.counts == {"DONE": 1, "FAILED": 1, "NEEDS_ONDEMAND": 1}


def test_pending_rows_block_cleanup(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, _ = stubbed("bedrock")
    verdict = assess_run(RUN, _rows("PENDING", "DONE"), ddb, bedrock, TABLE)
    assert not verdict.safe
    assert "PENDING" in verdict.reasons[0]


def test_job_still_running_blocks_cleanup(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, stub = stubbed("bedrock")
    stub.add_response("get_model_invocation_job", _job("InProgress"), {"jobIdentifier": JOB})
    verdict = assess_run(RUN, _rows("IN_BATCH", "IN_BATCH"), ddb, bedrock, TABLE)
    assert not verdict.safe
    assert "InProgress" in verdict.reasons[0]
    assert verdict.jobs == {JOB: "InProgress"}


def test_finished_job_with_unreconciled_real_chunks_blocks_cleanup(stubbed):
    ddb, ddb_stub = stubbed("dynamodb")
    bedrock, stub = stubbed("bedrock")
    stub.add_response("get_model_invocation_job", _job("Completed"), {"jobIdentifier": JOB})
    _stub_real_in_flight(ddb_stub, 3)
    verdict = assess_run(RUN, _rows("IN_BATCH"), ddb, bedrock, TABLE)
    assert not verdict.safe
    assert "3 real chunk" in verdict.reasons[0]


def test_finished_pure_spuria_job_is_safe(stubbed):
    # A job of filler only is never reconciled (batch-poller finds jobs through
    # WAITING_FOR_BATCH runs, and spuria has none), so IN_BATCH is its final state.
    ddb, ddb_stub = stubbed("dynamodb")
    bedrock, stub = stubbed("bedrock")
    stub.add_response("get_model_invocation_job", _job("Completed"), {"jobIdentifier": JOB})
    _stub_real_in_flight(ddb_stub, 0)
    assert assess_run(RUN, _rows("IN_BATCH", "IN_BATCH"), ddb, bedrock, TABLE).safe


def test_in_batch_row_without_job_id_blocks_cleanup(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, _ = stubbed("bedrock")
    verdict = assess_run(RUN, _rows("IN_BATCH", job=None), ddb, bedrock, TABLE)
    assert not verdict.safe


def test_delete_run_removes_rows_and_s3_prefix(stubbed):
    ddb, ddb_stub = stubbed("dynamodb")
    s3, s3_stub = stubbed("s3")
    rows = _rows("DONE", "FAILED")
    for row in rows:
        ddb_stub.add_response(
            "delete_item",
            {},
            {
                "TableName": TABLE,
                "Key": {"chunk_id": {"S": row.chunk_id}},
                "ConditionExpression": "spuria_run_id = :r AND #s = :st",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": {":r": {"S": RUN}, ":st": {"S": row.status}},
            },
        )
    prefix = f"audit-processes/spuria-{RUN}/"
    keys = [f"{prefix}chunks/blank.pdf", f"{prefix}staging/document-extraction/run-config/spuria-{RUN}-1.json"]
    s3_stub.add_response(
        "list_objects_v2", {"Contents": [{"Key": k} for k in keys]}, {"Bucket": BUCKET, "Prefix": prefix}
    )
    s3_stub.add_response(
        "delete_objects",
        {"Deleted": [{"Key": k} for k in keys]},
        {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": k} for k in keys], "Quiet": True}},
    )
    verdict = assess_run(RUN, rows, ddb, None, TABLE)

    assert delete_run(verdict, rows, ddb=ddb, s3=s3, table=TABLE, bucket=BUCKET,
                      base_prefix="audit-processes") == (2, 2)


def test_delete_run_refuses_an_unsafe_verdict(stubbed):
    ddb, _ = stubbed("dynamodb")
    s3, _ = stubbed("s3")
    rows = _rows("PENDING")
    verdict = assess_run(RUN, rows, ddb, None, TABLE)
    with pytest.raises(CleanupRefused):
        delete_run(verdict, rows, ddb=ddb, s3=s3, table=TABLE, bucket=BUCKET, base_prefix="audit-processes")


@pytest.mark.parametrize("bad", ["", "all-spuria", "0123456789a", "0123456789ab/..", "ZZZZZZZZZZZZ"])
def test_run_id_must_be_twelve_hex_chars(stubbed, bad):
    ddb, _ = stubbed("dynamodb")
    with pytest.raises(CleanupRefused):
        scan_spuria_rows(ddb, TABLE, bad)


def test_no_rows_is_safe_and_only_the_s3_prefix_is_left(stubbed):
    ddb, _ = stubbed("dynamodb")
    verdict = assess_run(RUN, [], ddb, None, TABLE)
    assert verdict.safe and verdict.counts == {}


def test_abandon_pending_unblocks_rows_of_a_job_that_never_formed(stubbed):
    # A failed inject can leave PENDING rows with no SQS message; nothing will
    # ever move them, and without this they would wait for the 30-day TTL.
    ddb, _ = stubbed("dynamodb")
    bedrock, _ = stubbed("bedrock")
    assert assess_run(RUN, _rows("PENDING", "DONE"), ddb, bedrock, TABLE, abandon_pending=True).safe


def test_abandon_pending_does_not_unblock_a_running_job(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, stub = stubbed("bedrock")
    stub.add_response("get_model_invocation_job", _job("InProgress"), {"jobIdentifier": JOB})
    verdict = assess_run(RUN, _rows("PENDING", "IN_BATCH"), ddb, bedrock, TABLE, abandon_pending=True)
    assert not verdict.safe


def test_unreadable_job_blocks_instead_of_crashing(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, stub = stubbed("bedrock")
    stub.add_client_error("get_model_invocation_job", service_error_code="ResourceNotFoundException")
    verdict = assess_run(RUN, _rows("IN_BATCH"), ddb, bedrock, TABLE)
    assert not verdict.safe
    assert "ResourceNotFoundException" in verdict.reasons[0]


def test_empty_job_id_counts_as_missing(stubbed):
    ddb, _ = stubbed("dynamodb")
    bedrock, _ = stubbed("bedrock")
    verdict = assess_run(RUN, _rows("IN_BATCH", job=""), ddb, bedrock, TABLE)
    assert not verdict.safe


def test_row_that_changed_since_assessment_keeps_the_s3_prefix(stubbed):
    # Reconcile can flip a row between the scan and the delete. The delete is
    # conditioned on the status seen, and the pointer must then stay: a live row
    # without its run-config pointer is released forever by batch-trigger.
    ddb, ddb_stub = stubbed("dynamodb")
    s3, _ = stubbed("s3")
    rows = _rows("DONE", "DONE")
    ddb_stub.add_response("delete_item", {}, None)
    ddb_stub.add_client_error("delete_item", service_error_code="ConditionalCheckFailedException")
    verdict = assess_run(RUN, rows, ddb, None, TABLE)

    with pytest.raises(CleanupFailed) as raised:
        delete_run(verdict, rows, ddb=ddb, s3=s3, table=TABLE, bucket=BUCKET, base_prefix="audit-processes")

    assert (raised.value.rows_deleted, raised.value.objects_deleted) == (1, 0)


def test_delete_error_reports_progress(stubbed):
    ddb, ddb_stub = stubbed("dynamodb")
    s3, _ = stubbed("s3")
    rows = _rows("DONE", "DONE")
    ddb_stub.add_response("delete_item", {}, None)
    ddb_stub.add_client_error("delete_item", service_error_code="ProvisionedThroughputExceededException")
    verdict = assess_run(RUN, rows, ddb, None, TABLE)

    with pytest.raises(CleanupFailed) as raised:
        delete_run(verdict, rows, ddb=ddb, s3=s3, table=TABLE, bucket=BUCKET, base_prefix="audit-processes")

    assert raised.value.rows_deleted == 1

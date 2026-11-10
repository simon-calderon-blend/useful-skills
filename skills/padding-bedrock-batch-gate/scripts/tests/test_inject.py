import itertools
import json
import re

import pytest

from padding_gate.appconfig import LiveConfig
from padding_gate.conveyor import ModelGroup, QueueDepth
from padding_gate.inject import (
    InjectFailed,
    InjectRefused,
    apply_plan,
    build_plan,
    chunk_item,
    minimal_pdf,
    wait_for_quiet,
)

BUCKET = "adr-test-medicalaudit-workarea"
TABLE = "adr-test-medicalaudit-doc-extraction-chunks"
QUEUE = "https://sqs.us-east-1.amazonaws.com/276553701208/q"
DIGEST = "d" * 64
MODEL = "arn:aws:bedrock:us-east-1:276553701208:application-inference-profile/x"
LIVE = LiveConfig(
    min_records=100,
    run_configs_prefix="_global/run-configs/",
    pointers_prefix="staging/document-extraction/run-config/",
    batch_doc_codes=frozenset({"ADM", "PDX"}),
)


class FakeResolver:
    def __init__(self, documents=("ADM", "PDX")):
        self._documents = set(documents)

    def documents(self, digest):
        assert digest == DIGEST
        return self._documents

    def pointer_key(self, process_id, run_id):
        return f"audit-processes/{process_id}/staging/document-extraction/run-config/{run_id}.json"


def _hex_source():
    counter = itertools.count()
    return lambda: f"{next(counter):032x}"


def _plan(**overrides):
    kwargs = dict(
        live=LIVE,
        depth=QueueDepth(visible=20, inflight=0),
        groups=[ModelGroup(model_id=MODEL, digest=DIGEST, real=20)],
        resolver=FakeResolver(),
        doc_code="ADM",
        count=None,
        base_prefix="audit-processes",
        new_hex=_hex_source(),
    )
    kwargs.update(overrides)
    return build_plan(**kwargs)


def test_minimal_pdf_is_one_blank_page():
    pdf = minimal_pdf()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert len(re.findall(rb"/Type /Page(?!s)", pdf)) == 1
    xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
    assert pdf[xref:].startswith(b"xref")


def test_plan_tops_up_the_target_group_with_buffer():
    plan = _plan()
    assert plan.count == 90
    assert len(plan.chunk_ids) == 90 == len(set(plan.chunk_ids))
    assert (plan.digest, plan.model_id) == (DIGEST, MODEL)
    assert plan.pdf_key == f"audit-processes/spuria-{plan.run_id}/chunks/blank.pdf"
    assert plan.pointer_key == (
        f"audit-processes/spuria-{plan.run_id}/staging/document-extraction/run-config/"
        f"spuria-{plan.run_id}-1.json"
    )
    for chunk_id in plan.chunk_ids:
        # chunk_id is the Bedrock recordId: alphanumeric, under the SQS 80-char Id cap.
        assert re.fullmatch(r"spuria[0-9a-f]{12}[0-9a-f]{32}", chunk_id)
        assert chunk_id.startswith(f"spuria{plan.run_id}")


def test_explicit_count_overrides_the_gap():
    assert _plan(count=15).count == 15


def test_explicit_count_cannot_exceed_the_computed_top_up():
    # Above the top-up is pure Bedrock spend: --count may only lower it.
    with pytest.raises(InjectRefused, match="between 1 and 90"):
        _plan(count=91)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"depth": QueueDepth(visible=0, inflight=0)}, "queue is empty"),
        ({"groups": []}, "no real chunk"),
        ({"groups": [ModelGroup(model_id=MODEL, digest=DIGEST, real=0, spuria=30)]}, "no real chunk"),
        ({"doc_code": "SPU"}, "not a batch doc_code"),
        ({"doc_code": "PDX", "resolver": FakeResolver(documents=["ADM"])}, "no document profile"),
        (
            {"depth": QueueDepth(visible=150, inflight=0),
             "groups": [ModelGroup(model_id=MODEL, digest=DIGEST, real=150)]},
            "already",
        ),
    ],
)
def test_plan_refusals(overrides, message):
    with pytest.raises(InjectRefused, match=message):
        _plan(**overrides)


def test_chunk_row_mirrors_chunk_pdf_shape():
    plan = _plan(count=1)
    item = chunk_item(plan, plan.chunk_ids[0], BUCKET, now=1_700_000_000)
    rid = plan.run_id
    assert item == {
        "chunk_id": {"S": plan.chunk_ids[0]},
        "pdf_id": {"S": f"spuria-{rid}-pdf"},
        "process_id": {"S": f"spuria-{rid}"},
        # rsplit("-", 1)[0] of run_id must give process_id back (manifest.py).
        "run_id": {"S": f"spuria-{rid}-1"},
        "doc_code": {"S": "ADM"},
        "chunk_index": {"N": "1"},
        "page_start": {"N": "1"},
        "page_end": {"N": "1"},
        "chunk_s3_uri": {"S": f"s3://{BUCKET}/{plan.pdf_key}"},
        "status": {"S": "PENDING"},
        "created_at": {"N": "1700000000"},
        "expire_at": {"N": str(1_700_000_000 + 30 * 86400)},
        "spuria_run_id": {"S": rid},
    }


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_wait_for_quiet_returns_once_depth_holds_still():
    clock = FakeClock()
    depths = iter([20, 24, 24, 24, 24])
    settled = wait_for_quiet(lambda: next(depths), quiet_seconds=60, poll_seconds=30,
                             max_wait=600, clock=clock, sleep=clock.sleep)
    assert settled == 24
    assert clock.now == 90  # 24 first seen at t=30, held through t=90


def test_wait_for_quiet_gives_up_on_a_moving_queue():
    clock = FakeClock()
    depths = itertools.count(1)
    with pytest.raises(InjectRefused, match="did not settle"):
        wait_for_quiet(lambda: next(depths), quiet_seconds=60, poll_seconds=30,
                       max_wait=120, clock=clock, sleep=clock.sleep)


def _record_calls(clients, log):
    for client in clients:
        client.meta.events.register(
            "before-parameter-build.*.*", lambda model, **_: log.append(model.name)
        )


def test_apply_writes_pointer_then_pdf_then_rows_then_messages(stubbed):
    s3, s3_stub = stubbed("s3")
    ddb, ddb_stub = stubbed("dynamodb")
    sqs, sqs_stub = stubbed("sqs")
    plan = _plan(count=12)
    log: list[str] = []
    _record_calls([s3, ddb, sqs], log)

    s3_stub.add_response("put_object", {}, {
        "Bucket": BUCKET, "Key": plan.pointer_key,
        "Body": json.dumps({"config_digest": DIGEST}).encode(), "ContentType": "application/json",
    })
    s3_stub.add_response("put_object", {}, {
        "Bucket": BUCKET, "Key": plan.pdf_key, "Body": minimal_pdf(), "ContentType": "application/pdf",
    })
    for chunk_id in plan.chunk_ids:
        ddb_stub.add_response("put_item", {}, {
            "TableName": TABLE, "Item": chunk_item(plan, chunk_id, BUCKET, now=5),
            "ConditionExpression": "attribute_not_exists(chunk_id)",
        })
    for batch in (plan.chunk_ids[:10], plan.chunk_ids[10:]):
        sqs_stub.add_response("send_message_batch", {"Successful": [], "Failed": []}, {
            "QueueUrl": QUEUE,
            "Entries": [
                {"Id": cid, "MessageBody": json.dumps({
                    "chunk_id": cid, "pdf_id": f"spuria-{plan.run_id}-pdf",
                    "process_id": f"spuria-{plan.run_id}"})}
                for cid in batch
            ],
        })

    apply_plan(plan, s3=s3, ddb=ddb, sqs=sqs, queue_url=QUEUE, bucket=BUCKET, table=TABLE, now=5)

    assert log == ["PutObject", "PutObject"] + ["PutItem"] * 12 + ["SendMessageBatch"] * 2


def test_apply_reports_the_run_id_when_sqs_partially_fails(stubbed):
    s3, s3_stub = stubbed("s3")
    ddb, ddb_stub = stubbed("dynamodb")
    sqs, sqs_stub = stubbed("sqs")
    plan = _plan(count=1)
    s3_stub.add_response("put_object", {}, None)
    s3_stub.add_response("put_object", {}, None)
    ddb_stub.add_response("put_item", {}, None)
    sqs_stub.add_response("send_message_batch", {
        "Successful": [],
        "Failed": [{"Id": plan.chunk_ids[0], "SenderFault": False, "Code": "InternalError"}],
    }, None)

    with pytest.raises(InjectFailed) as raised:
        apply_plan(plan, s3=s3, ddb=ddb, sqs=sqs, queue_url=QUEUE, bucket=BUCKET, table=TABLE, now=5)

    assert raised.value.run_id == plan.run_id
    assert raised.value.may_have_written


def test_interrupt_mid_write_still_names_the_run():
    class InterruptedS3:
        def put_object(self, **_):
            raise KeyboardInterrupt

    plan = _plan(count=1)
    with pytest.raises(InjectFailed) as raised:
        apply_plan(plan, s3=InterruptedS3(), ddb=None, sqs=None, queue_url=QUEUE,
                   bucket=BUCKET, table=TABLE, now=5)

    assert raised.value.run_id == plan.run_id

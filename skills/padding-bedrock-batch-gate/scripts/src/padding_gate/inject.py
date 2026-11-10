"""Plan and write the filler ("spuria") chunks.

Per run, everything lives under ``<base>/spuria-<run_id>/`` plus one chunks row
and one conveyor message per filler record:

1. a run-config POINTER to a body the pipeline already froze (batch-trigger
   resolves every chunk run_id -> pointer -> body; no pointer = chunk released),
2. one blank 1-page PDF shared by all rows,
3. the chunks rows (status PENDING, conditional on not existing),
4. the SQS messages.

S3 and DynamoDB are written before any message: a message whose row is missing
is deleted by batch-trigger as stale, so the reverse order would waste filler.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from padding_gate.appconfig import LiveConfig
from padding_gate.conveyor import ModelGroup, QueueDepth, needed_count

DEFAULT_DOC_CODE = "ADM"
CHUNK_TTL_DAYS = 30  # chunk_pdf.py CHUNKS_TTL_DAYS default; leftover filler expires on its own
# Rough Bedrock Batch cost of one blank-page record (Sonnet-class: ~2000 input
# tokens at $1.50/M, ~200 output at $7.50/M). For the confirmation prompt only.
EST_USD_PER_RECORD = 0.0045
_SQS_BATCH = 10


class InjectRefused(Exception):
    """Nothing was written: the request is unsafe or pointless."""


class InjectFailed(Exception):
    """A write failed part-way. The run id names whatever was written."""

    def __init__(self, message: str, *, run_id: str, may_have_written: bool) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.may_have_written = may_have_written


class _Resolver(Protocol):
    def documents(self, digest: str) -> set[str]: ...
    def pointer_key(self, process_id: str, run_id: str) -> str: ...


@dataclass(frozen=True)
class Plan:
    run_id: str
    count: int
    doc_code: str
    digest: str
    model_id: str
    visible: int
    group_real: int
    group_total: int
    min_records: int
    chunk_ids: tuple[str, ...]
    pdf_key: str
    pointer_key: str
    cost_usd: float

    @property
    def process_id(self) -> str:
        return f"spuria-{self.run_id}"

    @property
    def pdf_id(self) -> str:
        return f"spuria-{self.run_id}-pdf"

    @property
    def run_key(self) -> str:
        # manifest.py recovers the process id with run_id.rsplit("-", 1)[0].
        return f"spuria-{self.run_id}-1"


def minimal_pdf() -> bytes:
    """A valid blank Letter page; xref offsets computed, never hardcoded."""
    buf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, obj in enumerate(
        (
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        ),
        start=1,
    ):
        offsets.append(len(buf))
        buf += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(offsets) + 1}\n".encode() + b"0000000000 65535 f \n"
    buf += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    buf += f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(buf)


def build_plan(
    *,
    live: LiveConfig,
    depth: QueueDepth,
    groups: list[ModelGroup],
    resolver: _Resolver,
    doc_code: str,
    count: int | None,
    base_prefix: str,
    new_hex: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> Plan:
    if depth.visible == 0:
        raise InjectRefused("the conveyor queue is empty: there is nothing waiting to carry")
    if doc_code not in live.batch_doc_codes:
        raise InjectRefused(
            f"{doc_code!r} is not a batch doc_code in AppConfig extraction "
            f"(batch codes: {sorted(live.batch_doc_codes)})"
        )
    target = next((g for g in groups if g.real > 0), None)
    if target is None:
        raise InjectRefused("no real chunk is PENDING with a resolvable run config; nothing to carry")
    if doc_code not in resolver.documents(target.digest):
        raise InjectRefused(
            f"the run config {target.digest[:16]}... has no document profile for {doc_code!r}; "
            "batch-trigger would FAIL every filler chunk"
        )
    needed = needed_count(live.min_records, depth.visible, target.total)
    if needed == 0:
        raise InjectRefused(
            f"queue ({depth.visible}) and model group ({target.total}) already reach "
            f"min_records_per_job={live.min_records}"
        )
    if count is not None and not 1 <= count <= needed:
        raise InjectRefused(
            f"--count must be between 1 and {needed} (the computed top-up); "
            "more filler only adds Bedrock spend"
        )
    total = count if count is not None else needed

    run_id = new_hex()[:12]
    chunk_ids = tuple(f"spuria{run_id}{new_hex()}" for _ in range(total))
    base = base_prefix.rstrip("/")
    return Plan(
        run_id=run_id,
        count=total,
        doc_code=doc_code,
        digest=target.digest,
        model_id=target.model_id,
        visible=depth.visible,
        group_real=target.real,
        group_total=target.total,
        min_records=live.min_records,
        chunk_ids=chunk_ids,
        pdf_key=f"{base}/spuria-{run_id}/chunks/blank.pdf",
        pointer_key=resolver.pointer_key(f"spuria-{run_id}", f"spuria-{run_id}-1"),
        cost_usd=round(total * EST_USD_PER_RECORD, 2),
    )


def chunk_item(plan: Plan, chunk_id: str, bucket: str, now: int) -> dict:
    """chunk_pdf.py's PENDING row, plus the spuria_run_id marker cleanup keys on.

    pdf_id, process_id, run_id and page_start must be non-empty: batch-trigger and
    reconcile read them by subscript. pending_marker is left out on purpose so the
    poller's orphan sweep never re-sends filler.
    """
    return {
        "chunk_id": {"S": chunk_id},
        "pdf_id": {"S": plan.pdf_id},
        "process_id": {"S": plan.process_id},
        "run_id": {"S": plan.run_key},
        "doc_code": {"S": plan.doc_code},
        "chunk_index": {"N": "1"},
        "page_start": {"N": "1"},
        "page_end": {"N": "1"},
        "chunk_s3_uri": {"S": f"s3://{bucket}/{plan.pdf_key}"},
        "status": {"S": "PENDING"},
        "created_at": {"N": str(now)},
        "expire_at": {"N": str(now + CHUNK_TTL_DAYS * 86400)},
        "spuria_run_id": {"S": plan.run_id},
    }


def wait_for_quiet(
    read_depth: Callable[[], int],
    *,
    quiet_seconds: float,
    poll_seconds: float,
    max_wait: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Block until the visible depth holds still for ``quiet_seconds``.

    There is no event for "all of the run's chunks are queued"; a depth that stops
    moving stands in for it. Padding earlier fires a job of pure filler and leaves
    the real chunks behind for the next one.
    """
    start = clock()
    last = read_depth()
    since = start
    while True:
        if clock() - since >= quiet_seconds:
            return last
        if clock() - start > max_wait:
            raise InjectRefused(
                f"queue depth did not settle for {quiet_seconds:.0f}s within {max_wait:.0f}s"
            )
        sleep(poll_seconds)
        depth = read_depth()
        if depth != last:
            last, since = depth, clock()


def apply_plan(
    plan: Plan, *, s3: Any, ddb: Any, sqs: Any, queue_url: str, bucket: str, table: str, now: int
) -> None:
    try:
        s3.put_object(
            Bucket=bucket,
            Key=plan.pointer_key,
            Body=json.dumps({"config_digest": plan.digest}).encode(),
            ContentType="application/json",
        )
        s3.put_object(Bucket=bucket, Key=plan.pdf_key, Body=minimal_pdf(), ContentType="application/pdf")
        for chunk_id in plan.chunk_ids:
            ddb.put_item(
                TableName=table,
                Item=chunk_item(plan, chunk_id, bucket, now),
                ConditionExpression="attribute_not_exists(chunk_id)",
            )
        body = {"pdf_id": plan.pdf_id, "process_id": plan.process_id}
        for start in range(0, len(plan.chunk_ids), _SQS_BATCH):
            entries = [
                {"Id": cid, "MessageBody": json.dumps({"chunk_id": cid, **body})}
                for cid in plan.chunk_ids[start : start + _SQS_BATCH]
            ]
            failed = sqs.send_message_batch(QueueUrl=queue_url, Entries=entries).get("Failed")
            if failed:
                raise RuntimeError(f"SQS rejected {len(failed)} message(s): {failed}")
    except BaseException as error:  # Ctrl-C included: the run id must still be reported
        raise InjectFailed(
            f"write failed part-way ({error}); filler run {plan.run_id} may be partly written",
            run_id=plan.run_id,
            may_have_written=True,
        ) from error

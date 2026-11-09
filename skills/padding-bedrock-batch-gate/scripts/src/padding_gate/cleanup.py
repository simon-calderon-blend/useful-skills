"""Decide whether a filler run can be removed, and remove it only when it can.

The rule: a spuria row may go once nothing will read it again.

* DONE / FAILED / NEEDS_ONDEMAND: reconcile already processed it.
* IN_BATCH: batch-submit stamped ``batch_job_id``. Safe only when that Bedrock job
  is terminal AND no real chunk of the same job is still IN_BATCH, i.e. reconcile
  has passed over the job (or it was pure filler, which reconcile never visits:
  batch-poller finds jobs through WAITING_FOR_BATCH runs and filler has none).
* PENDING: the job has not formed yet. Removing the filler now is how the gate
  stays shut for the real chunks it was meant to carry. The one exception is a
  failed inject whose rows never got a message: nothing will ever move them, so
  ``abandon_pending`` lets the operator remove them deliberately.

All reads are strongly consistent: a stale "0 rows" or "0 real chunks in flight"
is exactly the read that would call an unsafe delete SAFE.

The test account is shared: someone else's claims can be in the same job, which is
why the check looks at the job, not at this run's own rows.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import ClientError

RECONCILED = frozenset({"DONE", "FAILED", "NEEDS_ONDEMAND"})
TERMINAL_JOB = frozenset({"Completed", "PartiallyCompleted", "Failed", "Stopped", "Expired"})
_RUN_ID = re.compile(r"[0-9a-f]{12}")


class CleanupRefused(Exception):
    """Deleting this run now could hang real claims."""


class CleanupFailed(Exception):
    """A delete stopped part-way. Counts say how far it got."""

    def __init__(self, message: str, *, rows_deleted: int, objects_deleted: int) -> None:
        super().__init__(message)
        self.rows_deleted = rows_deleted
        self.objects_deleted = objects_deleted


@dataclass(frozen=True)
class SpuriaRow:
    chunk_id: str
    spuria_run_id: str
    status: str
    batch_job_id: str | None


@dataclass
class Verdict:
    run_id: str
    safe: bool
    reasons: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    jobs: dict[str, str] = field(default_factory=dict)


def validate_run_id(run_id: str) -> str:
    if not _RUN_ID.fullmatch(run_id or ""):
        raise CleanupRefused(f"run id must be 12 lowercase hex characters, got {run_id!r}")
    return run_id


def scan_spuria_rows(ddb: Any, table: str, run_id: str | None = None) -> list[SpuriaRow]:
    """Filler rows of one run, or of every run when ``run_id`` is None."""
    params: dict[str, Any] = {
        "TableName": table,
        "ConsistentRead": True,
        "ProjectionExpression": "chunk_id, spuria_run_id, #s, batch_job_id",
        "ExpressionAttributeNames": {"#s": "status"},
    }
    if run_id is None:
        params["FilterExpression"] = "attribute_exists(spuria_run_id)"
    else:
        params["FilterExpression"] = "spuria_run_id = :r"
        params["ExpressionAttributeValues"] = {":r": {"S": validate_run_id(run_id)}}
    return [
        SpuriaRow(
            chunk_id=item["chunk_id"]["S"],
            spuria_run_id=item["spuria_run_id"]["S"],
            status=item.get("status", {}).get("S", "?"),
            batch_job_id=item.get("batch_job_id", {}).get("S"),
        )
        for page in ddb.get_paginator("scan").paginate(**params)
        for item in page.get("Items", [])
    ]


def _real_chunks_in_flight(ddb: Any, table: str, job_arn: str) -> int:
    pages = ddb.get_paginator("scan").paginate(
        TableName=table,
        Select="COUNT",
        ConsistentRead=True,
        FilterExpression="batch_job_id = :j AND #s = :ib AND attribute_not_exists(spuria_run_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":j": {"S": job_arn}, ":ib": {"S": "IN_BATCH"}},
    )
    return sum(page.get("Count", 0) for page in pages)


def assess_run(
    run_id: str,
    rows: list[SpuriaRow],
    ddb: Any,
    bedrock: Any,
    table: str,
    *,
    abandon_pending: bool = False,
) -> Verdict:
    verdict = Verdict(run_id=run_id, safe=False, counts=dict(Counter(r.status for r in rows)))
    allowed = RECONCILED | {"PENDING"} if abandon_pending else RECONCILED
    in_batch = [r for r in rows if r.status == "IN_BATCH"]
    others = [r for r in rows if r.status not in allowed and r.status != "IN_BATCH"]

    if others:
        statuses = Counter(r.status for r in others)
        hint = "" if abandon_pending or "PENDING" not in statuses else (
            " (if a failed inject left them with no SQS message, see --abandon-pending)"
        )
        verdict.reasons.append(
            f"{sum(statuses.values())} row(s) in {dict(statuses)}: the batch job has not formed yet{hint}"
        )
        return verdict
    if any(not r.batch_job_id for r in in_batch):
        verdict.reasons.append("IN_BATCH row(s) without batch_job_id: cannot tell which job owns them")
        return verdict

    for job_arn in sorted({r.batch_job_id for r in in_batch if r.batch_job_id}):
        try:
            status = bedrock.get_model_invocation_job(jobIdentifier=job_arn)["status"]
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", type(error).__name__)
            verdict.reasons.append(f"could not read job {job_arn}: {code}")
            continue
        verdict.jobs[job_arn] = status
        if status not in TERMINAL_JOB:
            verdict.reasons.append(f"job {job_arn} is {status}")
            continue
        real = _real_chunks_in_flight(ddb, table, job_arn)
        if real:
            verdict.reasons.append(
                f"job {job_arn} is {status} but {real} real chunk(s) are still IN_BATCH "
                "(reconcile has not processed it yet)"
            )

    verdict.safe = not verdict.reasons
    return verdict


def delete_run(
    verdict: Verdict,
    rows: list[SpuriaRow],
    *,
    ddb: Any,
    s3: Any,
    table: str,
    bucket: str,
    base_prefix: str,
) -> tuple[int, int]:
    """Delete the run's rows and its S3 prefix. Returns (rows, objects) deleted.

    Never touches SQS: an undrained filler message is discarded by batch-trigger
    as stale once its row is gone, or expires with the queue's retention.
    """
    if not verdict.safe:
        raise CleanupRefused("; ".join(verdict.reasons) or "verdict is not safe")
    run_id = validate_run_id(verdict.run_id)

    deleted_rows = 0
    changed: list[str] = []
    for row in rows:
        # Conditioned on the marker (only filler can go) and on the status the
        # verdict was based on (reconcile may have moved the row since).
        try:
            ddb.delete_item(
                TableName=table,
                Key={"chunk_id": {"S": row.chunk_id}},
                ConditionExpression="spuria_run_id = :r AND #s = :st",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":r": {"S": run_id}, ":st": {"S": row.status}},
            )
        except ddb.exceptions.ConditionalCheckFailedException:
            changed.append(row.chunk_id)
            continue
        except Exception as error:
            raise CleanupFailed(
                f"delete stopped at row {row.chunk_id}: {error}; S3 prefix left in place",
                rows_deleted=deleted_rows,
                objects_deleted=0,
            ) from error
        deleted_rows += 1
    if changed:
        # The pointer must outlive every row that still references it.
        raise CleanupFailed(
            f"{len(changed)} row(s) changed since the verdict and were kept; S3 prefix left in "
            "place. Re-run cleanup to reassess.",
            rows_deleted=deleted_rows,
            objects_deleted=0,
        )

    deleted_objects = 0
    prefix = f"{base_prefix.rstrip('/')}/spuria-{run_id}/"
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if not objects:
            continue
        response = s3.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
        errors = response.get("Errors") or []
        deleted_objects += len(objects) - len(errors)
        if errors:
            raise CleanupFailed(
                f"S3 refused to delete {len(errors)} object(s): {errors}",
                rows_deleted=deleted_rows,
                objects_deleted=deleted_objects,
            )
    return deleted_rows, deleted_objects

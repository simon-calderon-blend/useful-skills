# Cleanup safety

Batch-submit stamps `batch_job_id` (the job ARN) on every chunk it flips from PENDING to IN_BATCH. Reconcile then
moves each record of the finished job to DONE, FAILED or NEEDS_ONDEMAND, or re-queues it as PENDING. The batch-poller
only finds jobs through runs in `WAITING_FOR_BATCH`, so a job made only of filler is never reconciled, and its rows stay
IN_BATCH for good.

`padding-gate cleanup --run-id <id>` gives a verdict per run:

| Rows of the run | Verdict |
|---|---|
| all DONE / FAILED / NEEDS_ONDEMAND | SAFE: reconcile already processed them |
| any PENDING (or any status other than IN_BATCH or the three above) | blocked: the job has not formed. Deleting now keeps the gate shut for the real chunks |
| IN_BATCH without `batch_job_id` | blocked: the owning job is unknown |
| IN_BATCH, job not terminal (`Submitted`, `InProgress`, ...) | blocked |
| IN_BATCH, job terminal (`Completed`, `PartiallyCompleted`, `Failed`, `Stopped`, `Expired`), and **any real chunk of that job still IN_BATCH** | blocked: reconcile has not passed yet. In test those can be other people's claims |
| IN_BATCH, job terminal, no real chunk of the job still IN_BATCH | SAFE: either reconciled or pure filler |

All scans use `ConsistentRead`. A stale "0 rows" or "0 real chunks in flight" is exactly the read that would make an
unsafe delete look SAFE. A blocked dry run exits 2.

`--abandon-pending` lets PENDING rows through. It is for a failed inject only: rows written but never queued are
never moved by anything. IN_BATCH rows are still checked as above. If the rows did have messages, deleting them is
still harmless for real claims, because batch-trigger drops the messages as stale. It just undoes the padding.

`--apply` re-checks the verdict and refuses when it is not SAFE. It then deletes:

- each chunks row of the run, with `ConditionExpression spuria_run_id = <id> AND status = <status seen>`, so that
  only filler rows can go, and only if reconcile has not moved them since the verdict, and
- everything under `s3://.../audit-processes/spuria-<id>/` (the pointer and blank.pdf), but **only if every row went**.
  If any row changed, the pointer stays, because a live row without its pointer is released forever by batch-trigger.
  Exit 1, then re-run cleanup to reassess.

SQS is never touched. Once a filler message's row is gone, batch-trigger deletes the message as stale; otherwise it
expires with the queue's 4-day retention. The conveyor DLQ has `maxReceiveCount` 300, not 3.

Reconcile can still leave "ghost" `pdfs` / `runs` counter rows keyed by `spuria-<id>-pdf` / `spuria-<id>-1`. These are
harmless, and the tool does not remove them. The filler rows also carry a 30-day TTL (`expire_at`) as a backstop.

Note: in current CDK `main`, reconcile skips a record whose chunk row is missing (`chunk-not-found`) instead of
crashing. The gate stays conservative anyway, because deployed code can lag behind and a premature delete costs a
stuck run in a shared account.

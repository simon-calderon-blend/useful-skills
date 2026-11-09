# Mechanics

Sources: `adr-medicalAudit-pipelineCDK/lib/services/audit-orchestration/doc-extraction/` (main as of 2026-11-09) and the IAE
repo's `fill_spuria_conveyor.py` and `pipeline_runner/conveyor.py`. Re-check the code if behaviour looks different:
what is deployed can lag `main`.

## Why a small run stalls

`lambda-batch-trigger` runs every 2 minutes. On each tick it:

1. reads AppConfig `batch` and `storage` through the AppConfig agent (only deployed values count),
2. peeks `ApproximateNumberOfMessages` and returns if it is below `min_records_per_job`,
3. drains up to `max(min_records, min(max_records, max_job_size_mb / avg_record_size_mb))` messages,
4. drops duplicates and stale messages (row missing or not PENDING),
5. resolves each chunk's frozen run config through `run_id -> pointer -> body`
   (`<base>/<process_id>/<run_config_pointers><run_id>.json` holds `{"config_digest": ...}`,
   and the body is at `<base>/<run_configs><digest>.json`),
6. **groups chunks by `body.model.model_id`** and releases any group below `min_records`.

So filler only helps if it resolves to the same model as the real chunks. `padding-gate` takes the digest from the
pointer of the waiting real chunks (the most common one in the largest real group) instead of "the newest body".

Run-config bodies live under `_global/` and expire after 7 days. If no real run is waiting, there is no recent pointer,
and the tool refuses.

## How much

`count = (min_records - min(visible, model group total)) + 10`. The buffer of 10 is there because the peeked depth is
approximate and the drain discards duplicates. `--count` can only lower it, between 1 and the computed top-up. The tool refuses
when the queue is empty or when both the queue and the group already reach the gate.

## Timing

Padding before the run's own chunks have been queued fires a job of pure filler and leaves the real work for the next
job. There is no "all chunks queued" event, so `inject --apply` waits until the visible depth has not changed for
`--quiet-seconds` (300 s by default, polled every 30 s, giving up after `--max-wait` 1800 s). This is the same rule the
pipeline_runner watcher uses.

## What `inject --apply` writes (one run_id, 12 hex characters)

Written in this order. S3 and DynamoDB come before SQS, so a message never arrives before its row exists.

1. `s3://adr-<env>-medicalaudit-workarea/audit-processes/spuria-<id>/staging/document-extraction/run-config/spuria-<id>-1.json`
   -> `{"config_digest": <digest of the real chunks' run config>}`
2. `s3://.../audit-processes/spuria-<id>/chunks/blank.pdf`: a hand-built, valid, blank one-page PDF.
3. One row per filler chunk in `adr-<env>-medicalaudit-doc-extraction-chunks`, conditional on `attribute_not_exists(chunk_id)`:
   `chunk_id=spuria<id><32 hex>` (alphanumeric, because it becomes the Bedrock recordId), `pdf_id=spuria-<id>-pdf`,
   `process_id=spuria-<id>`, `run_id=spuria-<id>-1` (`rsplit("-",1)[0]` gives the process id back), `doc_code`,
   `chunk_index/page_start/page_end=1`, `chunk_s3_uri`, `status=PENDING`, `created_at`, `expire_at` (+30 days TTL),
   and the marker `spuria_run_id=<id>`. `pending_marker` is left out on purpose, so the poller's orphan sweep never
   re-sends filler.
4. One SQS message per row to `adr-<env>-medicalaudit-doc-extraction-chunks-conveyor`:
   `{"chunk_id", "pdf_id", "process_id"}` (Standard queue, batches of 10).

If a write fails or is interrupted (Ctrl-C included) part-way, the tool exits 1 (or 3 if the token expired) and prints
the run_id. Inspect it with `cleanup --run-id`. Rows whose SQS message was never sent stay PENDING forever, because
`pending_marker` is absent and the orphan sweep ignores them. Remove those with `cleanup --abandon-pending --apply`.

## doc_code

The doc_code must be in AppConfig `extraction.extractable_doc_codes` and not in `always_ondemand_doc_codes`
(read from the last COMPLETE deployment). It must also be in the pointed body's `documents`. In current batch-trigger
code, an unknown code FAILs that one chunk (drop-one) instead of aborting the whole drain, as it did before
2026-08-28. Either way the filler would be wasted, so the tool refuses. `ADM` is the blandest real code.

## AppConfig resolution

The application is matched by exact name, `adr-<env>-medicalaudit-doc-extraction-appconfig`, because dev also has
`e1-...` copies. For each of `batch`, `storage` and `extraction`, the tool takes the newest deployment in state
COMPLETE and reads that hosted version. The newest hosted version may never have been deployed.

## Cost

About 2,000 input and 200 output tokens per record at Sonnet-class batch rates: roughly US$0.0045 per record, or about
US$0.40 per 100 records. Treat this as an estimate only.

## Accounts and guards

`--env` maps to a fixed account (dev 072055531089, test 276553701208). STS must return exactly that account. Profiles
whose name contains PROD, MASTER, SECURITY or SENSITIVE, and `civileza-prod` / `civileza-mpa`, are refused before any
AWS call. Resource names come only from `--env`, and there are no override flags.

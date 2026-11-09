---
name: launching-iae-pipeline-runs
description: Use when launching, relaunching or dry-running Intelligent Audit Engine (IAE) claims ("radicados", "reclamaciones") through the medical-audit pipeline in dev or test, reusing a previous run (process_index.csv) or a local structuring ("estructuración", 200_soportes_estructurados) to skip doc-extraction, or when someone mentions pipeline_runner, POST /iniciar, idProcessIA, the dispatch flag, precargar.py or seeding audit-processes/<pid>/.
---

# launching-iae-pipeline-runs

Self-contained replacement for the IAE `scripts/pipeline_runner`. Run each script as
`uv run --project <skill>/scripts python <skill>/scripts/<x>.py`:

- `preflight.py`: read-only checks.
- `prepare.py`: writes `plan.json` and a `plan_id`.
- `launch.py`: dry-run unless `--execute`.
- `monitor.py`: tracking and download.

Never use the runner, `precargar.py` or `--smoke`.

**Every value comes from the user or from a live read.** Ask each decision with AskUserQuestion, in order.
`prepare.py` requires all of them.

## Decisions

1. **Env and profile.** `dev`/`ADR-DEV-MEDICALAUDIT` or `test`/`ADR-TEST-MEDICALAUDIT`, nothing else.
   Profiles containing PROD, MASTER, SECURITY or SENSITIVE are read-only. Check with
   `aws sts get-caller-identity --profile X`. On an expired token, ask the user to run `awsl`; never run it
   yourself and never use `aws sso login`.
2. **Claim source.**
   - `--source-dir D --claim A …`: local `000_reclamacion_cruda/`. Confirm the ids parsed from each folder
     name (preflight prints them).
   - `--source-index runs/<run>/process_index.csv`: whole claims from previous pids in the same env.
3. **`--structuring`:** `none`, `local[:<200_ dir>]`, `workarea` (index mode), `workarea:<pid>` or
   `mai:<run-id>`. Reuse copies the artifacts plus a `consolidated.json` marker, so doc-extraction skips.
4. **AppConfig and tracker_data.** Show what preflight read: the dispatch flag and who closed it,
   `maxMessagesPerCycle`, the qualifier compared with the AgentCore endpoints, and duplicates (test).
   Anything beyond the launch pause needs explicit consent: `--allow-open-dispatch`, or a qualifier change
   (then wait at least 5 min before dispatching).
5. **`--request`:**
   - `api`: the API writes it from the body.
   - `local`: validated against the schema; overwrites the API's copy.
   - `source`: the previous pid's original, used as the exact POST body.
6. **`--invoice`:**
   - `lambda`: not seeded, so the fetch Lambda calls SIA.
   - `source`: from the previous pid, checked against `SER_*`.
   - `local` or `ser`: seeded. Any seeded file suppresses SIA.

## Flow

1. Run preflight under the asm-exec command it prints, so the token, `aud` and API checks run. Stop on any
   `FAILED`.
2. `prepare.py …`: show the summary, the `plan_id` and the launch command.
3. `launch.py --plan runs/<R>/plan.json`: dry-run. Show the action list.
4. After the user confirms in chat, run the printed `… launch.py --execute --plan-id <id>`.
   - The script picks a working asm-exec. Never call `get-secret-value`.
   - It POSTs only after the throttle controller logs `Dispatch feature flag is OFF` following the close.
     A fixed sleep is not enough, because the AppConfig cache is stale after the container thaws.
5. `monitor.py --env E --run-dir runs/<R>`. Say "launched" only when `launch_report.json` shows every claim
   `RECIBIDO` and seeded, and the executions exist.
6. To relaunch: `--stop-run runs/<R> --execute` (tracker becomes `SF_ABORTED`), then
   `--execute --leave-dispatch-closed`, then `--open-dispatch --execute`.

Batches under 100 chunks stall at the Bedrock gate: use the `padding-bedrock-batch-gate` skill.

## Red flags: stop

- Treating `pipeline_runner --dry-run`/`--smoke` as read-only. They create an IAM role and a Lambda, and
  pause dispatch.
- POSTing without the controller's `OFF` line.
- Building the claim list with `ls`/`$(ls …)`.
- Copying IDs, buckets, the API or the bastion from the repo or another env.
- Copying `200_` without the marker.
- Seeding `claim_invoice_details.json` when SIA should answer.
- Re-running `--execute` before reading `launch_report.json` and the breadcrumb.

Details:

- [reference/decision-matrix.md](reference/decision-matrix.md): options, sources, file:line.
- [reference/common-errors.md](reference/common-errors.md): check ↔ the real error it prevents.

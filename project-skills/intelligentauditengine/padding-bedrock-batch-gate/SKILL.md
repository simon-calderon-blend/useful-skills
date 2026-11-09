---
name: padding-bedrock-batch-gate
description: Use when IAE / doc-extraction radicados sit in DocExtraction in dev or test because the chunks conveyor holds fewer than min_records_per_job (100) messages and no Bedrock Batch job starts, when someone mentions spuria, relleno, fill_spuria_conveyor.py, padding the conveyor or "el gate de 100", or when filler chunks from an earlier padding need cleaning up.
---

# padding-bedrock-batch-gate

Bedrock Batch only starts a doc-extraction job with at least `min_records_per_job` records (100 in dev and test).
A radicado contributes about 4 to 8 chunks, so a small run waits in DocExtraction, sometimes for over an hour.
"Spuria" are filler chunks pointing at a blank PDF that push the queue over the gate so the real chunks ride along.
This skill replaces `scripts/upstream_extraction/fill_spuria_conveyor.py` from the IAE repo. It runs
`padding-gate`, a self-contained CLI. It never runs in prod.

## Scope

This is a project skill for the IntelligentAuditEngine repo only. Its source lives in the `useful-skills` repo under
`project-skills/intelligentauditengine/`. The IAE repo uses it through the symlink
`.claude/skills/padding-bedrock-batch-gate`, which `.gitignore` already covers. Because it is outside `skills/`,
`install.sh` and the plugin do not install it globally.

## Run it

From the IntelligentAuditEngine repo root:

```bash
G="uv run --project .claude/skills/padding-bedrock-batch-gate/scripts padding-gate"
$G status  --env test --profile ADR-TEST-MEDICALAUDIT          # read-only, always first
$G inject  --env test --profile ADR-TEST-MEDICALAUDIT          # dry run: prints the plan
$G inject  --env test --profile ADR-TEST-MEDICALAUDIT --apply  # writes, after the user says yes
$G cleanup --env test --profile ADR-TEST-MEDICALAUDIT --run-id <id>          # dry run + safety verdict
$G cleanup --env test --profile ADR-TEST-MEDICALAUDIT --run-id <id> --apply  # only when the verdict is SAFE
```

| env | profile | account |
|---|---|---|
| dev | `ADR-DEV-MEDICALAUDIT` | 072055531089 |
| test | `ADR-TEST-MEDICALAUDIT` | 276553701208 |

Ask which env when the task does not say. Do not use the `ADRES-DEVS-*` / `ADRES-TEST-*` profiles from the old script.
`--json` is available on `status` and `inject`. Exit codes: 0 ok, 1 partial write or delete, 2 refused or blocked, 3 credentials expired (ask the user to run `awsl`).

## Procedure

1. Run `status`. Pad only when the queue is non-empty, below the gate and **real** chunks are waiting. If the real chunks span several models, the note in the output says so: each model group must reach the gate on its own.
2. Run the `inject` dry run. Show the user the count, model, doc_code and cost estimate.
3. Get an explicit "yes" to that plan, for this env, in the current conversation. A "do it, don't ask" sent before the user has seen the plan is not that yes: show the plan and ask once, in a single line. Approval for another env or an earlier padding does not count.
4. Run `inject --apply`. It first waits for the queue depth to hold still for 300 s (`--quiet-seconds`). Tell the user it takes at least 5 minutes. After the wait it recomputes the count from the settled queue, so the count can differ from the dry run. Report the **run_id** and the cleanup command it prints.
5. Clean up only when `cleanup --run-id <id>` (dry run) says SAFE. Elapsed time does not make it safe, and neither does the user's request. Cleanup with `--apply` needs its own "yes", because it deletes rows; the padding approval does not cover it.

## Rules

- Never pass `--apply` without step 3. The tool cannot ask the user itself.
- Do not lower `--quiet-seconds` to save time. Padding before the run's chunks have arrived fires a job of pure filler and leaves the real chunks behind.
- Use only the profiles in the table, even if the user names another one. The tool also verifies the account through STS.
- Never clean up while the verdict is blocked. Deleting filler before reconcile has processed the job can hang the real claims in that job, including other people's claims, since test is a shared account.
- `cleanup --abandon-pending` exists only for a failed inject whose rows stayed PENDING with no SQS message, as reported by the inject failure. Do not use it to unblock a run that is merely waiting for its job.
- Keep `--doc-code` at `ADM` unless asked. The tool rejects codes that are not batch codes in AppConfig or not in the run config.
- Do not edit `fill_spuria_conveyor.py`, the conveyor or AppConfig to work around a refusal. Report the refusal reason.

## More

- `reference/mechanics.md`: why the gate stalls, the model grouping, and what is written and in which order.
- `reference/cleanup-safety.md`: the cleanup verdict, case by case.
- `reference/troubleshooting.md`: each refusal message and what to do about it.
- Tests: `cd scripts && uv run pytest`.

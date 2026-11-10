# Troubleshooting

| Message / exit | Meaning | Do |
|---|---|---|
| `refused: refusing sensitive profile` (2) | profile name looks like prod, master, security or sensitive | use `ADR-DEV-MEDICALAUDIT` / `ADR-TEST-MEDICALAUDIT` |
| `refused: profile resolves to account X, but env ... is account Y` (2) | wrong profile for the env | fix `--profile` or `--env` |
| exit 3, "credentials expired" | SSO token expired or missing | ask the user to run `awsl` (it needs a browser); do not run it yourself |
| `no AppConfig application named ...` | app missing or renamed | check `adr-<env>-medicalaudit-doc-extraction-appconfig` exists; `e1-...` copies are ignored on purpose |
| `profile 'x' has no COMPLETE deployment` | a deployment of batch, storage or extraction is in progress or rolled back | wait for it, or ask the owner; do not deploy AppConfig yourself |
| `the conveyor queue is empty` | nothing is waiting, or the job already drained | check Step Functions or the batch job instead; padding cannot help |
| `no real chunk is PENDING with a resolvable run config` | only filler is waiting, or the real runs have no pointer (started before StageRunConfig, or the body expired after 7 days) | nothing to carry; do not pad |
| `... already reach min_records_per_job` | the gate will trip on the next tick | wait about 2 minutes; if no job starts, look at the capacity broker reservations, not at padding |
| `... has no document profile for 'X'` / `not a batch doc_code` | wrong `--doc-code` | use `ADM` |
| `--count must be between 1 and N` | `--count` above the computed top-up | omit `--count`; more filler only adds cost |
| `queue depth did not settle` | producers still adding chunks after `--max-wait` | rerun later, or lower `--quiet-seconds` only if the user accepts the risk of a pure-filler job |
| `FAILED: write failed part-way` (1, or 3 if the token expired) | S3, DynamoDB or SQS error, or Ctrl-C, mid-write | run `cleanup --run-id <printed id>` to see what exists. If its rows sit PENDING with no message, ask the user, then run `cleanup --run-id <id> --abandon-pending --apply`. Do not retry blindly, since a retry pads twice |
| `FAILED: N row(s) changed since the verdict` (1) | reconcile moved rows during cleanup | re-run the cleanup dry run; the S3 prefix was kept on purpose |
| `refusing to run with endpoint overrides set` (2) | `AWS_ENDPOINT_URL*` variables are set (LocalStack, floci...) | unset them; the tool only talks to real dev/test |
| cleanup `blocked: ... PENDING` | the job has not formed | wait; if it stays PENDING for hours, run `status` and check the gate and model groups |
| cleanup `blocked: job ... InProgress` | Bedrock is still running | wait for the job |
| cleanup `blocked: ... real chunk(s) are still IN_BATCH` | reconcile has not processed the finished job | wait for batch-poller/reconcile (minutes); never force it |

Queue above 100 but no job: padding is not the issue. Look at the capacity broker (`ondemand-capacity` profile and its
reservations) and the batch-trigger logs.

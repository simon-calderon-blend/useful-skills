# Common errors and the checks that prevent them

These are mined from 73 Claude Code sessions on the IAE repo (2026-09-25 to 2026-11-06). The counts are of
distinct sessions where the error showed up in real tool output. Each check name matches the
`preflight.py` JSON output.

| Check | Real error (verbatim where possible) | Root cause | Sessions |
|---|---|---|---|
| `claims_exist` | `Radicados not found in ../../runs/e2e_test_input: Permissions, Size, User, Date…` | `--claim $(ls …)` where `ls` is aliased to eza/rtk (header, trailing `/`); zsh does not word-split | 6 (2 broke real launches) |
| `appconfig_live`, `dispatch_strategy` | `ResourceNotFoundException: DeploymentStrategy with Id npbsudp could not be found` / `Hosted Configuration Version … could not be found` / `Environment Id 0lloxzq test could not be found` | IDs copied across accounts or profiles | 5 |
| `appconfig_live`, `runtime_qualifier` | repo `"qualifier": "DEFAULT"` vs live `v4_15_3`; config present in a hosted version but "not deployed" | terraform creates hosted versions but does not deploy them; live edits | 4 |
| `batch_gate_estimate`, `conveyor_depth` | `gate: queue has 82 < 100`; executions in `DocExtraction` for 1.5 h | Bedrock Batch `min_records_per_job: 100` | 4 |
| `token_audience` | `Consulta a FUCTAS fallida: HTTPError (HTTP 401)` with execution SUCCEEDED; `Token audience does not match` | Keycloak audience mapper empty or lost | 4 |
| `aws_identity`, `sso_session_remaining` | `Token has expired and refresh failed`; `poll_failed` mid-run | SSO session expired; waits have no time limit | 4 |
| `prerequisite_globs` | `ClaimNotEligibleError {"rejections":[{"id":"factura-obligatoria","glob":"FAC_*.pdf"…` | `FACT_` vs `FAC_`; rule patched live (repo copy stale) | 3 |
| `count_throttle` (+ single poller in `monitor.py`) | `ERROR <radicado> wait: failed (error)`, `outcome=error, arn=?` for 25–47 claims | one `ListExecutions` paginator per thread → `ThrottlingException` | 2 |
| `claims_exist` | `ground_truth directory not found` | default `--source-dir ground_truth/` is a DVC folder that is not checked out | 2 |
| `profile_in_aws_config` | `ProfileNotFound: The config profile (ADRES-TEST-MEDICAL-AUDIT-1) could not be found` | stale profile name in runner/AGENTS.md | 1 |
| `dispatch_flag` | 24/24 claims `execution_not_started` for 23 min; runner exit 0, `failures: []` | dispatch was already `False`; the runner restores "as found" and never opened it | 1 |
| `large_pdfs` | `errorCode: 413, "Input is too long"` → `DocExtractionIncomplete` | 317 MB PDF with 14 pages | 1 |

## Errors found while building the skill (real test launch, 2026-11-09)

| Check / guard | Real error | Root cause |
|---|---|---|
| `dispatch_off_confirmed` (launch waits for the controller's `OFF` log) | `000003_1332` re-extracted (`trigger: first_run`). It was dispatched at 17:17:16Z, 109 s after the close deployment completed and before its seeding finished. | The AppConfig extension serves a stale value after the container thaws; a fixed settle does not guarantee the pause |
| `bastion_online` (live jump host) | `describe-instance-information` returned nothing; `StartInstances`: `Instance does not have a volume attached at root (/dev/sda1)` | static bastion ids are dead |
| `client_secret_present` (asm-exec selection) | `asm-exec: ERROR: Failed to resolve: adr-test-medicalaudit-scriptconnection:SecretString:secretapi` | `/usr/local/bin/asm-exec` calls the removed MCP tool `aws___call_aws` |
| `dispatch_flag` detail (`maxMessagesPerCycle`) | 10 of 11 executions found; the 11th was still in `api-sqs` | the per-cycle limit is 10 in test |
| `runtime_qualifier` vs endpoints | the qualifier changed to `v4_16_1` mid-session (deployment 49) without the launcher knowing | `runtime` is edited live; read it at plan and execute time |

## Decision mistakes the flow prevents

| Mistake | Guard |
|---|---|
| Folder name not matching the template → `abs(hash(name)) % 10**9` as `idReclamacion` (909656568, `nombreEntidad: null`), different every run (`RUNNER/cli.py:341`) | `claim_id_parses` fails, no hash fallback |
| A local `000_/request.json` overwrote the one the API wrote (radicado 3123) | `request_json_override` plus decision 4 |
| Reusing structuring by copying `200_` → extraction ran anyway | marker `consolidated.json` in `work.consolidated`; `structuring_source` |
| `sourcePrefix`/`skip_extraction` (retired) → API refuses | not used; prefixes are seeded directly |
| Invoking `api-init-process` directly → messages left in `api-sqs` (kept 14 days) relaunch on reopen | only `POST /iniciar` through the API |
| Shared test env: other people's processes in our batch (117 records vs 94) | `running_executions`, `conveyor_depth` |
| `--skip-delivery` assumed to be a no-op | server forwards `skip_delivery` in test (`CDK/.../lambda-init-handler/index.py:432-433`); rejected elsewhere |
| Reporting "launched" before checking | launch counts as done only with `RECIBIDO` + seeded in `launch_report.json` |
| `pipeline_runner --dry-run` / `--smoke` treated as read-only | they create an IAM role + Lambda; `--dry-run` pauses (in test, closes) dispatch. Not used. |
| Duplicate in test within 48 h → `estado != RECIBIDO` | `tracker_duplicates` |
| Orphaned pause from a killed run | `foreign_breadcrumb` + `launch.py --recover` |
| Seeding `claim_invoice_details.json` when SIA should answer | decision `--invoice lambda` (not seeded) |
| Relaunching without stopping the previous run → duplicate within 48 h | `launch.py --stop-run` + check that the tracker is terminal |

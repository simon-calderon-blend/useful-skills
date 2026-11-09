# Decision matrix

Paths: `RUNNER` = `IntelligentAuditEngine/scripts/pipeline_runner/src/pipeline_runner/`, `CDK` =
`adr-medicalAudit-pipelineCDK/` (read at `develop@4a0090b9`, 2026-11-09). Runner references describe the
behavior this skill replaces.

## 1. Environment and profile

| Option | Account | Notes |
|---|---|---|
| `dev` / `ADR-DEV-MEDICALAUDIT` | 072055531089 | No duplicate check on `POST /iniciar`. Has infra-copy apps `e1-adr-dev-medicalaudit-*`: resolve by exact name. |
| `test` / `ADR-TEST-MEDICALAUDIT` | 276553701208 | Shared. Duplicate check of 48 h. After the batch, dispatch is left closed (`CLOSE_MARKER`). The runner's `ADRES-TEST-MEDICAL-AUDIT-1` (`RUNNER/environments.py:93`) does not exist in `~/.aws/config`. |
| prod | none | Not supported (the runner refuses it too, `RUNNER/environments.py:13-15`). |

**Claim source**: `--source-dir` (local `<claim>/000_reclamacion_cruda/`) or `--source-index` (a previous run's
`process_index.csv`; every `s3uri` must be in the live workarea bucket of the same env). In index mode,
`raw/` documents, artifacts and `consolidated.json` are copied server-side from the previous pid.

The API is private: Deny unless `aws:SourceVpce` (`CDK/lib/services/audit-api/api-stack.ts:292-311`).
Transport is an SSM port-forward. The jump host is resolved live:
1. Use the configured bastion if SSM reports it `Online`.
2. Otherwise use any SSM-Online instance in the API VPC, derived from the env subnets, preferring `bastion`
   names.

As of 2026-11-09 the configured bastions were dead. Test `i-07eb9e02496576639` was stopped with no root
volume. Dev `i-068050b46fe0feabb` was stopped. The working test host was `i-0a16f8e4c644e2af5`. The probe
`GET /proceso/<uuid4>` must return 404. The transport needs `aws` + `session-manager-plugin` and creates no
resources. Keycloak is public:
`https://iam.test.ia.adres.gov.co/realms/master/protocol/openid-connect/token`, `client_credentials`, client
`adr-<env>-medicalaudit-radicador`. The secret `adr-<env>-medicalaudit-scriptconnection` has the key
`secretapi` and is resolved only through `asm-exec`. The script picks a binary that uses the MCP tool
`aws___run_script`. `/usr/local/bin/asm-exec` from older plugin versions calls the removed
`aws___call_aws` and always fails with "Failed to resolve". The token must carry
`aud = adr-<env>-medicalaudit-intelligent-audit-engine-api`.

## 2. Structuring (estructuración)

How the skip works: the extraction dispatcher reuses when `<base>/<pid>/<work.consolidated>consolidated.json`
exists (dev/test only, `CDK/.../lambda-extraction-dispatcher/index.py:72,176-209`). Artifacts without the
marker are re-extracted. With the marker and zero artifacts the stage is SUCCEEDED with an empty 200.
The engine reads 200 from `staging/document-extraction/artifacts/` (`engine_ingest_mappings`), not from the
runner's `staging/structured` (`RUNNER/seed_layout.json`).

| Option | Source | What is seeded (live prefixes) | Requirements |
|---|---|---|---|
| `workarea` (index mode) | the row's previous pid | server-side copy of `artifacts/` + `consolidated.json` | the source exists. Verified 2026-11-09: 11/11 got `trigger: cached`, except one dispatched before its seeding finished (see dispatch below). |
| `none` | n/a | nothing; doc-extraction runs | small batches: see `padding-bedrock-batch-gate` |
| `local[:dir]` | `<claim>/200_soportes_estructurados/` or given dir | `NNN_CODE_x.json` → `output.structured/CODE_x.json` plus a generated marker | ≥1 `.json`; no name collisions after stripping `NNN_` |
| `workarea:<pid>` | `<base>/<pid>/` in the same env bucket | server-side copy of the artifacts; copies `consolidated.json` if present, else generates one (transient, 7-day lifecycle) | the source pid must belong to the same radicado |
| `mai:<run-id>` | `adr-medical-audit-executions-local-mai` (dev) / `adr-test-medical-audit-executions-local-mai` (test), `runs/<run-id>/<folder>/200_soportes_estructurados/` | same as local, server-side | folder equals the claim |

`raw/` always comes from the local `000_reclamacion_cruda/` of the same claim, so documents and artifacts
never mix claims (the reason the staging machine dropped level 0, `CDK/.../artifact-staging/README.md`).

## 3. AppConfig and tracker_data (read; change only with consent)

| Item | Where | Read how |
|---|---|---|
| dispatch flag | `adr-<env>-medicalaudit-throttle-controller-appconfig` / `dispatch` → `values.dispatch.enabled` | last COMPLETE deployment (the runner reads the latest *hosted* version, `RUNNER/dispatcher.py:147-163`) |
| who closed it | Description of the last `dispatch` deployment contains `pipeline-runner: dispatch closed after batch` | `list_deployments` |
| storage prefixes | `api/storage.output.intake`, `doc-extraction/storage.output.structured` + `work.consolidated`, `fetch-claim-invoice-details/storage.output` | deployed versions |
| engine mapping | `intelligent-audit-engine` / `engine_ingest_mappings`; also `runtime.qualifier` | deployed; newer undeployed hosted versions exist (terraform does not deploy) |
| runtime qualifier | `intelligent-audit-engine` / `runtime.qualifier` = the AgentCore endpoint name of `adr_<env>_medicalaudit_intelligent_audit_engine` | deployed plus `list_agent_runtime_endpoints`. Changing it is a separate user decision. The invoker extension polls every 5 min (`IAE/infra/modules/invoker-lambda/variables.tf:56-60`), so wait at least 5 min before dispatching. |
| prerequisites | `prerequisite-engine` / `minimum-requirements` | deployed. In dev it differs from the repo (`documento-clinico-obligatorio` removed live). |
| tracker_data | DynamoDB `adr-<env>-medicalaudit-tracker-data`, GSI `claim_id_created_date_index` | test: newest row < 48 h with a non-terminal status → `POST /iniciar` is rejected (`CDK/.../lambda-init-handler/index.py:298-315`). The skill never writes it. |

The launch pause writes a new hosted version plus a deployment (0-bake strategy). The pause is effective
only when `/aws/lambda/adr-<env>-medicalaudit-api-throttle-controller` logs
`Dispatch feature flag is OFF — skipping dispatch` after the deployment completed.

The controller runs every 2 minutes (CDK `config/environments/*.ts`, `throttleCheckIntervalMinutes`). Its
AppConfig extension serves the cached value on the first invoke after the container thaws. Real case: the
close completed at 17:15:27Z and 3 executions still started at 17:17:16Z.

`maxMessagesPerCycle` is 10 in test, so 11 claims dispatch over two cycles.

Recovery breadcrumb: `~/.local/state/launching-iae-pipeline-runs/paused-<env>.json`.

## 4. request.json

The init handler always writes it from the POST body to `<base>/<pid>/<intake>request.json`
(`CDK/.../lambda-init-handler/index.py:258-276`). Schema:
`CDK/lib/services/audit-api/models/iniciar-request.model.ts:24-97`. It requires `idReclamacion` and
`idSolicitud` (integers). `soportes`, if present, needs `rutaArchivosObligatorios` and
`rutaArchivosSoportes`. `idSoporte` is integer or null. `skipDelivery` is accepted only in test.

| Option | Effect |
|---|---|
| `source` (index mode) | the original `raw/request.json` of the previous pid is the exact POST body and is copied byte for byte. Runner-made runs have runner-fabricated originals (ids from the folder name, fake rutas). |
| `api` | The body is built from the folder name (template `<ignore>_<numero>` or `--name-regex`) and the API writes request.json. A local `000_/request.json` is not seeded. |
| `local` | The local file is validated against the schema; its ids must match the body. It is seeded and overwrites the API's copy. |

## 5. claim_invoice_details.json

The seeded file goes to `<base>/<pid>/<fetch-claim-invoice-details output>claim_invoice_details.json`. If it
exists, the SIA fetch is skipped (`CDK/.../fetch-claim-invoice-details/.../index.py:198-203`). If it is
missing, `RuntimeError("SER ausente…")` is a hard stop.

| Option | Source | Requirement |
|---|---|---|
| `lambda` | not seeded: `fetch-claim-invoice-details` calls SIA (verified: the file appears about 10–15 s after the POST, with a different size from the old copy) | SIA must have the claim, else `SER ausente` stops the run |
| `source` (index mode) | previous pid's `raw/claim_invoice_details.json` | non-empty `detalles`; CUPS equal those of `SER_*` |
| `local` | `000_/claim_invoice_details.json` | non-empty `detalles` |
| `ser` | first `SER_*.json` in `000_` (port of `IAE/scripts/claim_invoice.py:58-81`) | non-empty `detalles` |

The runner always seeds this file, writing `{"detalles": []}` when it has no source, and that suppresses
SIA. This skill seeds it only when told to.

## 6. Relaunch

1. Stop the run's RUNNING executions (`launch.py --stop-run runs/<R> --execute`). The tracker becomes `SF_ABORTED`
   within seconds (verified), so the 48 h duplicate check accepts the new POST.
2. Optionally change the qualifier, then wait at least 5 minutes.
3. Run `launch.py --execute --leave-dispatch-closed`.
4. Run `launch.py --open-dispatch --execute`.

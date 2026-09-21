# Floci environment variables

| Variable | Default | Purpose |
|---|---|---|
| `FLOCI_HOSTNAME` | _(none)_ | Hostname embedded in response URLs. Set to the Compose service name in multi-container setups |
| `FLOCI_DEFAULT_REGION` | `us-east-1` | Region reported in ARNs and responses |
| `FLOCI_DEFAULT_ACCOUNT_ID` | `000000000000` | Account ID used in ARNs |
| `FLOCI_STORAGE_MODE` | `memory` | `memory`, `persistent`, `hybrid` or `wal` |
| `FLOCI_STORAGE_PERSISTENT_PATH` | `./data` | Directory for persistent storage |
| `FLOCI_SERVICES_DOCKER_NETWORK` | _(none)_ | Docker network for spawned containers (Lambda, ElastiCache, RDS, OpenSearch, MSK) |
| `FLOCI_AUTH_VALIDATE_SIGNATURES` | `false` | Verify S3 presigned URL signatures |
| `FLOCI_SERVICES_LAMBDA_EPHEMERAL` | `false` | Remove Lambda containers after each invocation |
| `FLOCI_SERVICES_LAMBDA_HOT_RELOAD_ENABLED` | `false` | Reload Lambda code on change (needs the Docker socket) |

The exhaustive list is `docs/configuration/environment-variables.md` in
https://github.com/floci-io/floci.

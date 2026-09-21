# Migrating from LocalStack

Swap the image for `floci/floci:latest-compat`. That image translates
LocalStack environment variables (`LOCALSTACK_HOST`, `PERSISTENCE`,
`LAMBDA_DOCKER_NETWORK`) automatically, so they keep their names and no
`FLOCI_*` equivalents are needed alongside them. The standard
`floci/floci:latest` image does not translate them; moving to it later means
renaming them per [env-vars.md](env-vars.md).

| Item | LocalStack | Floci |
|---|---|---|
| Image | `localstack/localstack` | `floci/floci:latest-compat` |
| Compose service name | `localstack` | `floci` (update `LOCALSTACK_HOST` to match) |
| Data volume path | `/var/lib/localstack` | `/app/data` |
| Init scripts | `/etc/localstack/init/ready.d` | unchanged |
| Health endpoint | `/_localstack/init`, `/_localstack/health` | both still work; native path is `/_floci/init` |
| Testcontainers artifact | `org.testcontainers:localstack` | `io.floci:testcontainers-floci` |
| Port, credentials, client config | `4566`, `test`/`test` | unchanged |

## Compose, before and after

```yaml
services:
  localstack:
    image: localstack/localstack
    ports: ["4566:4566"]
    environment:
      LOCALSTACK_HOST: localstack
      PERSISTENCE: "1"
      LAMBDA_DOCKER_NETWORK: myapp_default
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/var/lib/localstack
      - ./init/ready.d:/etc/localstack/init/ready.d:ro
```

```yaml
services:
  floci:
    image: floci/floci:latest-compat
    ports: ["4566:4566"]
    environment:
      LOCALSTACK_HOST: floci
      PERSISTENCE: "1"
      LAMBDA_DOCKER_NETWORK: myapp_default
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/app/data
      - ./init/ready.d:/etc/localstack/init/ready.d:ro
```

## CI

Change only the service name and image. Floci serves the LocalStack status
paths on every image, so an existing wait on `/_localstack/health` keeps working. Terraform provider blocks and SDK client
code need no change.

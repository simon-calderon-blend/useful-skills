---
name: floci
description: Runs and configures Floci (floci/floci), a free local AWS emulator serving S3, SQS, SNS, DynamoDB, Lambda, Secrets Manager, SSM and more on one endpoint, localhost:4566. Use whenever Floci is mentioned, when pointing the AWS CLI, an SDK, Terraform or CDK at a local endpoint to test AWS code without an AWS account, when running AWS integration tests in CI, when replacing or migrating from LocalStack, or when a Floci setup loses data on restart, returns localhost URLs to other containers, or fails to run Lambda.
---

# Floci

Floci emulates AWS locally. Existing AWS clients work unchanged once they point
at `http://localhost:4566` with dummy credentials. Floci is recent: take image
tags, `FLOCI_*` variables and paths from this skill, not from LocalStack habits.

## Quick start

```yaml
services:
  floci:
    image: floci/floci:latest
    ports: ["4566:4566"]
```

```bash
docker compose up -d
export AWS_ENDPOINT_URL=http://localhost:4566 AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
aws s3 mb s3://smoke-test && aws s3 ls   # smoke test
```

AWS CLI v2 and current SDKs read `AWS_ENDPOINT_URL`; pass `--endpoint-url` to
older tooling. Readiness endpoint: `GET /_floci/init`.

## Symptoms

| Symptom | Cause | Fix |
|---|---|---|
| Buckets, tables or queues vanish on restart, even with a volume mounted | Storage defaults to `memory` | [Persistence](#persistence) |
| Another container gets `localhost` queue or presigned URLs, then "Could not connect to the endpoint URL" | Floci does not know its own hostname | [Multi-container](#multi-container) |
| Lambda, RDS, ElastiCache, OpenSearch or MSK fail to start or are unreachable | They run as real containers | [Container-backed services](#container-backed-services) |
| S3 calls fail with `lookup <bucket>.localhost: no such host` | Virtual-hosted addressing | Enable path-style: see [references/clients.md](references/clients.md) |
| Terraform creates resources in real AWS | Service missing from `endpoints` | [references/clients.md](references/clients.md) |

## Persistence

Mounting a volume is not enough; the storage mode must change too, and the path
must be the container side of the mount.

```yaml
    volumes:
      - floci-data:/app/data
    environment:
      FLOCI_STORAGE_MODE: persistent          # memory (default) | persistent | hybrid | wal
      FLOCI_STORAGE_PERSISTENT_PATH: /app/data
volumes:
  floci-data:
```

## Multi-container

Floci embeds its hostname in the URLs it returns. Set `FLOCI_HOSTNAME: floci`
(the bare Compose service name, no port) so other containers can follow those URLs, and have
them use `http://floci:4566` as their endpoint.

## Container-backed services

Lambda, RDS, ElastiCache, OpenSearch and MSK are spawned as sibling containers,
so Floci needs the Docker socket and the network to attach them to. Give the
network an explicit `name` so the value is known, not derived from the directory.

```yaml
services:
  floci:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      FLOCI_SERVICES_DOCKER_NETWORK: appnet
    networks: [appnet]          # every service that calls Floci joins it too
networks:
  appnet:
    name: appnet
```

The socket gives Floci control of the host's Docker daemon, so mount it only on
dev machines and disposable CI runners.

## References

Read only the one the task needs.

- [references/clients.md](references/clients.md): configuring Go, Node, Python, Terraform or OpenTofu clients.
- [references/ci.md](references/ci.md): GitHub Actions service container, Testcontainers.
- [references/localstack-migration.md](references/localstack-migration.md): replacing an existing LocalStack setup.
- [references/env-vars.md](references/env-vars.md): every common `FLOCI_*` variable with its default.

## Done when

- [ ] `GET /_floci/init` succeeds and a CLI or SDK smoke test passes
- [ ] The app reads the endpoint from env or config in one place, enabled only
      behind an environment switch (`APP_ENV=local|test`), so production stays
      off the emulator and real credentials stay out of it
- [ ] Every AWS operation the feature relies on is confirmed in the Floci docs
      (it covers a subset of AWS), or has a recorded fallback (mock or real AWS)

# CI

## GitHub Actions

Run Floci as a service container, wait for readiness, smoke test, then run the
suite. The wait matters because service containers start before they are ready.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      floci:
        image: floci/floci:latest
        ports: ["4566:4566"]
    env:
      AWS_ENDPOINT_URL: http://localhost:4566
      AWS_DEFAULT_REGION: us-east-1
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
    steps:
      - uses: actions/checkout@v4
      - name: Wait for Floci
        run: timeout 60 sh -c 'until curl -sf http://localhost:4566/_floci/init; do sleep 1; done'
      - name: Smoke test
        run: aws s3 mb s3://smoke-test
      - name: Run tests
        run: make test
```

For Lambda and the other container-backed services, add the socket mount to the
service (`volumes: ["/var/run/docker.sock:/var/run/docker.sock"]`) and set
`FLOCI_SERVICES_DOCKER_NETWORK` as described in SKILL.md.

## Testcontainers (Java)

```xml
<dependency>
  <groupId>io.floci</groupId>
  <artifactId>testcontainers-floci</artifactId>
  <scope>test</scope>
</dependency>
```

Take the current version from Maven Central.

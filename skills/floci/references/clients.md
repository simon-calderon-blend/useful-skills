# Client configuration

All clients use region `us-east-1` and credentials `test` / `test`, and take the
endpoint from `AWS_ENDPOINT_URL`. The one setting that differs per client is S3
path-style addressing, which every S3 client needs against Floci:

| Client | Endpoint option | S3 path-style option |
|---|---|---|
| Node, AWS SDK v3 | `endpoint` | `forcePathStyle: true` |
| Python, boto3 | `endpoint_url` | not needed by default; if required, `Config(s3={"addressing_style": "path"})` |
| Go, AWS SDK v2 | `config.WithBaseEndpoint` | `o.UsePathStyle = true` |
| Terraform / OpenTofu | `endpoints { ... }` | `s3_use_path_style = true` |

## Go (AWS SDK v2)

Use `WithBaseEndpoint`; `WithEndpointResolverWithOptions` is deprecated. Apply
the overrides only when the endpoint is set, so the same code keeps the default
credential chain and virtual-hosted addressing in production.

```go
endpoint := os.Getenv("AWS_ENDPOINT_URL") // set only for local and test

opts := []func(*config.LoadOptions) error{}
if endpoint != "" {
    opts = append(opts,
        config.WithRegion("us-east-1"),
        config.WithBaseEndpoint(endpoint),
        config.WithCredentialsProvider(
            credentials.NewStaticCredentialsProvider("test", "test", ""),
        ),
    )
}

cfg, err := config.LoadDefaultConfig(context.TODO(), opts...)
if err != nil {
    log.Fatal(err)
}

client := s3.NewFromConfig(cfg, func(o *s3.Options) {
    o.UsePathStyle = endpoint != ""
})
```

## Terraform / OpenTofu

List the endpoint for every AWS service the configuration touches, including
`iam` and `sts` when roles are involved. A service left out is sent to real AWS.

```hcl
variable "endpoint" {
  type    = string
  default = "http://localhost:4566"
}

provider "aws" {
  region     = "us-east-1"
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true

  endpoints {
    s3             = var.endpoint
    sqs            = var.endpoint
    sns            = var.endpoint
    dynamodb       = var.endpoint
    lambda         = var.endpoint
    iam            = var.endpoint
    sts            = var.endpoint
    ssm            = var.endpoint
    secretsmanager = var.endpoint
  }
}
```

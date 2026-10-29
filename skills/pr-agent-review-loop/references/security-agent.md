# AWS Security Agent on GitHub PRs

## Identity and sequence
- Login `aws-security-agent[bot]` (`user.type == "Bot"`).
- On each push it first posts an issue comment: "AWS Security Agent is reviewing your pull request and will post feedback shortly." Then, minutes later (PR #190: 15:35 → 15:42 UTC), a review (`state: COMMENTED`) plus inline comments. It re-reviews after every push, so wait out the monitor round before declaring done.
- The "is reviewing" comment is informational: no reply needed.
- A clean re-review is NOT a review: it is another issue comment whose body is just "No issues identified." (PR #190, ~8 min after the push). That is the Security Agent's round-complete signal; no reply needed.

## Review body
Starts with `# Security Code Review Summary`: severity counts, the dominant theme, remediation priority, and "secondary hardening" questions. It is not a thread; answer its open questions in one top-level PR comment.

## Inline comment format
```
**Severity:** MEDIUM
**What is the issue?** ...  Verified: ... Not verified: ...
**Evidence:** source → hop (file:line) → ... → sink
**What is the recommendation?** ...
***To request automated fixes, ... "@AWS-Security-Agent fix all findings"***
***Provide feedback by reacting to this comment with :+1: or :-1:***
```
- Line numbers refer to `original_commit_id`; re-locate them in HEAD.
- Its "Not verified" list is where your triage adds most value: those claims usually concern code outside the diff (another repo, a broker) that you can read yourself.
- The automated-fix trigger needs code remediation enabled in the Agent Space; not used here.

## Seen in practice
PR #190 (doc-extraction `ondemand-capacity`), MEDIUM "unvalidated config maps reach the Capacity Broker":
- VALID as defence in depth: the Lambda took AppConfig maps verbatim. But part of its premise was imprecise: AppConfig JSON_SCHEMA validators DO run at `StartDeployment` (draft-04; only `const` is ignored) - https://docs.aws.amazon.com/appconfig/latest/userguide/appconfig-creating-configuration-and-profile-validators.html. The runtime check is a backstop, not the only gate.
- Its recommendation ("mirror the sibling's checks, require the concurrency bucket") had to be applied to the SCHEMA as well: requiring the bucket only at runtime made schema-valid profiles fail every run (caught by the adversarial cycle).
- "Not verified: broker rejects oversized/unknown buckets" → answered by reading the broker: it does (`_validate_demands`), but it does not dedupe duplicate entries.

PR #149 (promotion develop→test, 10 findings, fixed in #151). Corrections worth reusing if raised again:
- `/iniciar` is a PRIVATE API Gateway (VPCE + resource policy), not internet-facing.
- "Narrow the `ClientError` arm to 404" did not apply: `run_config._get_bytes` already maps NoSuchKey to `RunConfigNotFound`; the right fix was to delete the arm.
- An ownership check it asked for was not implementable: the dispatch payload carries neither `process_id` nor `run_id`.

PR #221 (develop → test promotion, 11 findings over 4 rounds, fixed in #225).

Format differences from #190:
- Some findings arrive as top-level ISSUE comments, not inline. They start with ``**`<file>`** (line N)`` and use the same Severity/Issue/Evidence/Recommendation blocks.
- The review body only counts findings, and the counts include those issue comments: "identified 4 security findings: 1 high, 3 medium" was 3 inline plus 1 issue comment.
- Collect findings from all three endpoints (`issues/<pr>/comments`, `pulls/<pr>/comments`, `pulls/<pr>/reviews`). Answer the issue-comment findings in one top-level comment.

Classifications, reusable if the same findings come back:
- FALSO POSITIVO: "grant `kms:GenerateDataKey*`/`kms:Decrypt` for an imported SQS queue that may be SSE-KMS". The queue, in the PACA repo, sets no `encryption`, so CDK defaults to SSE-SQS and no KMS is involved. Read the owning repo's queue definition.
- FALSO POSITIVO: "add `aws:SourceArn` and drop `kms:Decrypt`" on the SNS/EventBridge service-principal statements of the key policy.
  - AWS requires both `GenerateDataKey*` and `Decrypt` for EventBridge→SNS-KMS and SNS→SQS-KMS: https://repost.aws/knowledge-center/sns-not-getting-eventbridge-notification
  - `aws:SourceAccount` is the documented confused-deputy control: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-key-management.html
- FALSO POSITIVO (by design): "pin the ADRES `auth_url` path to `/auth/`". The repo documents `auth_url` as overridable per gateway (`lib/gateways/_shared/CLAUDE.md`), and the host is allowlisted at schema and runtime.
- VALID but partial: "decode `isBase64Encoded` + cap body". The cap applied. The base64 part does not: REST APIs only base64-encode request bodies when `binaryMediaTypes` is configured, which no gateway here does: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-payload-encodings.html
- YA RESUELTO: findings on ops scripts that a teammate deleted from the base branch while the loop ran (#224). Reply with the SHA that removed them.
- It also re-reviews on every push to the HEAD branch. On a promotion PR, any merge into `develop` counts, including other people's. A clean round is the issue comment "No issues identified."

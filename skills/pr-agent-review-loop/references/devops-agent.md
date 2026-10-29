# AWS DevOps Agent on GitHub PRs

## Identity and outputs
- Login `aws-devops-agent-us-east-1[bot]` (region suffix in the login; match with `aws-devops-agent-[a-z0-9-]+\[bot\]$`).
- Posts a review with an EMPTY body plus inline comments.
- Also owns the check run `aws-devops-agent/release-readiness-review` (link to `*.aidevops.global.app.aws/changes/<id>`). It goes back to `pending` ("analysis in progress") on every push.

## Inline comment format
```
<one-line imperative recommendation>

---

<one-line risk statement>

- **By design, not a regression:** ...
- **Mechanism:** ...
- **Unverifiable from this repo:** ...
- **Likelihood is low:** ... this is a confirmation ask, not a suspected defect.
<optional code block with operational steps>
```
The bold labels tell you its own confidence. "By design" / "no code change" / "confirmation ask" usually map to FUERA DE ALCANCE or FALSO POSITIVO, but still verify.

## Seen in practice (PR #190)
- "Seed the AppConfig profile in each env after deploy" → FUERA DE ALCANCE: an operational step already documented; reply with the doc and script lines.
- After the fix push it re-reviewed (new empty-body review, ~5 min) and re-raised the SAME seeding ask on a different file/line (`scripts/push-appconfig.sh:100`). Re-asks do not track your earlier reply: classify YA RESUELTO, reply pointing to the first thread, and correct any factual slip (it said "on-demand runs" fail; the entry state gates every run).
- "Confirm with the other team that array ordering doesn't matter to the broker" → FALSO POSITIVO after reading the broker repo locally: admission checks every demand (all-or-nothing) and persists the list in one `update_item`.

## Seen in practice (PR #221, develop → test promotion; fix PR #225)
- It posted NO review and NO comments, only the `release-readiness-review` check.
- The check read "change approved" (pass), went back to `pending` whenever `develop` moved, and returned to `pass` in about 2-5 min on both PRs.
- "No comments from this bot" is normal. Base the exit criterion on its check, not on waiting for a review.

## MCP server (`plugin:aws-agents-for-devsecops:aws-devops-agent`)
- HTTP 401 "Invalid or expired access token" is NOT an expired token: the plugin sends `Authorization: Bearer ${DEVOPS_AGENT_TOKEN}` and the variable is unset, and the account has no Agent Space (the Bearer token is issued from an Agent Space web app). Decision on record: leave it red; creating an Agent Space is billable and needs an account decision. Do not try to fix it inside this loop - use the GitHub comments and tell the user.
- `-32602 Invalid request parameters` from `aws-mcp` = expired AWS credentials (the `[default]` profile uses `aws login`, not `aws sso login`).
- The GitHub-side review and check keep working without the MCP.

## Related skills (Claude Code plugin `aws-agents-for-devsecops`; need the MCP servers above; not exercised in this loop)
`aws-agents-for-devsecops:analyzing-release-readiness` (the release-readiness check), `:chatting-with-aws-devops-agent`, `:investigating-incidents-with-aws-devops-agent`; for the Security Agent: `:diff-scanning-with-aws-security-agent` (scan a diff before pushing), `:remediating-with-aws-security-agent`, `:scanning-with-aws-security-agent`.

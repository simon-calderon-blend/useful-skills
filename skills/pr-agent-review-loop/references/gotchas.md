# Gotchas (verified)

> Verified in Claude Code sessions. Tool names below (`EnterWorktree`, `ListAgents`, `SendMessage`, Workflow, GateGuard, the rtk hook) are Claude Code's; on Codex/Kiro use the equivalent or skip. Sections tagged "(Claude Code)" do not apply elsewhere. Everything about `gh`, git, CI and the bots is tool-independent.

## Worktree
- Always work in the PR branch's worktree, never the main checkout. Another process has run checkout/pull/merge on the main checkout in parallel before.
- git refuses to check out a branch that another worktree already has. Reuse that worktree if `git status` is clean and HEAD == `origin/<branch>`, via `EnterWorktree(path=...)`.
- `.claude/worktrees/` is NOT gitignored: always stage explicit paths, never `git add -A`/`.`.
- Workflow/subagents may edit the main checkout even when handed worktree paths: set their cwd to the worktree and check `git diff` afterwards.

## git inside a worktree-isolated session (rtk hook present; Claude Code)
- The rtk hook rewrites `git ...` into `rtk git ...`, and the worktree-isolation guard refuses ANY rtk-wrapped git (`rtk git`, `rtk proxy git`, `git -C`), and any compound command with shell variables or loops that mention git/rtk.
- What works: the absolute binary, one plain command per call, literal args: `/usr/bin/git status --short`, `/usr/bin/git diff --output=<file>`, `/usr/bin/git push origin <branch>`.
- Outside such a session, prefer `rtk proxy git` for fetch/ls-remote/range logs/push: rtk's filtered output has shown impossible ref states and mangled `"$VAR:refs/heads/x"` refspecs.
- `gh` and `rtk` also reformat outputs (`gh pr checks` → "CI Checks Summary"): use `--json`/`--jq` for anything you act on.

## Publishing
- No force-push, ever; a plain push of new commits is a fast-forward.
- Never commit generated skill docs (`docs/superpowers/`); keep plans in the scratchpad.
- `gh api -X POST .../replies` echoes the full comment JSON; add `--jq .html_url`.

## CI
- A job that fails in ~2 s with zero steps and "log not found" is an Actions infrastructure failure. Read the annotations: `gh api repos/<o>/<r>/check-runs/<job-id>/annotations`. Seen 2026-09-28: "The job was not started because recent account payments have failed or your spending limit needs to be increased" - org-wide (develop failed too). Not fixable from the PR: classify FUERA DE ALCANCE and tell the user; re-run the job once billing is fixed.

## Subagents
- A subagent's report of edits/tests can be fabricated (a Workflow agent once reported 8 files and green tests; 3 were real). Verify with `git status`/`git diff --stat` and re-run the tests yourself.
- Adversarial reviewers are worth it: on PR #190, cycle 1 caught a runtime check stricter than its schema that the bot's own recommendation introduced, and cycle 2 caught that relaxing it re-opened the original risk. The fix was to tighten schema AND runtime from one constant.
- Ground AWS behaviour claims (yours, the bots', the reviewers') in official docs via the aws-knowledge MCP, and put the URL in the reply.

## Hooks you may hit (Claude Code)
- GateGuard ("Fact-Forcing Gate") blocks the first Edit/Write of each file and the first Bash of the session until you state importers/callers, affected API, data schema and the user's verbatim instruction; then retry the same call.

## Head is a shared branch (PR #221, develop → test promotion)
- You can't have a worktree on `develop` while the main checkout has it. Branch the worktree off `origin/develop` and ask the user how to land it. The choice made in #221: a fix PR into `develop` (#225), because pushing directly to a shared branch skips review.
- Reply in the threads of the promotion PR with the SHAs from the fix PR: "Fixed in `<sha>` (PR #N → develop; this PR picks it up on merge)".
- Watch BOTH PRs in the monitor. The bots review the fix PR too.
- The base can move under you while you work. In #221 a teammate merged #224, which deleted three scripts two of my unpushed commits had edited, so those findings became YA RESUELTO. Before pushing, run `/usr/bin/git fetch origin <base>` and then `/usr/bin/git log --oneline HEAD..origin/<base>`.
- If the base moved and the branch is still unpushed, rebuild it: `/usr/bin/git switch -c <fix-branch> origin/<base>`, then cherry-pick the commits you keep and drop the obsolete ones. That is not a force-push, because nothing was published yet.
- Another session may be working on the same PR, repo or skill. Before writing, check `ListAgents`, `gh pr list` and the target files' mtimes. Don't overwrite a peer's files; ask the user.

## More worktree-guard traps (in addition to the rtk rule above; Claude Code)
- A `cd` into another repo moves the session's primary directory, and `EnterWorktree(path=...)` then refuses a worktree of the original repo. Recover with a plain `cd <worktree>`. Read other repos by absolute path; never `cd` into them.
- The guard also refuses heredocs combined with `cd`, `sed`/`rtk` with shell variables, `$(command -v gh)`, and loops that call `rtk`/`gh` with variables.
  - Use Edit/Write instead of heredocs.
  - Use `uv --directory <dir> run ...` instead of `cd <dir> && uv run`.
  - Put loops in a script under the scratchpad and run it with `bash <script>`, calling gh by its absolute path (`which gh` once).
- `grep` gets rewritten to `rg` by a hook, so a POSIX `\|` regex fails. Use `/usr/bin/grep -E`.

## Session resume
- The scratchpad directory survives a session resume but its CONTENTS may not (seen: `pr221/` came back empty). Before relying on saved files after a resume, re-create the directory and re-derive anything you need: diffs, reply bodies, downloaded comments.
- Background subagents stop when the session ends. Resume them with `SendMessage(to=<agentId>)`; they keep their transcript.

## Verifying CDK without touching AWS
- `npx cdk synth --no-lookups -c environment=<env> --exclusively '<env>/<stack>' -o <scratchpad>/cdkout`
  - `--no-lookups` fails instead of calling AWS.
  - `--exclusively` bundles assets only for that stack, yet still synthesizes every template.
  - `-c aws:cdk:bundling-stacks=[]` is rejected, because user context can't use `aws:` keys.
- Then assert on the real template with `jq`. For example: did the IAM condition survive into the role in the stack that owns the state machine?

## AWS/CDK fix patterns verified on #221
- **AppConfig inline JSON Schema validators are draft 4.**
  - TypeBox `Type.Literal`/`Type.Union` of literals renders `const`, a draft-6 keyword that AppConfig ignores, so any string passes. Use `Type.String({ enum: [...] })`.
  - TypeBox `Type.Record` emits only `patternProperties`. Add `additionalProperties: false` or bad keys pass.
  - TypeBox `Value.Check` ignores `enum` on `Type.String`, so a seed test built only on `Value.Check` stops catching bad values. Check the values against the `enum` read from the published schema.
  - Other schemas in the repo still use `Type.Literal`: `doc-extraction` `effort`, `intelligent-audit-engine-capacity`, `prerequisite-engine`.
- **`CallAwsService` has no option for an IAM condition.** The statement is built from `iamAction` and `iamResources` only.
  - What works: `(task as unknown as {taskPolicies: iam.PolicyStatement[]}).taskPolicies[0].addCondition(...)`. Pin it with a jest assertion so a CDK upgrade can't silently drop it.
  - `PutMetricData` has no resource-level permissions, so it takes `Resource: "*"` plus the `cloudwatch:namespace` condition.
- A `States.ALL` Catch that leads to a `Pass` hides failures: the execution SUCCEEDS, so `ExecutionsFailed` never fires. If the branch must stay non-blocking, emit a metric from the state machine (`aws-sdk:cloudwatch:putMetricData`), alarm on it, and add a short Retry to the SDK tasks.

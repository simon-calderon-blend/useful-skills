---
name: pr-agent-review-loop
description: Use when a GitHub PR has review comments from AWS Security Agent (aws-security-agent[bot]) or AWS DevOps Agent (aws-devops-agent-*[bot]) or other review bots that must be closed out, or its CI must go green - "loop de comentarios de Security Agent / DevOps Agent en un PR", "dejar el PR sin comentarios de los bots", "cerrar hallazgos de seguridad del PR", "atender los comentarios del agente de seguridad/devops".
argument-hint: <pr#> <goal> [max_adversarial=3] [max_outer=5] [monitor_timeout=45m]
---

# PR agent review loop

Drive a PR until the review bots have nothing pertinent left and CI is green: verify every bot claim against the real code, fix only what is valid, try to break your own fix, publish, answer every thread, then watch for the bots' next round.

**Core principle:** a bot comment is a hypothesis about the code, not an instruction. Nothing is fixed, dismissed or replied to until you have read the code (and, for AWS behaviour, the docs) yourself.

Arguments: `<pr#>` `<goal>` (e.g. "cerrar hallazgos de seguridad", "dejar CI verde" - it decides what counts as pertinent) and optional caps `max_adversarial` (3), `max_outer` (5), `monitor_timeout` (45m). They come from the slash command, or from the user's message when the harness has no argument passing.

**Portability:** this skill runs unchanged on Claude Code, Codex and Kiro. Each step states the goal and names the Claude Code tool only as an example; where your harness lacks it, use the stated fallback. `<skill-dir>` is the directory holding this SKILL.md (`~/.claude/skills/`, `~/.codex/skills/` and `~/.kiro/skills/` `pr-agent-review-loop` are the same directory through symlinks). "Scratchpad" is the session's temp dir (`mktemp -d` when the harness gives none).

## Hard rules

- Work in the PR branch's worktree only; never edit the main checkout. See `references/gotchas.md` for how git behaves inside a worktree-isolated session.
- No force-push, no rebase/merge of the base branch unless CI fails because of it and the user agrees. "N commits behind" / `mergeable=UNKNOWN` is not a bot comment.
- Never resolve review threads and never merge the PR - reply and leave them for the human.
- Never trust a subagent's report of edits or test runs; check `git status`/`git diff` yourself.
- Fix only VALID findings; no adjacent refactors.

## Flow

### 0. Context (read-only)
1. Confirm the PR number and head branch (`gh pr view <pr> --json headRefName,baseRefName,author,state`). If the user's text names two PRs, ask. If the head branch is a shared branch (`develop`, `test`, `main`) or another author's, ask before planning any push.
2. Worktree: isolate the work in a worktree of the PR branch. Use your harness's worktree skill or tool if it has one (Claude Code: `superpowers:using-git-worktrees`), otherwise `git worktree add <path> <branch>`. If the branch is already checked out elsewhere (`git worktree list`), git refuses a second worktree: reuse it only if clean and at `origin/<branch>`; work from it (Claude Code: `EnterWorktree(path=...)`; elsewhere run every command with that path as cwd). If it is dirty or diverged, it is someone's work in progress: stop and ask.
3. Download, into the scratchpad: `pulls/<pr>/reviews`, `pulls/<pr>/comments` (inline), `issues/<pr>/comments`, and `gh pr checks <pr> --json name,state,bucket,link`. Group by `.user.login` to get the bot logins (the monitor filters on them). Bot formats: `references/security-agent.md`, `references/devops-agent.md`.
4. MCP status: if the devops-agent MCP is 401, do not fix it - continue with the GitHub comments and tell the user.

### 1. Triage (verify before acting; Claude Code: load `superpowers:receiving-code-review`)
For each comment/failed check: open the cited code (lines drift - the bot's snippet is from `original_commit_id`), follow the data flow it claims, and for AWS claims read the official doc (aws-knowledge MCP if configured, otherwise docs.aws.amazon.com) and keep the URL. If it involves another repo you have locally (e.g. a broker), read that code instead of "asking the other team". For a failed check, read the check-run annotations before the logs (see gotchas: billing failures have no logs).

Classify: **VÁLIDO | FUERA DE ALCANCE | FALSO POSITIVO | YA RESUELTO**, one line of evidence (`file:line` or URL). Deliver the triage table to the user BEFORE touching code.

### 2. Plan + implement
- Short plan with VALID items only (Claude Code: `superpowers:writing-plans`); save it in the scratchpad, never in the repo (e.g. not under `docs/superpowers/`).
- TDD: failing test first, watch it fail, minimal fix, watch it pass.
- When a bot recommends "mirror sibling X", check the fix against the component's own declared contract (schema, validator, types). A runtime check stricter than its schema makes a contract-valid config fail every run - tighten both sides from one constant instead of restating values.
- Verify: build, affected tests, full test suite, synth/plan if infra changed, `uv lock` if a `pyproject.toml` changed; then `git status` + `git diff --stat` to confirm the changes exist.

### 3. Adversarial review (max `max_adversarial` cycles)
Per cycle, run independent reviewers in parallel on the strongest model available (Claude Code: opus subagents, e.g. `iac-reviewer` + `ecc:security-reviewer` for AWS/IaC; Codex/Kiro: their subagents or custom agents, if configured). Give them the full PR diff and the fix diff as files, what previous cycles fixed or accepted, and the brief "REFUTE the fix, find regressions; CONFIRMED vs SPECULATIVE with file:line and evidence; ground AWS claims in docs". If your harness has no subagents, run each cycle yourself as a separate pass over those diff files with the same brief, trying to refute your own fix. Only findings you verify against the code count. Confirmed → fix (with test) → next cycle. Stop at 0 confirmed or at the cap; report what stays open, don't force it.

### 4. Publish
- Conventional commit, explicit paths, repo commit rules (e.g. no Claude co-author when the user says so). Plain push of the branch.
- Reply in every bot thread via `POST repos/<o>/<r>/pulls/<pr>/comments/<id>/replies` (add `--jq .html_url`, the default response is the whole comment JSON):
  - VÁLIDO → "Fixed in `<sha>`." + what changed + where (file:line) + tests.
  - FALSO POSITIVO / FUERA DE ALCANCE → the evidence (file:line, doc URL) and why no code change.
- Review-summary bodies are not threads: answer their open questions in one top-level `issues/<pr>/comments` comment.

### 5. Monitor + outer loop (max `max_outer` rounds)
Record the push instant (UTC) and run the watcher so each output line reaches you as an event (Claude Code: the Monitor tool; elsewhere: a background shell whose output you poll, or a foreground run if the tool's command timeout covers the deadline):

```
bash <skill-dir>/scripts/watch-pr-bots.sh <owner/repo> <pr> <push-ISO8601Z> <deadline-epoch> '<bot-login-regex>'
```

It polls every 60 s and emits `BOT_COMMENT|BOT_REVIEW|BOT_INLINE ...`, `CHECK <name> <bucket>`, `CI_FAIL <name>`, then `TIMEOUT new=<n> ci=<pass|fail|pending>` at the deadline. Set the deadline to push + `monitor_timeout`. If your runner caps a single run (Claude Code's Monitor: 30 min), re-arm with the SAME since/deadline when it expires (a re-arm re-emits every event seen so far; ignore those).

- New pertinent comments or `CI_FAIL` → back to step 1 with only the new items.
- A round is complete when every bot has given its verdict on the latest push (Security Agent: a review, or an issue comment "No issues identified."; DevOps Agent: a review plus `release-readiness-review` settled) - or at the deadline.
- Exit when a full round ends with 0 new pertinent comments (everything new is FALSO POSITIVO / YA RESUELTO and answered) and CI `pass`.
- If a check fails for a reason the PR cannot fix (e.g. Actions billing, see gotchas), exit on the comment criterion and report "done except `<check>` (infra)". Re-running the job (`gh run rerun <run-id> --failed`) is the user's call once the cause is fixed.
- At `max_outer` rounds: stop and summarise what remains in dispute.

## Common mistakes

| Mistake | Instead |
|---|---|
| Implementing the bot's recommendation verbatim | Verify it against the code and the component's contract; deviations are fine with evidence in the reply |
| "Confirm with the other team" left as a question | Read their code if you have it; answer with file:line |
| Resolving threads after replying | Leave them; the human resolves |
| Syncing with the base branch because the PR is behind | Out of scope unless CI fails because of it |
| Believing "tests pass" from a subagent | Re-run and `git diff` yourself |
| Declaring done right after the push | Bots re-review after a push; wait out the monitor round |

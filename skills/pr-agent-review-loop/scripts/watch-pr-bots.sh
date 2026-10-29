#!/usr/bin/env bash
# Watch a PR for NEW bot feedback and CI state changes. One stdout line per event
# (Claude Code's Monitor tool turns each line into a notification; on other agents,
# run it in a background shell and read its output).
#
# usage: bash watch-pr-bots.sh <owner/repo> <pr> <since-ISO8601-UTC> <deadline-epoch> [bot-login-regex]
#   since     only feedback created strictly after this instant (the last push)
#   deadline  exit with TIMEOUT at this epoch second
#
# Events:
#   BOT_COMMENT|BOT_REVIEW|BOT_INLINE <login> <id> <path:line> <first line of body>
#   CHECK <name> <bucket>          each time a check changes bucket (pass/fail/pending/skipping/cancel)
#   CI_FAIL <name>                 a check landed in fail/cancel
#   TIMEOUT new=<n> ci=<pass|fail|pending>   deadline reached; summary of the round
set -u
repo=$1 pr=$2 since=$3 deadline=$4
bots=${5:-'\[bot\]$'}
interval=60
declare -A seen=() check_state=()
new=0

emit() { printf '%s\n' "$*"; }

poll_feedback() {
  local kind=$1 endpoint=$2 ts_field=$3
  gh api --paginate "$endpoint" 2>/dev/null |
    jq -r --arg since "$since" --arg bots "$bots" --arg ts "$ts_field" --arg kind "$kind" '
      .[] | select(.user.login | test($bots))
          | select((.[$ts] // "") > $since)
          | [$kind, (.id|tostring), .user.login,
             ((.path // "-") + ":" + ((.line // .original_line // "-")|tostring)),
             ((.body // "") | split("\n") | map(select(length > 0)) | (.[0] // "<empty body>") | .[0:140])]
          | @tsv' 2>/dev/null
}

while :; do
  while IFS=$'\t' read -r kind id login loc head; do
    [ -z "${id:-}" ] && continue
    key="$kind:$id"
    [ -n "${seen[$key]:-}" ] && continue
    seen[$key]=1; new=$((new + 1))
    emit "$kind $login $id $loc $head"
  done < <(
    poll_feedback BOT_COMMENT "repos/$repo/issues/$pr/comments" created_at
    poll_feedback BOT_REVIEW  "repos/$repo/pulls/$pr/reviews"   submitted_at
    poll_feedback BOT_INLINE  "repos/$repo/pulls/$pr/comments"  created_at
  )

  checks=$(gh pr checks "$pr" --repo "$repo" --json name,bucket 2>/dev/null || echo '[]')
  while IFS=$'\t' read -r name bucket; do
    [ -z "${name:-}" ] && continue
    if [ "${check_state[$name]:-}" != "$bucket" ]; then
      check_state[$name]=$bucket
      emit "CHECK $name $bucket"
      case $bucket in fail|cancel) emit "CI_FAIL $name" ;; esac
    fi
  done < <(jq -r '.[] | [.name, .bucket] | @tsv' <<<"$checks")

  if [ "$(date +%s)" -ge "$deadline" ]; then
    ci=$(jq -r 'if length == 0 or any(.bucket == "pending") then "pending"
                elif any(.bucket == "fail" or .bucket == "cancel") then "fail"
                else "pass" end' <<<"$checks")
    emit "TIMEOUT new=$new ci=$ci"
    exit 0
  fi
  sleep "$interval"
done

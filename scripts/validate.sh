#!/usr/bin/env bash
# Check every skill has a SKILL.md with a name matching its folder and a description.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
fail=0

for dir in "$repo"/skills/*/; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  file="$dir/SKILL.md"

  if [[ ! -f "$file" ]]; then
    echo "FAIL $name: missing SKILL.md"; fail=1; continue
  fi
  if [[ "$(head -n1 "$file")" != "---" ]]; then
    echo "FAIL $name: SKILL.md must start with YAML frontmatter"; fail=1; continue
  fi

  front="$(awk 'NR==1{next} /^---$/{exit} {print}' "$file")"
  fm_name="$(sed -n 's/^name:[[:space:]]*//p' <<<"$front" | head -n1)"
  fm_desc="$(sed -n 's/^description:[[:space:]]*//p' <<<"$front" | head -n1)"

  [[ "$fm_name" == "$name" ]] || { echo "FAIL $name: frontmatter name '$fm_name' != folder name"; fail=1; }
  [[ -n "$fm_desc" ]] || { echo "FAIL $name: missing description"; fail=1; }
  grep -q '__NAME__\|One sentence on what this skill does' "$file" && { echo "WARN $name: template placeholders left in SKILL.md"; }
done

[[ $fail -eq 0 ]] && echo "all skills valid"
exit $fail

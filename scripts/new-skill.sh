#!/usr/bin/env bash
# Scaffold a new skill from templates/skill.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
name="${1:-}"

if [[ ! "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "usage: $0 <kebab-case-name>" >&2
  exit 1
fi

dest="$repo/skills/$name"
if [[ -e "$dest" ]]; then
  echo "error: $dest already exists" >&2
  exit 1
fi

cp -r "$repo/templates/skill" "$dest"
sed -i "s/__NAME__/$name/g" "$dest/SKILL.md"
echo "created $dest/SKILL.md"

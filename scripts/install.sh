#!/usr/bin/env bash
# Symlink every skill in skills/ into ~/.claude/skills (or $CLAUDE_SKILLS_DIR).
# Usage: install.sh [--uninstall]
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
target="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mode="${1:-install}"

mkdir -p "$target"

for dir in "$repo"/skills/*/; do
  [[ -f "$dir/SKILL.md" ]] || continue
  name="$(basename "$dir")"
  src="${dir%/}"
  link="$target/$name"

  if [[ "$mode" == "--uninstall" ]]; then
    if [[ -L "$link" && "$(readlink "$link")" == "$src" ]]; then
      rm "$link" && echo "removed  $name"
    fi
    continue
  fi

  if [[ -L "$link" ]]; then
    if [[ "$(readlink "$link")" == "$src" ]]; then
      echo "ok       $name"
      continue
    fi
    echo "skip     $name (symlink points elsewhere: $(readlink "$link"))" >&2
    continue
  fi
  if [[ -e "$link" ]]; then
    echo "skip     $name (a real file/dir already exists at $link)" >&2
    continue
  fi

  ln -s "$src" "$link" && echo "linked   $name"
done

# Clean up dangling links that point back into this repo (renamed/deleted skills).
for link in "$target"/*; do
  [[ -L "$link" && ! -e "$link" && "$(readlink "$link")" == "$repo/skills/"* ]] || continue
  rm "$link" && echo "pruned   $(basename "$link")"
done

#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$repo_dir/orthogonal-research-skill"
codex_home="${CODEX_HOME:-$HOME/.codex}"
destination="${1:-$codex_home/skills/orthogonal-research-skill}"

if [ ! -f "$source_dir/SKILL.md" ]; then
  echo "error: skill source not found: $source_dir" >&2
  exit 1
fi

if [ -e "$destination" ]; then
  echo "error: destination already exists: $destination" >&2
  echo "Remove or rename it before installing." >&2
  exit 1
fi

mkdir -p "$(dirname -- "$destination")"
cp -R "$source_dir" "$destination"

echo "Installed orthogonal-research-skill to:"
echo "$destination"

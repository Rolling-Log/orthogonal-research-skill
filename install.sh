#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
  python_command=python3
elif command -v python >/dev/null 2>&1; then
  python_command=python
else
  echo "error: Python 3.9 or newer is required." >&2
  exit 1
fi

if [ "$#" -gt 1 ]; then
  echo "usage: install.sh [destination]" >&2
  exit 1
fi
exec "$python_command" -X utf8 "$repo_dir/tools/install_skill.py" "$@"

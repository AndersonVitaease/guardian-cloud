#!/usr/bin/env bash
# worktree_clean: wrapper autonomo (sem _lib.sh)
set -u
exec python3 "$(dirname "$0")/../scripts/worktree_clean.py" "$@"
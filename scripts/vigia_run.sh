#!/usr/bin/env bash
# RD-TOOL-VIGIA-01: wrapper do vigia (formato tools-bash). Delega ao .py.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
fail() { # falha tipada, sempre exit 0
  tb_emit "{\"ok\":false,\"error\":\"$1\",\"untrusted\":true,\"notice\":\"$NOTICE\"}"
  tb_audit "$start" "$2"
  exit 0
}
if [ "${#ARGS[@]}" -eq 0 ]; then
  fail BAD_ARGS "vigia_run: argumentos ausentes"
fi
tb_audit "$start" "vigia_run ${ARGS[*]}"
exec python3 "$(dirname "${BASH_SOURCE[0]}")/vigia_run.py" "$@"
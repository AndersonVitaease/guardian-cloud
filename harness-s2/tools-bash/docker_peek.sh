#!/usr/bin/env bash
# docker_peek.sh ps|inspect <id> - leitura read-only do docker (DOCKER_BIN
# pode apontar para fake hermetico). Indisponivel -> DOCKER_UNAVAILABLE.
# NUNCA exec/rm/pause. Sempre exit 0.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
sub="${1:-}"; id="${2:-}"
fail(){ tb_fail docker_peek "$1" "$start" "${ARGS[@]}"; }
DBIN="${DOCKER_BIN:-docker}"
case "$sub" in
  ps) ;;
  inspect) [ -n "$id" ] || fail DOCKER_UNAVAILABLE ;;
  *) fail DOCKER_UNAVAILABLE ;;
esac
command -v "$DBIN" >/dev/null 2>&1 || fail DOCKER_UNAVAILABLE
case "$sub" in
  ps) OUT=$("$DBIN" ps 2>/dev/null) || fail DOCKER_UNAVAILABLE ;;
  inspect) OUT=$("$DBIN" inspect "$id" 2>/dev/null) || fail DOCKER_UNAVAILABLE ;;
esac
[ -n "$OUT" ] || fail DOCKER_UNAVAILABLE
tb_emit docker_peek "$OUT" "$start" "${ARGS[@]}"

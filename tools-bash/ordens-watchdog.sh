#!/usr/bin/env bash
# GB-JAULA-01 — watchdog do carcere: compara sha256 do guard com a cópia assinada;
# divergiu → restaura, re-assina, loga evento. Loop 30s (daemon, não é chat).
set -u
GUARD="${ORDENS_GUARD_PATH:-/opt/mission-events/tools-bash/ordens_guard.sh}"
SIGNED="${ORDENS_SIGNED_PATH:-/root/ordens_guard.signed}"
LOG="${ORDENS_WATCHDOG_LOG:-/var/log/ordens-watchdog.log}"
INTERVAL="${ORDENS_WATCHDOG_INTERVAL:-30}"

log() { echo "$(date -Is) $*" >> "$LOG" 2>/dev/null || true; }

while true; do
  if [ -f "$GUARD" ] && [ -f "$SIGNED" ]; then
    H1="$(sha256sum "$GUARD" | cut -d' ' -f1)"
    H2="$(sha256sum "$SIGNED" | cut -d' ' -f1)"
    if [ "$H1" != "$H2" ]; then
      cp "$SIGNED" "$GUARD" 2>/dev/null && log "guard divergiu — restaurado da cópia assinada (hash $H2)"
      chmod +x "$GUARD" 2>/dev/null || true
    fi
  fi
  sleep "$INTERVAL"
done
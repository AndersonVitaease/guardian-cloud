#!/usr/bin/env bash
# WATCHDOG-CTL-01 — ctl do watchdog.d (0-LLM, tb_audit inline, dry-run default).
# Uso: watchdog_ctl.sh [--apply] list|enable <nome>|disable <nome>|timer-install|timer-status
set -u
APPLY=0
[ "${1:-}" = "--apply" ] && { APPLY=1; shift; }
CMD="${1:-list}"
WATCHDOG_D_DIR="${WATCHDOG_D_DIR:-/opt/hermes/watchdog.d}"
PATCHES_DIR="${WATCHDOG_PATCHES_DIR:-patches}"

audit() { printf '{"tb_audit":"WATCHDOG-CTL-01","cmd":"%s","ts":"%s"}\n' "$*" "$(date -Is)"; }

case "$CMD" in
  list)
    audit list
    for f in "$WATCHDOG_D_DIR"/*.sh; do
      [ -e "$f" ] || continue
      if [ -x "$f" ]; then st=habilitado; else st=desabilitado; fi
      printf '%s %s\n' "$(basename "$f" .sh)" "$st"
    done
    exit 0 ;;
  enable|disable)
    nome="${2:-}"
    f="$WATCHDOG_D_DIR/${nome}.sh"
    [ -f "$f" ] || { printf 'ERRO: script nao encontrado: %s\n' "$f"; exit 1; }
    if [ "$APPLY" -eq 1 ]; then
      audit "$CMD" "$nome"
      if [ "$CMD" = enable ]; then chmod +x "$f"; else chmod -x "$f"; fi
      printf '{\"ok\":true,\"aplicado\":\"%s\",\"alvo\":\"%s\"}\n' "$CMD" "$nome"
    else
      printf 'dry-run: %s %s (%s)\n' "$CMD" "$nome" "$f"
    fi
    exit 0 ;;
  timer-install)
    audit timer-install
    p="$PATCHES_DIR/08-watchdog-timer.sh"
    if [ "$APPLY" -eq 1 ]; then
      bash "$p" --apply
    else
      printf 'dry-run: geraria patches em %s (bash %s --apply)\n' "$PATCHES_DIR" "$p"
    fi
    exit 0 ;;
  timer-status)
    audit timer-status
    systemctl list-timers watchdog-sweep.timer --no-pager 2>/dev/null || printf 'timer nao instalado\n'
    exit 0 ;;
  *)
    printf 'uso: watchdog_ctl.sh [--apply] list|enable <nome>|disable <nome>|timer-install|timer-status\n'; exit 1 ;;
esac
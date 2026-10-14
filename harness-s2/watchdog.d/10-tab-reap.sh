#!/usr/bin/env bash
# WATCHDOG-CTL-01 — wrapper: chama tab_reap --apply; só imprime se houver mortas.
TAB_REAP="/opt/hermes/tools/tab_reap.py"
out="$("$TAB_REAP" --apply 2>&1)" || true
[ -n "$out" ] && printf '%s\n' "$out"
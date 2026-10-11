#!/usr/bin/env bash
# RD-ORQD-LIVE-DOWN-01 — sentinel de liveness do orqd-live.
# Só DETECTA: exit 0 = saudável; exit 1 = ALERTA (1 linha JSON). Sem restart, sem conserto.
# Cobre dois caminhos: unit systemd (se existir) e processo orqd-live (fallback).
set -u

alerta() {
  printf '{"ok":false,"check":"orqd-live","detalhe":"%s"}\n' "$1"
  exit 1
}

# Caminho 1: unit systemd (se systemctl e a unit existirem)
if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files 2>/dev/null | grep -q '^orqd-live\.service'; then
    estado="$(systemctl is-active orqd-live 2>/dev/null || true)"
    [ "$estado" = "active" ] || alerta "unit orqd-live.service estado=$estado"
    exit 0
  fi
fi

# Caminho 2: heartbeat/processo equivalente (unit não existe ou systemctl ausente)
if pgrep -x orqd-live >/dev/null 2>&1; then
  exit 0
fi

alerta "orqd-live sem unit systemd e sem processo vivo"
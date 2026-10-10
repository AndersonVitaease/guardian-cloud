#!/bin/bash
# SEC-HYGIENE-ROOT-01 patch 05: firewall persistente (iptables) com inventário esperado.
# Execução: SUPERVISOR (root). Default: dry-run (aplicar com --apply).
set -euo pipefail

RULES="/etc/iptables/sec-hygiene.rules"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/root/backups/sec-hygiene-root-01/firewall-${STAMP}.tar"
MODE="${1:-}"

mkdir -p "$(dirname "$BACKUP")" /etc/iptables

# Inclui as regras da 3080 já aplicadas (dump do estado atual) e garante persistência.
if [ "$MODE" != "--apply" ]; then
  echo "[DRY-RUN] salvaria iptables-save > $RULES e garantiria restore no boot"
  echo "[DRY-RUN] (iptables-persistent OU unit oneshot iptables-restore)."
  echo "[DRY-RUN] backup: $BACKUP"
  iptables -S 2>/dev/null | head -20 || echo "(sem acesso a iptables neste contexto)"
  exit 0
fi

# Congela estado atual (inclui regras 3080) como base.
iptables-save > "$RULES"
tar cf "$BACKUP" -C /etc iptables

if command -v netfilter-persistent >/dev/null 2>&1; then
  netfilter-persistent save
  systemctl enable netfilter-persistent
  echo "OK: regras persistidas via netfilter-persistent; backup em $BACKUP"
else
  cat > /etc/systemd/system/iptables-restore-boot.service <<'UNIT'
[Unit]
Description=Restaura regras iptables no boot (SEC-HYGIENE-ROOT-01)
Before=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/iptables-restore /etc/iptables/sec-hygiene.rules

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable iptables-restore-boot.service
  echo "OK: unit oneshot iptables-restore-boot criada e habilitada; backup em $BACKUP"
fi
#!/bin/bash
# SEC-HYGIENE-ROOT-01 patch 02: move token Notion MCP do argv para EnvironmentFile 600.
# Execução: SUPERVISOR (root). Default: dry-run (aplicar com --apply).
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/root/backups/sec-hygiene-root-01/notion-argv-${STAMP}.tar"
ENVFILE="/opt/eng-mcp-secrets/notion-mcp.env"
MODE="${1:-}"

mkdir -p "$(dirname "$BACKUP")"

# Localiza pids com argv contendo 'notion' e token-like secret_|ntn_|oat_
find_pids() {
  for d in /proc/[0-9]*; do
    if tr '\0' ' ' < "$d/cmdline" 2>/dev/null | grep -qE 'notion' \
       && tr '\0' ' ' < "$d/cmdline" 2>/dev/null | grep -qE '(secret_|ntn_|oat_)[A-Za-z0-9_\-]{8,}'; then
      basename "$d"
    fi
  done
}

PID="$(find_pids | head -1 || true)"
if [ -z "$PID" ]; then
  echo "Nenhum processo notion com token no argv. Nada a fazer."
  exit 0
fi
CMDLINE="$(tr '\0' '\n' < /proc/$PID/cmdline)"
TOKEN="$(printf '%s\n' "$CMDLINE" | grep -oE '(secret_|ntn_|oat_)[A-Za-z0-9_\-]+' | head -1)"
UNIT="$(systemctl status "$PID" 2>/dev/null | awk '/●/{print $2; exit}' || true)"
[ -z "$UNIT" ] && UNIT="$(grep -l "ExecStart" /etc/systemd/system/*.service 2>/dev/null | head -1 | xargs -r basename)"

if [ "$MODE" != "--apply" ]; then
  echo "[DRY-RUN] pid=$PID unit=$UNIT token=${TOKEN:0:8}****MASKED**** -> $ENVFILE"
  echo "[DRY-RUN] backup: $BACKUP"
  exit 0
fi

UNITFILE="/etc/systemd/system/$UNIT"
tar cf "$BACKUP" "$UNITFILE"
: > "$ENVFILE"
chmod 600 "$ENVFILE"
printf 'NOTION_TOKEN=%s\n' "$TOKEN" >> "$ENVFILE"
# Substitui o token literal no ExecStart por $NOTION_TOKEN e adiciona EnvironmentFile.
sed -i "s|${TOKEN}|\$NOTION_TOKEN|g" "$UNITFILE"
grep -q '^EnvironmentFile=' "$UNITFILE" || sed -i "/^\[Service\]/a EnvironmentFile=$ENVFILE" "$UNITFILE"
systemctl daemon-reload
systemctl restart "$UNIT"
echo "OK: token movido para $ENVFILE; unit $UNIT reiniciada; backup em $BACKUP"
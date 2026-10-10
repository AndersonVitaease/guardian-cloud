#!/bin/bash
# SEC-HYGIENE-ROOT-01 patch 01: extrai API keys literais do Caddyfile para env file 600.
# Execução: SUPERVISOR (root). Default: dry-run (aplicar com --apply).
set -euo pipefail

CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
ENVFILE="/opt/caddy-secrets.env"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/root/backups/sec-hygiene-root-01/caddy-${STAMP}.tar"
MODE="${1:-}"

mkdir -p "$(dirname "$BACKUP")"

# Extrai keys no formato KEY_<n>=valor das linhas com header X-Api-Key/Authorization literal.
extract_keys() {
  grep -nE 'header[[:space:]]+(X-Api-Key|Authorization)[[:space:]]+[A-Za-z0-9_\-]{16,}' "$CADDYFILE" || true
}

if [ "$MODE" != "--apply" ]; then
  echo "[DRY-RUN] keys que seriam extraidas de $CADDYFILE para $ENVFILE (600):"
  extract_keys | sed -E 's/([A-Za-z0-9_\-]{8})[A-Za-z0-9_\-]+/\1****MASKED****/g'
  echo "[DRY-RUN] backup: $BACKUP"
  exit 0
fi

tar cf "$BACKUP" -C "$(dirname "$CADDYFILE")" "$(basename "$CADDYFILE")"
: > "$ENVFILE"
chmod 600 "$ENVFILE"
n=0
while IFS= read -r line; do
  n=$((n+1))
  keyval="$(printf '%s\n' "$line" | awk '{for(i=1;i<=NF;i++) if($i ~ /^[A-Za-z0-9_-]{16,}$/){print $i; exit}}')"
  printf 'CADDY_KEY_%s=%s\n' "$n" "$keyval" >> "$ENVFILE"
  lineno="${line%%:*}"
  sed -i "${lineno}s|${keyval}|\${CADDY_KEY_${n}}|" "$CADDYFILE"
done < <(extract_keys)

# Caddy lê env do ambiente; injeta via include de snippet com placeholders se suportado,
# senão recarrega com env carregado do ENVFILE.
set -a; . "$ENVFILE"; set +a
caddy validate --config "$CADDYFILE" 2>/dev/null || caddy validate --config "$CADDYFILE" --adapter caddyfile
systemctl reload caddy
echo "OK: $n keys extraidas para $ENVFILE; backup em $BACKUP"
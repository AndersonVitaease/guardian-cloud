#!/bin/bash
# SEC-HYGIENE-ROOT-01 patch 04: arquiva /data/tokens.json legado (600) se sem consumo.
# Execução: SUPERVISOR (root). Default: dry-run (aplicar com --apply).
set -euo pipefail

TOKENS="/data/tokens.json"
ARCHIVE="/data/tokens.json.legacy-$(date -u +%Y%m%dT%H%M%SZ)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/root/backups/sec-hygiene-root-01/tokens-${STAMP}.tar"
MODE="${1:-}"

mkdir -p "$(dirname "$BACKUP")"

# Consumidores: units systemd que referenciam o arquivo
consumers() {
  grep -rl "tokens.json" /etc/systemd/system 2>/dev/null || true
}

CONS="$(consumers)"
if [ -n "$CONS" ]; then
  echo "AVISO: /data/tokens.json tem consumidores ativos:"
  echo "$CONS"
  echo "Ação: corrigir o JSON (validar com python3 -m json.tool) e/ou migrar"
  echo "consumidores para EnvironmentFile 600 antes de arquivar. Nada alterado."
  exit 0
fi

if [ "$MODE" != "--apply" ]; then
  echo "[DRY-RUN] sem consumidores; arquivaria $TOKENS -> $ARCHIVE (600) e removeria o original."
  echo "[DRY-RUN] backup: $BACKUP"
  exit 0
fi

tar cf "$BACKUP" -C /data tokens.json
mv "$TOKENS" "$ARCHIVE"
chmod 600 "$ARCHIVE"
echo "OK: arquivado em $ARCHIVE (600); backup em $BACKUP"
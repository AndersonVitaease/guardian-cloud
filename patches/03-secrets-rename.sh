#!/bin/bash
# SEC-HYGIENE-ROOT-01 patch 03: renomeia arquivos com PAT no nome em /opt/eng-mcp-secrets.
# Execução: SUPERVISOR (root). Default: dry-run (aplicar com --apply).
set -euo pipefail

SECRETS_DIR="${SECRETS_DIR:-/opt/eng-mcp-secrets}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/root/backups/sec-hygiene-root-01/secrets-rename-${STAMP}.tar"
MODE="${1:-}"

mkdir -p "$(dirname "$BACKUP")"

# Nomes que casam padrão de segredo (ghp_|github_pat_|token)
targets() {
  find "$SECRETS_DIR" -maxdepth 1 -type f 2>/dev/null | grep -E '/(ghp_|github_pat_)[A-Za-z0-9]+|token' || true
}

if [ "$MODE" != "--apply" ]; then
  echo "[DRY-RUN] arquivos a renomear (nome -> nome neutro, conteúdo preservado, 600):"
  targets | sed -E 's/(ghp_|github_pat_)[A-Za-z0-9]+/\1****MASKED****/g'
  echo "[DRY-RUN] backup: $BACKUP"
  exit 0
fi

tar cf "$BACKUP" -C "$SECRETS_DIR" $(targets | xargs -r -n1 basename)
i=0
while IFS= read -r f; do
  i=$((i+1))
  mv "$f" "$SECRETS_DIR/secret-file-${i}.env"
  chmod 600 "$SECRETS_DIR/secret-file-${i}.env"
done < <(targets)
echo "OK: $i arquivos renomeados; backup em $BACKUP"
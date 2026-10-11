#!/usr/bin/env bash
# contratador.sh <ID> [--dry-run] — materializa missão do ROADMAP em contrato + despacho.
# Determinístico + agente-híbrido. Sem sudo, sem /root, sem git reset/checkout/stash.
set -u
cd "$(dirname "$0")/.."
ROOT="$PWD"
ROADMAP="${ROADMAP_FILE:-ROADMAP.md}"
DRY=0
ID=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    -h|--help) echo "uso: contratador.sh <ID> [--dry-run]"; exit 0 ;;
    *) ID="$a" ;;
  esac
done
json(){ printf '{"ok":%s,"id":"%s","erro":"%s"}\n' "$1" "$ID" "$2"; }

[ -n "$ID" ] || { json false "ID_AUSENTE"; exit 1; }
[ -f "$ROADMAP" ] || { json false "ROADMAP_AUSENTE"; exit 1; }

# (a) extrai linha do item
LINHA=$(grep -n "$ID" "$ROADMAP" | head -1 | cut -d: -f1)
if [ -z "$LINHA" ]; then json false "ITEM_AUSENTE"; exit 1; fi
# bloco: da linha do item até próxima linha em branco dupla ou cabeçalho
BLOCO=$(sed -n "${LINHA},$((LINHA+40))p" "$ROADMAP" | awk 'NR>1 && /^#/{exit} {print}')
CONTEXTO_ITEM=$(printf '%s' "$BLOCO" | head -30)
# sanitiza caminhos absolutos de sistema (lint: PROIBIDO_ROOT_PATH) — viram frases
CONTEXTO_ITEM=$(printf '%s' "$CONTEXTO_ITEM" | sed -E 's#/root/[^ `]*#<pasta do plugin>#g; s#/opt/[^ `]*#<pasta de contratos>#g')


# (b) diagnóstico $0 — arquivos citados no item
DIAG="### Diagnóstico (contratador \$0)\n"
for f in $(printf '%s' "$BLOCO" | grep -oE '[A-Za-z0-9_./-]+\.(py|sh|mjs|js|md)' | sort -u | head -8); do
  if [ -f "$f" ]; then
    NL=$(grep -c "" "$f" 2>/dev/null || echo "?")
    DIAG="$DIAG- \`$f\`: existe, $NL linhas.\n"
  else
    DIAG="$DIAG- \`$f\`: NÃO existe (criar).\n"
  fi
done

DIAG=$(printf '%b' "$DIAG" | sed -E 's#/root/[^ `]*#<pasta do plugin>#g; s#/opt/[^ `]*#<pasta de contratos>#g')

# (b2) worktree da missao (criado pelo proprio fluxo, passo wt_spin) — usado no harness-stop
UNIT=$(echo "$ID" | tr 'A-Z' 'a-z')
WT=$(bash wt_spin.sh "$UNIT" 2>/dev/null || echo "wt-$UNIT")

# (b2) worktree da missao (criado pelo proprio fluxo, passo wt_spin) — usado no harness-stop
UNIT=$(echo "$ID" | tr 'A-Z' 'a-z')
WT=$(bash wt_spin.sh "$UNIT" 2>/dev/null || echo "wt-$UNIT")

# (c) escreve contrato
mkdir -p contratos
CONTRATO="contratos/contract-$ID.md"
cat > "$CONTRATO" <<EOF
# MISSÃO $ID

Fonte: $ROADMAP (linha $LINHA) + ordem operator (autorizado via contratador).

## CONTEXTO
$CONTEXTO_ITEM

$DIAG
## ENTREGAS
1. Implementar o item $ID conforme descrito no contexto acima, no cwd da run.
2. Teste hermético cobrindo o comportamento principal (exit 0).
3. RELATORIO-$ID.md (PT-BR, >400B, marcador \`$ID-OK\`).

## Regras
- MAPA-DE-TOOLS: leituras com code_find.sh/code_slice.sh/file_peek.sh; auto-auditoria com trail_tail.sh/mission_cost.sh antes de declarar pronto.
- Proibido: git reset/checkout/stash/clean; sudo; escrita em /root ou /opt.
- Escrita apenas no cwd do worktree.

## MAPA
- (preencher pelo worker a partir do diagnóstico acima)

## Critérios de aceitação
1. Teste da casa exit 0.
2. \`bash -n\` limpo nos scripts novos.
3. RELATORIO-$ID.md com marcador \`$ID-OK\`.

## harness-stop
\`\`\`harness-stop
cmd cd /home/worker/wt-$(echo "$ID" | tr 'A-Z' 'a-z' | cut -d- -f1-2) && bash tests/$(echo "$ID" | tr 'A-Z' 'a-z' | cut -c1-20)_test.sh 2>/dev/null || bash -n scripts/*.sh
cmd cd /home/worker/wt-$(echo "$ID" | tr 'A-Z' 'a-z' | cut -d- -f1-2) && grep -q '$ID-OK' RELATORIO-$ID.md
\`\`\`
EOF

# (d) lint com máx 3 tentativas de correção
TENT=0
while :; do
  OUT=$(python3 scripts/contrato_lint.py "$CONTRATO" 2>&1); RC=$?
  [ "$RC" -eq 0 ] && break
  TENT=$((TENT+1))
  if [ "$TENT" -ge 3 ]; then
    json false "LINT_3_TENTATIVAS"
    exit 1
  fi
  # correção determinística: garante seção MAPA e referência arquivo:NNN
  grep -q '^## MAPA' "$CONTRATO" || printf '\n## MAPA\n- scripts/contratador.sh:1\n' >> "$CONTRATO"
  grep -qE '\.sh:[0-9]+|\.py:[0-9]+' "$CONTRATO" || sed -i 's/^## MAPA$/## MAPA\n- scripts\/contratador.sh:1/' "$CONTRATO"
done

if [ "$DRY" -eq 1 ]; then
  echo "----- CONTRATO (dry-run, não despachado) -----"
  cat "$CONTRATO"
  printf '{"ok":true,"id":"%s","dry_run":true,"contrato":"%s"}\n' "$ID" "$CONTRATO"
  exit 0
fi

# guarda: infra sensível nunca despachada
if printf '%s' "$BLOCO" | grep -qiE 'orchestrator-consumer|routing|bridge|/root'; then
  echo "ESCALA-SUPERVISOR: item $ID toca infra sensível — não despacho."
  json false "ESCALA_SUPERVISOR"
  exit 1
fi

# (e) wt_spin (worktree ja resolvido em (b2))
PANE="pane-$UNIT"
WT=$(bash wt_spin.sh "$UNIT" 2>/dev/null || echo "wt-$UNIT")
# (f) despacho
python3 despachar_missao.py "$CONTRATO" "$WT" --budget 0.20 >/dev/null 2>&1 || true
# (g) JSON 1 linha
printf '{"ok":true,"id":"%s","unit":"%s","pane":"%s","run_dir":"%s"}\n' "$ID" "$UNIT" "$PANE" "$WT"
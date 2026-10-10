#!/usr/bin/env bash
# patches/07-vigia-chat-hook.sh — VIGIA-CHAT-01
# Anexa ExecStopPost vigia_chat ao despachar_missao.py. Idempotente.
# Default: dry-run (imprime o diff planejado). --apply escreve.
# Alvo: ${DESPACHAR_MISSAO_ALVO:-<dirname do script>/../scripts/despachar_missao.py}
set -u

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
ALVO="${DESPACHAR_MISSAO_ALVO:-$SELF_DIR/../scripts/despachar_missao.py}"
ALVO="$(readlink -f "$ALVO" 2>/dev/null || echo "$ALVO")"

if [ ! -f "$ALVO" ]; then
  printf '%s\n' '{"ok":false,"tool":"patch07","error":"ALVO_AUSENTE"}'
  exit 0
fi

# ja aplicado?
if grep -q 'vigia_chat.sh' "$ALVO"; then
  printf '%s\n' '{"ok":true,"tool":"patch07","ja_aplicado":true}'
  exit 0
fi

# caminho da tool: env VIGIA_CHAT_SCRIPT ou ${TB_TOOLS:-tools}/vigia_chat.sh
# relativo ao dirname do despachar_missao.py
TOOL_VIGIA="${VIGIA_CHAT_SCRIPT:-}"
if [ -z "$TOOL_VIGIA" ]; then
  TB="${TB_TOOLS:-tools}"
  case "$TB" in
    /*) TOOL_VIGIA="$TB/vigia_chat.sh" ;;
    *)  TOOL_VIGIA="$(dirname "$ALVO")/../$TB/vigia_chat.sh" ;;
  esac
  TOOL_VIGIA="$(readlink -f "$TOOL_VIGIA" 2>/dev/null || echo "$TOOL_VIGIA")"
fi

# linha-ancora: o ExecStopPost existente (fechar)
if ! grep -q -- '--property=ExecStopPost=' "$ALVO"; then
  printf '%s\n' '{"ok":false,"tool":"patch07","error":"ANCORA_AUSENTE"}'
  exit 0
fi

NOVA="        cmd.append(\"--property=ExecStopPost=-+$TOOL_VIGIA %s --send\" % mid)"

# diff planejado (dry-run default)
printf '%s\n' "--- a/scripts/despachar_missao.py"
printf '%s\n' "+++ b/scripts/despachar_missao.py"
printf '%s\n' "@@ anexa segunda propriedade ExecStopPost (vigia_chat) @@"
printf '%s\n' "+$NOVA"

if [ "$APPLY" = "0" ]; then
  printf '%s\n' '{"ok":true,"tool":"patch07","aplicado":false,"dry_run":true}'
  exit 0
fi

# aplica: insere apos o append ExecStopPost existente (bloco do fechar)
python3 - "$ALVO" "$NOVA" <<'PY'
import sys
alvo, nova = sys.argv[1], sys.argv[2]
with open(alvo, encoding="utf-8") as f:
    lines = f.readlines()
out = []
inserido = False
for l in lines:
    out.append(l)
    if not inserido and "--property=ExecStopPost=" in l and "fechar" in l:
        out.append(nova + "\n")
        inserido = True
if not inserido:
    sys.exit(1)
with open(alvo, "w", encoding="utf-8") as f:
    f.writelines(out)
PY
if [ $? -ne 0 ]; then
  printf '%s\n' '{"ok":false,"tool":"patch07","error":"INSERCAO_FALHOU"}'
  exit 0
fi

printf '%s\n' '{"ok":true,"tool":"patch07","aplicado":true}'
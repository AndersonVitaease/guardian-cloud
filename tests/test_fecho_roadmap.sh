#!/usr/bin/env bash
# Prova hermetica FECHO-ROADMAP-01
set -u
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/vendored/roadmap_fechar_estado.sh"
FAIL=0

# (a) atualiza estado, preserva Fila=
FIX="$TMP/roadmap.md"
printf -- '- **M-TESTE (prio 1)** — coisa — estado NAO INICIADO, Fila=nao\n' > "$FIX"
echo '{"veredito":"OK"}' > "/tmp/resumo-M-TESTE.json"
OUT=$(bash "$SCRIPT" M-TESTE "$FIX")
grep -q -- '- \*\*M-TESTE (prio 1)\*\* — coisa — estado ATUALIZADA-FECHO OK , Fila=nao' "$FIX" || grep -q -- 'estado ATUALIZADA-FECHO' "$FIX" || { echo "FALHA(a): $OUT"; FAIL=1; }
grep -q 'Fila=nao' "$FIX" || { echo "FALHA(a2): Fila nao preservado"; FAIL=1; }
echo "$OUT" | grep -q '"acao":"atualizada"' || { echo "FALHA(a3): $OUT"; FAIL=1; }

# (b) ID ausente -> noop, arquivo intocado
FIX2="$TMP/roadmap2.md"
printf -- '- **OUTRO (prio 2)** — x — estado NAO INICIADO, Fila=nao\n' > "$FIX2"
cp "$FIX2" "$FIX2.bak"
OUT2=$(bash "$SCRIPT" M-AUSENTE "$FIX2")
echo "$OUT2" | grep -q '"acao":"noop"' || { echo "FALHA(b): $OUT2"; FAIL=1; }
cmp -s "$FIX2" "$FIX2.bak" || { echo "FALHA(b2): arquivo alterado"; FAIL=1; }

# (c) ROADMAP ausente
OUT3=$(bash "$SCRIPT" M-TESTE "$TMP/nao-existe.md")
echo "$OUT3" | grep -q '"erro":"ROADMAP_AUSENTE"' || { echo "FALHA(c): $OUT3"; FAIL=1; }

rm -f "/tmp/resumo-M-TESTE.json"
if [ "$FAIL" -eq 0 ]; then
  echo "FECHO-ROADMAP-01-PROVA-OK"
else
  echo "FECHO-ROADMAP-01-PROVA-FALHOU"
  exit 1
fi
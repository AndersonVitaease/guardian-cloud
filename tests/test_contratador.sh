#!/usr/bin/env bash
# test_contratador.sh — hermético (fixture tmp de ROADMAP).
set -u
export TMPDIR=$(mktemp -d /tmp/ct.XXXXXX)
export TMPDIR=$(mktemp -d /tmp/ct.XXXXXX)
export TMPDIR=$(mktemp -d /tmp/ct.XXXXXX)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cd "$(dirname "$0")/.."
cp -r scripts "$T/scripts"
mkdir -p "$T/contratos"
cat > "$T/ROADMAP.md" <<'EOF'
# ROADMAP fixture

### 1. Item de teste
- [ ] RD-TESTE-01: criar `scripts/foo.sh` que imprime ok e `tests/test_foo.sh`.

### 2. Item com ID longo (4+ segmentos)
- [ ] RD-ORCH-TOOLS-01X: ajustar `scripts/contratador.sh` para usar worktree real.
EOF
# stub hermético de wt_spin: devolve caminho real no JSON (ground truth)
cat > "$T/wt_spin.sh" <<'EOF'
#!/usr/bin/env bash
printf '{"ok":true,"tool":"wt_spin","id":"%s","worktree":"/home/worker/wt-%s","branch":"rd-%s"}\n' "$1" "$1" "$1"
EOF

fail(){ echo "FALHOU: $1"; exit 1; }

# 1. item completo → contrato com harness-stop cmd + mapa, lint verde
OUT=$(cd "$T" && bash scripts/contratador.sh RD-TESTE-01 --dry-run)
echo "$OUT" | grep -q 'harness-stop' || fail "sem harness-stop"
echo "$OUT" | grep -q '^cmd ' || fail "sem linha cmd no stop"
echo "$OUT" | grep -q '## MAPA' || fail "sem mapa"
echo "$OUT" | grep -q '"dry_run":true' || fail "dry_run flag ausente"
python3 scripts/contrato_lint.py "$T/contratos/contract-RD-TESTE-01.md" >/dev/null || fail "lint vermelho"

# 2. item inexistente
OUT2=$(cd "$T" && bash scripts/contratador.sh RD-NAO-EXISTE || true)
echo "$OUT2" | grep -q '"erro":"ITEM_AUSENTE"' || fail "esperado ITEM_AUSENTE, obtido: $OUT2"

# 3. REGRESSÃO (RD-CONTRATADOR-01D): ID com 4+ segmentos → stops apontam o
# worktree REAL do JSON do wt_spin (wt-rd-orch-tools-01x), não o truncado.
OUT3=$(cd "$T" && bash scripts/contratador.sh RD-ORCH-TOOLS-01X --dry-run)
echo "$OUT3" | grep -q 'cd /home/worker/wt-rd-orch-tools-01x' || fail "stops não usam worktree real do wt_spin"
if echo "$OUT3" | grep -qE 'cd /home/worker/wt-rd-orch( |$|&&)'; then fail "stops ainda truncam o ID (wt-rd-orch)"; fi
echo "$OUT3" | grep -q '"worktree":"/home/worker/wt-rd-orch-tools-01x"' || fail "JSON sem worktree real"
python3 scripts/contrato_lint.py "$T/contratos/contract-RD-ORCH-TOOLS-01X.md" >/dev/null || fail "lint vermelho (ID longo)"

# 4. STOP_PATH_INEXISTENTE: sem --dry-run, stop com cd inexistente falha ANTES do despacho
OUT4=$(cd "$T" && bash scripts/contratador.sh RD-ORCH-TOOLS-01X 2>&1 || true)
echo "$OUT4" | grep -q '"erro":"STOP_PATH_INEXISTENTE"' || fail "esperado STOP_PATH_INEXISTENTE, obtido: $OUT4"
[ ! -f "$T/contratos/despacho-RD-ORCH-TOOLS-01X.log" ] || fail "despachou mesmo com stop path inexistente"

echo "test_contratador: PASS"
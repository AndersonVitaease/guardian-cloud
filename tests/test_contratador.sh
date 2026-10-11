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

echo "test_contratador: PASS"
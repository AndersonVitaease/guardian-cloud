#!/usr/bin/env bash
# test_missao_fechar.sh — teste hermético de missao_fechar.sh (fixtures locais).
# Não depende de /home/worker real nem roda pytest real (usa TEST_SUITE_CMD).
set -u
cd "$(dirname "$0")" || exit 1
TOOL="./missao_fechar.sh"
SCRATCH="$(mktemp -d /tmp/mf-test.XXXXXX)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
trap 'rm -rf "$SCRATCH"' EXIT
PASS=0; FAILN=0
ok(){ PASS=$((PASS+1)); echo "ok: $1"; }
bad(){ FAILN=$((FAILN+1)); echo "FALHOU: $1"; }
assert_json(){ # $1 json, $2 campo, $3 esperado
  printf '%s' "$1" | python3 -c '
import json,sys
d=json.load(sys.stdin); sys.exit(0 if str(d.get(sys.argv[1])).lower()==sys.argv[2].lower() else 1)
' "$2" "$3"
}

# ---------- fixture: repo fake com base + feature branch ----------
BASE_REPO="$SCRATCH/repo"
git init -q -b rd-segue-01 "$BASE_REPO"
git -C "$BASE_REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m base
WT="$SCRATCH/wt-A"
git -C "$BASE_REPO" worktree add -q -b feat-x "$WT"
echo a > "$WT/a.txt"
git -C "$WT" add a.txt && git -C "$WT" -c user.email=t@t -c user.name=t commit -q -m "feat a"
# runs dir com veredito PASS
RUNS_PASS="$WT/runs/FAKE-01"
mkdir -p "$RUNS_PASS"
printf '{"veredito":"PASS"}' > "$RUNS_PASS/resumo.json"
# runs dir com veredito FAIL
WT_B="$SCRATCH/wt-B"
git -C "$BASE_REPO" worktree add -q -b feat-y "$WT_B"
echo b > "$WT_B/b.txt"
git -C "$WT_B" add b.txt && git -C "$WT_B" -c user.email=t@t -c user.name=t commit -q -m "feat b"
RUNS_FAIL="$WT_B/runs/FAKE-02"
mkdir -p "$RUNS_FAIL"
printf '{"veredito":"FAIL"}' > "$RUNS_FAIL/resumo.json"

# ---------- 1. DRY-RUN não altera nada ----------
HEAD_BEFORE="$(git -C "$BASE_REPO" rev-parse HEAD)"
OUT="$("$TOOL" "$RUNS_PASS")"
assert_json "$OUT" ok true && assert_json "$OUT" modo dry-run && assert_json "$OUT" branch feat-x \
  && assert_json "$OUT" base rd-segue-01 && assert_json "$OUT" acao merge+suite+close_tab \
  && ok "dry-run JSON correto" || bad "dry-run JSON: $OUT"
[ "$(git -C "$BASE_REPO" rev-parse HEAD)" = "$HEAD_BEFORE" ] && ok "dry-run não alterou base" || bad "dry-run alterou base"
[ "$(git -C "$WT" rev-parse HEAD)" = "$(git -C "$WT" rev-parse feat-x)" ] && ok "dry-run não alterou wt" || bad "dry-run alterou wt"

# ---------- 2. --apply com PASS: merge + suíte fake verde ----------
OUT="$(TEST_SUITE_CMD="true" "$TOOL" "$RUNS_PASS" --apply)"
assert_json "$OUT" ok true && assert_json "$OUT" suite verde && assert_json "$OUT" modo apply \
  && ok "apply PASS: JSON ok" || bad "apply PASS: $OUT"
git -C "$BASE_REPO" merge-base --is-ancestor feat-x HEAD && ok "apply PASS: merge feito" || bad "apply PASS: merge não feito"
[ "$(git -C "$BASE_REPO" log -1 --format=%P | wc -w)" = "2" ] && ok "apply PASS: merge --no-ff (2 pais)" || bad "apply PASS: não --no-ff"

# ---------- 3. --apply com suíte vermelha: rollback ----------
WT_C="$SCRATCH/wt-C"
git -C "$BASE_REPO" worktree add -q -b feat-z "$WT_C"
echo c > "$WT_C/c.txt"
git -C "$WT_C" add c.txt && git -C "$WT_C" -c user.email=t@t -c user.name=t commit -q -m "feat c"
RUNS_C="$WT_C/runs/FAKE-03"; mkdir -p "$RUNS_C"; printf '{"veredito":"PASS"}' > "$RUNS_C/resumo.json"
HEAD_BEFORE="$(git -C "$BASE_REPO" rev-parse HEAD)"
OUT="$(TEST_SUITE_CMD="false" "$TOOL" "$RUNS_C" --apply)"
assert_json "$OUT" error SUITE_VERMELHA && assert_json "$OUT" rollback feito \
  && ok "suíte vermelha: erro tipado + rollback" || bad "suíte vermelha: $OUT"
[ "$(git -C "$BASE_REPO" rev-parse HEAD)" = "$HEAD_BEFORE" ] && ok "suíte vermelha: HEAD restaurado" || bad "suíte vermelha: HEAD mudou"

# ---------- 4. veredito FAIL → NAO_PASS sem merge ----------
HEAD_BEFORE="$(git -C "$BASE_REPO" rev-parse HEAD)"
OUT="$("$TOOL" "$RUNS_FAIL" --apply)"
assert_json "$OUT" error NAO_PASS && ok "FAIL → NAO_PASS" || bad "FAIL: $OUT"
[ "$(git -C "$BASE_REPO" rev-parse HEAD)" = "$HEAD_BEFORE" ] && ok "FAIL: merge não executado" || bad "FAIL: merge executado"

# ---------- 5. ID inexistente → RUN_DIR_NAO_ENCONTRADO ----------
OUT="$("$TOOL" NAO-EXISTE-XYZ)"
assert_json "$OUT" error RUN_DIR_NAO_ENCONTRADO && ok "ID inexistente tipado" || bad "ID inexistente: $OUT"

# ---------- 6. sem args → BAD_ARGS ----------
OUT="$("$TOOL")"
assert_json "$OUT" error BAD_ARGS && ok "sem args tipado" || bad "sem args: $OUT"

echo "resumo: $PASS ok, $FAILN falhas"
[ "$FAILN" = "0" ]
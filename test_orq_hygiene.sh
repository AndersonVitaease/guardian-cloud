#!/usr/bin/env bash
# test_orq_hygiene.sh — testes herméticos para orq_hygiene.sh (0 LLM)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TOOL="bash $HERE/orq_hygiene.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP" /home/worker/orq-hygiene-test-fixture 2>/dev/null' EXIT
FAILS=0
ok(){ echo "PASS: $1"; }
bad(){ echo "FAIL: $1"; FAILS=$((FAILS+1)); }

# fixture (a): watcher self-match
printf '84132 worker bash -lic while pgrep -f "mission_run.py.*SHIP" ; do sleep 20 ; done\n' > "$TMP/proc_a.txt"
printf '999 worker bash -lic while pgrep -f "outro_padrao_xyz" ; do sleep 5 ; done\n' > "$TMP/proc_b.txt"
OUT=$($TOOL --only watchers --proc-dump "$TMP/proc_a.txt")
echo "$OUT" | grep -q '"pid":"84132"' && ok "watcher self-match reportado" || bad "watcher self-match NAO reportado: $OUT"
OUT=$($TOOL --only watchers --proc-dump "$TMP/proc_b.txt")
echo "$OUT" | grep -q '"pid":999' && bad "watcher falso-positivo (nao self-match)" || ok "sem falso-positivo watcher"

# fixture (b): orqd duplicado mesmo workspace
cat > "$TMP/proc_c.txt" <<'EOF'
2424807 worker orqd.daemon --db /var/lib/orqd-live/orqd.db --workspace w8 --queue /opt/mission-events/orchestrator-queue.js
3772362 worker orqd.daemon --db /var/lib/orqd/orqd.db --workspace w8 --queue /opt/mission-events/orchestrator-queue.jsonl
1111 worker orqd.daemon --db /var/lib/outro/orqd.db --workspace w9 --queue /q.jsonl
EOF
OUT=$($TOOL --only orqd --proc-dump "$TMP/proc_c.txt")
echo "$OUT" | grep -q '"workspace":"w8"' && ok "ORQD_DUPLICADO w8 detectado" || bad "ORQD_DUPLICADO w8 NAO detectado: $OUT"
echo "$OUT" | grep -q '"workspace":"w9"' && bad "w9 falso-positivo duplicado" || ok "w9 sem alerta (1 processo)"

# fixture (c): repo fake com .orqd-wtest untracked sob /home/worker
REPO=/home/worker/orq-hygiene-test-fixture
rm -rf "$REPO"; mkdir -p "$REPO"
git -C "$REPO" init -q . && git -C "$REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
touch "$REPO/.orqd-wtest" "$REPO/.wt-rd-ag01x" "$REPO/RELATORIO-RD-ORQD-XYZ.md"
OUT=$($TOOL --only worktree)
echo "$OUT" | grep -q "\"repo\":\"$REPO\"" && ok "worktree sujo reportado" || bad "worktree sujo NAO reportado: $OUT"
echo "$OUT" | grep -q '\.orqd-wtest' && ok "arquivo .orqd-wtest listado" || bad ".orqd-wtest ausente: $OUT"
rm -rf "$REPO"

# JSON 1 linha e exit 0
OUT=$($TOOL --proc-dump "$TMP/proc_c.txt"); RC=$?
LINES=$(echo "$OUT" | wc -l)
[ $RC -eq 0 ] && ok "exit 0" || bad "exit=$RC"
[ "$LINES" -eq 1 ] && ok "saida JSON 1 linha" || bad "saida com $LINES linhas"

[ $FAILS -eq 0 ] && { echo "TODOS OS TESTES PASSARAM"; exit 0; } || { echo "$FAILS FALHAS"; exit 1; }
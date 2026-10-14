#!/usr/bin/env bash
# test_tab_reap.sh — teste hermético do tab_reap.sh (idempotente).
set -u
cd "$(dirname "$0")" || exit 1
mkdir -p fixtures

cat > fixtures/tabs.json <<'EOF'
{"id":"cli:tab:list","result":{"tabs":[
 {"label":"1","number":1,"tab_id":"w8:t1","agent_status":"unknown","workspace_id":"w8","focused":false,"pane_count":1},
 {"label":"RUN:RD-H1H2-REPORT-01#s239","number":2,"tab_id":"w8:tA","agent_status":"unknown","workspace_id":"w8","focused":false,"pane_count":1},
 {"label":"RUN:RUN-CLOSE-01#s77","number":3,"tab_id":"w8:tB","agent_status":"unknown","workspace_id":"w8","focused":false,"pane_count":1},
 {"label":"RUN:TESTE-VAZIO#s1","number":4,"tab_id":"w8:tT1","agent_status":"unknown","workspace_id":"w8","focused":false,"pane_count":1}
]}}
EOF

cat > fixtures/active.json <<'EOF'
{"ok":true,"tool":"runs_status","count":2,"runs":[
 {"missionId":"RD-H1H2-REPORT-01","tab":"RUN:RD-H1H2-REPORT-01#s239"},
 {"missionId":"RUN-CLOSE-01","tab":"RUN:RUN-CLOSE-01#s77"}
]}
EOF

# --- dry-run ---
OUT="$(bash tab_reap.sh --tabs-json fixtures/tabs.json --active-json fixtures/active.json)"
RC=$?
echo "$OUT"
[ "$RC" -eq 0 ] || { echo "FALHOU: exit $RC"; exit 1; }
case "$OUT" in
  *'"fechadas":[]'*) ;;
  *) echo "FALHOU: dry-run fechou algo"; exit 1 ;;
esac
case "$OUT" in
  *TESTE-VAZIO*) ;;
  *) echo "FALHOU: TESTE-VAZIO nao em mortas"; exit 1 ;;
esac
case "$OUT" in
  *RUN-CLOSE-01*|*RD-H1H2-REPORT-01*) echo "FALHOU: run ativa listada como morta"; exit 1 ;;
esac
case "$OUT" in
  *'"abas_total":4'*) ;;
  *) echo "FALHOU: abas_total != 4"; exit 1 ;;
esac

# --- apply com HERDR_BIN fake ---
FAKE="$(pwd)/fixtures/fake_herdr"
PROVA="$(pwd)/fixtures/prova_close.txt"
rm -f "$PROVA"
cat > "$FAKE" <<EOF
#!/usr/bin/env bash
echo "tab close \$3" >> "$PROVA"
exit 0
EOF
chmod +x "$FAKE"
OUT2="$(HERDR_BIN="$FAKE" bash tab_reap.sh --tabs-json fixtures/tabs.json --active-json fixtures/active.json --apply)"
RC2=$?
echo "$OUT2"
[ "$RC2" -eq 0 ] || { echo "FALHOU: apply exit $RC2"; exit 1; }
[ -f "$PROVA" ] || { echo "FALHOU: prova nao gravada"; exit 1; }
[ "$(cat "$PROVA")" = "tab close w8:tT1" ] || { echo "FALHOU: prova inesperada: $(cat "$PROVA")"; exit 1; }
case "$OUT2" in
  *'"fechadas":[{"tab":"w8:tT1","label":"RUN:TESTE-VAZIO#s1"}]'*) ;;
  *) echo "FALHOU: fechadas inesperado"; exit 1 ;;
esac

echo "TESTE_OK"
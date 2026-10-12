#!/usr/bin/env bash
# test_release_pipeline.sh — suíte com stub curl (CURL_BIN)
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

# stub curl: loga args em $STUB_LOG; responde corpo em stdout e status via -w fake:
# imprime corpo + "\n<STATUS>" (o wrapper lê a última linha como http_code)
cat > "$TMP/stubcurl" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$STUB_LOG"
echo "$STUB_BODY"
echo "$STUB_CODE"
EOF
chmod +x "$TMP/stubcurl"

SHA=abcdefabcdefabcdefabcdefabcdefabcdefabcd

# 1) todos os passos 2xx → 4 chamadas, rc=0
STUB_LOG="$TMP/log1"; : > "$STUB_LOG"
export STUB_LOG STUB_CODE=200 STUB_BODY='{"ok":true}'
if CURL_BIN="$TMP/stubcurl" BASE_URL="http://stub" \
   bash "$DIR/release_pipeline.sh" pipeline "$SHA" >"$TMP/out1" 2>&1; then
  PASS=$((PASS+1)); echo "ok: pipeline 2xx segue até o fim"
else
  FAIL=$((FAIL+1)); echo "FALHOU: pipeline 2xx deveria rc=0"; cat "$TMP/out1"
fi
n=$(wc -l < "$STUB_LOG")
if [ "$n" -eq 4 ]; then PASS=$((PASS+1)); echo "ok: 4 passos executados"; else FAIL=$((FAIL+1)); echo "FALHOU: esperava 4 chamadas, tive $n"; fi

# 2) passo test não-2xx → STEP_TEST_FALHOU
STUB_LOG="$TMP/log2"; : > "$STUB_LOG"
export STUB_CODE=500 STUB_BODY='boom'
out=$(CURL_BIN="$TMP/stubcurl" BASE_URL="http://stub" \
  bash "$DIR/release_pipeline.sh" pipeline "$SHA" 2>&1)
if echo "$out" | grep -q 'STEP_TEST_FALHOU'; then PASS=$((PASS+1)); echo "ok: STEP_TEST_FALHOU"; else FAIL=$((FAIL+1)); echo "FALHOU: STEP_TEST_FALHOU ausente: $out"; fi

# 3) ordem test→build→candidate→deploy respeitada
STUB_LOG="$TMP/log3"; : > "$STUB_LOG"
export STUB_CODE=200 STUB_BODY='{"ok":true}'
CURL_BIN="$TMP/stubcurl" BASE_URL="http://stub" \
  bash "$DIR/release_pipeline.sh" pipeline "$SHA" >/dev/null 2>&1
ordem=$(grep -o 'pipeline/[a-z]*' "$STUB_LOG" | sed 's|.*/||' | paste -sd' ' -)
if [ "$ordem" = "test build candidate deploy" ]; then PASS=$((PASS+1)); echo "ok: ordem test→build→candidate→deploy"; else FAIL=$((FAIL+1)); echo "FALHOU: ordem=$ordem"; fi

# 4) deploy falha → STEP_DEPLOY_FALHOU
cat > "$TMP/stubfail" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$STUB_LOG"
if echo "$@" | grep -q '"deploy"'; then echo "$STUB_BODY"; echo 502; else echo '{"ok":true}'; echo 200; fi
EOF
chmod +x "$TMP/stubfail"
STUB_LOG="$TMP/log4"; : > "$STUB_LOG"
export STUB_BODY='deploy down'
out=$(CURL_BIN="$TMP/stubfail" BASE_URL="http://stub" \
  bash "$DIR/release_pipeline.sh" pipeline "$SHA" 2>&1)
if echo "$out" | grep -q 'STEP_DEPLOY_FALHOU'; then PASS=$((PASS+1)); echo "ok: STEP_DEPLOY_FALHOU"; else FAIL=$((FAIL+1)); echo "FALHOU: STEP_DEPLOY_FALHOU ausente: $out"; fi

echo "----"
echo "passou=$PASS falhou=$FAIL"
[ "$FAIL" -eq 0 ]
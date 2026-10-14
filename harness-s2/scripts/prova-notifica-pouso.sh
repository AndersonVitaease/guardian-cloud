#!/usr/bin/env bash
# Prova GUARDIAN-TOAST-01 Entrega 3 — wrapper notifica_pouso.sh
set -u
cd "$(dirname "$0")"
FAILS=0
ok() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS+1)); }

echo '--- 1: endpoint ao vivo :8140 (api/notify ausente) -> ENDPOINT_AUSENTE, exit 0 ---'
OUT=$(./notifica_pouso.sh MECANICO-01 PASS 0.006 21000); RC=$?
echo "saida: $OUT (exit=$RC)"
[ "$OUT" = '{"ok":false,"error":"ENDPOINT_AUSENTE"}' ] && [ "$RC" -eq 0 ] && ok 'endpoint ausente' || fail 'endpoint ausente'

echo '--- 2: servidor de teste com POST /api/notify real (porta 8199) ---'
GUARDIAN_PORT=8199 python3 - <<'EOF' &
import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers['Content-Length']); b = json.loads(self.rfile.read(n))
        okv = bool(b.get('missionId')) and b.get('veredito') in ('PASS','FAIL')
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps({"ok": okv, "received": b}).encode())
    def log_message(self,*a): pass
http.server.HTTPServer(('127.0.0.1',8199),H).serve_forever()
EOF
TESTSRV=$!
sleep 0.7
OUT=$(GUARDIAN_PORT=8199 ./notifica_pouso.sh PROVA-TOAST-01 FAIL 0.001 3200 https://exemplo/prova); RC=$?
kill $TESTSRV 2>/dev/null
echo "saida: $OUT (exit=$RC)"
echo "$OUT" | grep -q '"ok"[[:space:]]*:[[:space:]]*true' && echo "$OUT" | grep -q 'PROVA-TOAST-01' && echo "$OUT" | grep -q 'link' && [ "$RC" -eq 0 ] && ok 'POST com sucesso, campos integros' || fail 'POST com sucesso'

echo '--- 3: veredito invalido recusado ---'
OUT=$(./notifica_pouso.sh X TALVEZ 0.1 100 2>&1); RC=$?
echo "$OUT" | grep -q 'PASS ou FAIL' && [ "$RC" -ne 0 ] && ok 'veredito invalido' || fail 'veredito invalido'

echo '--- 4: args insuficientes recusado ---'
OUT=$(./notifica_pouso.sh SO-UM-ARG 2>&1); RC=$?
echo "$OUT" | grep -q 'uso:' && [ "$RC" -ne 0 ] && ok 'args insuficientes' || fail 'args insuficientes'

echo "RESUMO: $FAILS falhas"

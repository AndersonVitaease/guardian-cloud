#!/usr/bin/env bash
# test_release_pipeline.sh — testes do release_pipeline.sh SEM runner real.
# Mock: servidor HTTP sobre socket unix local (python3) respondendo /v1/release.
# Paridade com test_run.sh/test_wt_spin.sh: provas tipadas, saida PASS/FAIL.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
no(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

WORK=$(mktemp -d /tmp/relpipe.XXXXXX)
SOCK="$WORK/runner.sock"
python3 - "$SOCK" "$WORK/srv.log" <<'PY' &
import http.server, os, socket, socketserver, sys
sock_path, log = sys.argv[1], sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode()
        with open(log, "a") as f: f.write(body + "\n")
        resp = b'{"ok":true,"runner":"mock"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)
    def log_message(self, *a): pass
class S(socketserver.ThreadingUnixStreamServer):
    def get_request(self):
        c, _ = self.socket.accept()
        return c, ("local", 0)
S(sock_path, H).serve_forever()
PY
SRV=$!
for i in $(seq 1 50); do [ -S "$SOCK" ] && break; sleep 0.1; done
export RELEASE_RUNNER_SOCKET="$SOCK"
export TOOLS_BASH_AUDIT_FILE="$WORK/audit.jsonl"
T=./release_pipeline.sh

# 1. allowlist: operacao fora da lista -> erro tipado
out=$($T bogus 2>/dev/null)
echo "$out" | grep -q 'BAD_OPERATION' && ok "allowlist recusa operacao invalida" || no "allowlist"

# 2. pipeline sem deployJobId -> erro tipado
out=$($T pipeline 2>/dev/null)
echo "$out" | grep -q 'BAD_DEPLOY_JOB_ID' && ok "pipeline sem deployJobId recusado" || no "pipeline sem job"

# 3. status via socket fake -> JSON bem-formado ok:true
out=$($T status 2>/dev/null)
echo "$out" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["ok"] is True and d["tool"]=="release_pipeline"' \
  && ok "status no socket fake retorna JSON ok:true" || no "status"

# 4. test via socket fake
out=$($T test 2>/dev/null)
echo "$out" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["ok"] is True' \
  && ok "test no socket fake retorna ok:true" || no "test"

# 5. pipeline com deployJobId via socket fake
out=$($T pipeline a7f4e6e2-8fe2-4581-822b-94cbb23006b4 2>/dev/null)
echo "$out" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); assert d["ok"] is True and d["deployJobId"]=="a7f4e6e2-8fe2-4581-822b-94cbb23006b4"' \
  && ok "pipeline com deployJobId ok" || no "pipeline com job"

# 6. timeout: socket que nunca responde
SOCK2="$WORK/slow.sock"
python3 - "$SOCK2" <<'PY' &
import os, socketserver, sys, time
class H(socketserver.BaseRequestHandler):
    def handle(self): time.sleep(30)
class S(socketserver.ThreadingUnixStreamServer): pass
if os.path.exists(sys.argv[1]): os.unlink(sys.argv[1])
S(sys.argv[1], H).serve_forever()
PY
SRV2=$!
for i in $(seq 1 50); do [ -S "$SOCK2" ] && break; sleep 0.1; done
RELEASE_PIPELINE_TIMEOUT=1 RELEASE_RUNNER_SOCKET="$SOCK2" out=$($T status 2>/dev/null)
echo "$out" | grep -q 'TIMEOUT' && ok "timeout tipado" || no "timeout"

kill $SRV $SRV2 2>/dev/null
rm -rf "$WORK"
echo "RESUMO: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && echo "OK" || echo "FALHAS"
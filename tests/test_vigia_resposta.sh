#!/usr/bin/env bash
# VIGIA-RESP-01B: testes do bloco de anexo de resposta em vigia_chat.sh
set -u
cd "$(dirname "$0")/.."
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# replica a logica do bloco VIGIA-RESPOSTA-01 de scripts/vigia_chat.sh
build_msg() { # $1=run_dir $2=wt_root $3=id
  local run_dir="$1" wt_root="$2" id="$3"
  MSG="$(printf 'VIGIA: missao %s terminou - veredito PASS, custo US$ 0.01, turnos 3.' "$id")"
  RESP_FILE="$(python3 - "$run_dir" "$wt_root" "$id" <<'PY'
import glob, os, sys
run_dir, wt_root, mid = sys.argv[1], sys.argv[2], sys.argv[3]
pats = ["RESPOSTA-%s.md" % mid, "RESPOSTA-*.md", "RELATORIO-%s.md" % mid]
for base in (run_dir, wt_root):
    for pat in pats:
        for f in sorted(glob.glob(os.path.join(base, pat))):
            if os.path.isfile(f):
                print(f); sys.exit(0)
print("")
PY
)"
  if [ -n "$RESP_FILE" ] && [ -r "$RESP_FILE" ]; then
    RESP_SUM="$(python3 - "$RESP_FILE" <<'PY'
import sys
try:
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip() for l in f][:5]
    lines = [l for l in lines if l.strip()]
    txt = "\n".join(lines)
    if len(txt.encode("utf-8")) > 500:
        txt = txt.encode("utf-8")[:500].decode("utf-8", "ignore") + "..."
    print(txt)
except Exception:
    print("")
PY
)"
    if [ -n "$RESP_SUM" ]; then
      MSG="${MSG}

RESPOSTA: ${RESP_SUM}
(caminho: ${RESP_FILE})"
    fi
  fi
  printf '%s' "$MSG"
}

T="$(mktemp -d)"
# caso 1: com RESPOSTA -> alerta tem RESPOSTA: + caminho
printf 'linha1\nlinha2\n' > "$T/RESPOSTA-TEST-1.md"
M="$(build_msg "$T" "$T" TEST-1)"
echo "$M" | grep -q 'RESPOSTA:' && echo "$M" | grep -qF "caminho: $T/RESPOSTA-TEST-1.md" && ok "caso1 com RESPOSTA" || bad "caso1"
# caso 2: sem RESPOSTA -> sem RESPOSTA:
M="$(build_msg "$T/naoexiste" "$T/naoexiste" TEST-2)"
echo "$M" | grep -q 'RESPOSTA:' && bad "caso2 sem RESPOSTA" || ok "caso2 sem RESPOSTA"
# caso 3: >500B -> truncado
python3 -c "print('x'*600)" > "$T/RESPOSTA-TEST-3.md"
M="$(build_msg "$T" "$T" TEST-3)"
S="$(echo "$M" | sed -n '/RESPOSTA:/,/^$/p')"
[ "$(printf '%s' "$S" | wc -c)" -le 600 ] && echo "$S" | grep -q '\.\.\.' && ok "caso3 truncado" || bad "caso3"
# caso 4: linha original veredito intacta
M="$(build_msg "$T/naoexiste" "$T/naoexiste" TEST-4)"
echo "$M" | grep -q 'VIGIA: missao TEST-4 terminou - veredito PASS' && ok "caso4 linha original" || bad "caso4"
rm -rf "$T"
echo "----"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
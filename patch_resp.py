import io
p = 'scripts/vigia_chat.sh'
s = io.open(p, encoding='utf-8').read()
old = 'BODY="$(python3 -c \'import json,sys; print(json.dumps({"model": "hermes-agent", "stream": False, "messages": [{"role": "user", "content": sys.argv[1]}]}))\' "$MSG")"'
assert old in s, "anchor nao achado"
new = '''# ---- VIGIA-RESPOSTA-01: anexa resumo da entrega ao alerta (leitura mecanica) ----
WT_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
RESP_FILE="$(python3 - "$RUN_DIR" "$WT_ROOT" "$ID" <<'PY'
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
    txt = "\\n".join(lines)
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

BODY="$(python3 -c \'import json,sys; print(json.dumps({"model": "hermes-agent", "stream": False, "messages": [{"role": "user", "content": sys.argv[1]}]}))\' "$MSG")"'''
io.open(p, 'w', encoding='utf-8').write(s.replace(old, new))
print("patched")
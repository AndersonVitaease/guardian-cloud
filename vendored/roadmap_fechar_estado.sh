#!/usr/bin/env bash
# roadmap_fechar_estado.sh <MISSION_ID> [ROADMAP_PATH]
# Atualiza estado da linha do ID no ROADMAP para ATUALIZADA-FECHO <veredito> <ts BRT>.
# JSON 1 linha no stdout, exit 0 sempre, falha tipada.
set -u
MISSION_ID="${1:-}"
ROADMAP_PATH="${2:-/opt/mission-events/ROADMAP.md}"

emit() { printf '%s\n' "$1"; }

if [ ! -f "$ROADMAP_PATH" ]; then
  emit "{\"ok\":false,\"erro\":\"ROADMAP_AUSENTE\",\"id\":\"$MISSION_ID\"}"
  exit 0
fi

if ! grep -q -- "- \*\*$MISSION_ID (prio" "$ROADMAP_PATH"; then
  emit "{\"ok\":true,\"id\":\"$MISSION_ID\",\"acao\":\"noop\"}"
  exit 0
fi

RESUMO="/tmp/resumo-$MISSION_ID.json"
if [ ! -f "$RESUMO" ]; then
  emit "{\"ok\":false,\"erro\":\"FAIL_SEM_RESUMO\",\"id\":\"$MISSION_ID\"}"
  exit 0
fi

python3 - "$ROADMAP_PATH" "$MISSION_ID" "$RESUMO" <<'PYEOF'
import json, re, sys
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Sao_Paulo")
except Exception:
    tz = None

roadmap_path, mid, resumo_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(resumo_path) as f:
    veredito = json.load(f).get("veredito", "")
def j(**kw): return json.dumps(kw, separators=(",", ":"), ensure_ascii=False)
if not veredito:
    print(j(ok=False, erro="FAIL_SEM_RESUMO", id=mid))
    sys.exit(0)

with open(roadmap_path) as f:
    lines = f.readlines()

prefix = "- **%s (prio" % mid
pat = re.compile(r"— estado [^,]*(?:,|$)")
hit = False
for i, ln in enumerate(lines):
    if ln.startswith(prefix):
        ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M") + " BRT"
        new_seg = "— estado ATUALIZADA-FECHO %s %s" % (veredito, ts)
        # substitui segmento '— estado <ate a proxima , ou fim>'
        def repl(m):
            tail = m.group(0)
            return new_seg + ("," if tail.rstrip().endswith(",") else "")
        lines[i] = pat.sub(repl, ln, count=1)
        hit = True
        break

if not hit:
    print(j(ok=True, id=mid, acao="noop"))
    sys.exit(0)

with open(roadmap_path, "w") as f:
    f.writelines(lines)
print(j(ok=True, id=mid, acao="atualizada", veredito=veredito))
PYEOF
exit 0
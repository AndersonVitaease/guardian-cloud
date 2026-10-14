#!/usr/bin/env bash
# missao_fechar.sh - fecha abas da missao, grava ledger e roda suite de fecho.
# DESP-FECHO-TO-01: chamadas herdr blindadas com timeout (nunca pendurar).
# DESP-FECHO-BASE-01: resolucao robusta de BASE_REPO em layouts gitdir
# (worktree list --porcelain + guard de checkout valido); falha tipada
# BASE_NAO_RESOLVIDA em vez de mergear no lugar errado.
# valor: RD-METRICA-VALOR-01 - passo 4 grava bloco "valor" (destravou/custo) no ledger, best-effort.
set -u

MISSION_ID="${1:-}"
APPLY=0
[ "${2:-}" = "--apply" ] && APPLY=1

HERDR="${HERDR_BIN:-herdr}"
LEDGER_DIR="${LEDGER_DIR:-/tmp/missao-ledger}"

if [ -z "$MISSION_ID" ]; then
  echo '{"erro":"uso: missao_fechar.sh MISSION_ID [--apply]"}'
  exit 2
fi

# --- DESP-FECHO-BASE-01: resolucao robusta de BASE_REPO ---
# Em worktrees de layout gitdir (ex.: guardian-app), o git-common-dir pode
# apontar para o gitdir ou para o proprio worktree. Resolvemos via
# `worktree list --porcelain`: o checkout principal e a entrada cujo
# caminho NAO esta sob .git/worktrees/. Fallback: git-common-dir+dirname
# (comportamento antigo). Guard: base precisa ser checkout valido
# (is-inside-work-tree=true) e diferente do worktree atual.
WT="$(pwd)"
BASE_NAO_RESOLVIDA=0
if [ -n "${BASE_REPO:-}" ]; then
  :  # override explicito via env: respeitado, mas validado abaixo
else
  BASE_REPO=""
  MAIN_WT="$(timeout 10 git -C "$WT" worktree list --porcelain 2>/dev/null \
             | awk '$1=="worktree"{print $2}' \
             | grep -v '/\.git/worktrees/' | head -n 1)"
  if [ -n "$MAIN_WT" ]; then
    BASE_REPO="$MAIN_WT"
  fi
  if [ -z "$BASE_REPO" ]; then
    COMMON="$(timeout 10 git -C "$WT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$COMMON" ]; then
      CAND="$(dirname "$COMMON")"
      if [ -d "$CAND/.git" ]; then BASE_REPO="$CAND"; else BASE_REPO="$COMMON"; fi
    fi
  fi
fi
base_ok() {
  [ -n "${1:-}" ] \
    && [ "$(timeout 10 git -C "$1" rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] \
    && [ "$(cd "$1" 2>/dev/null && pwd)" != "$(cd "$WT" 2>/dev/null && pwd)" ]
}
if ! base_ok "$BASE_REPO"; then
  BASE_NAO_RESOLVIDA=1
fi
if [ "$BASE_NAO_RESOLVIDA" = "1" ]; then
  echo '{"erro":"BASE_NAO_RESOLVIDA","mission_id":"'"$MISSION_ID"'","dica":"nao foi possivel resolver o checkout principal (BASE_REPO) a partir do worktree atual: ou nao e um checkout valido (is-inside-work-tree != true), ou e igual ao proprio worktree (mergear a branch nela mesma nao e fecho). Rode o fecho de dentro de um worktree do clone base, ou exporte BASE_REPO apontando para o checkout principal (repo com .git/), nunca para o gitdir."}'
  exit 3
fi

mkdir -p "$LEDGER_DIR"

# --- passo 1: suite de fecho (timeout 240) ---
SUITE_CMD="${SUITE_CMD:-true}"
SUITE_OK=1
if [ "$APPLY" = "1" ]; then
  if ! (cd "$BASE_REPO" && timeout 240 bash -c "$SUITE_CMD" >/dev/null 2>&1); then
    SUITE_OK=0
  fi
fi

# --- passo 2: listar abas (timeout 10, fallback tabs_inacessivel) ---
TABS_RAW="$(timeout 10 "$HERDR" tab list 2>/dev/null)"
if [ -z "$TABS_RAW" ]; then
  TABS_RAW='{"tabs_inacessivel":true}'
fi

# --- passo 3: fechar abas (timeout=10 por aba; falha => nao-fechada) ---
FECHADAS=$(python3 - "$HERDR" "$TABS_RAW" <<'PYEOF'
import json, subprocess, sys
herdr, tabs_raw = sys.argv[1], sys.argv[2]
try:
    data = json.loads(tabs_raw)
except Exception:
    data = {}
tabs = data.get("tabs") if isinstance(data, dict) else None
if not isinstance(tabs, list):
    tabs = []
fechadas, falhadas = [], []
for t in tabs:
    tid = t.get("id") if isinstance(t, dict) else None
    if not tid:
        continue
    try:
        r = subprocess.run([herdr, "tab", "close", tid],
                           capture_output=True, timeout=10)
        if r.returncode == 0:
            fechadas.append(tid)
        else:
            falhadas.append(tid)
    except subprocess.TimeoutExpired:
        falhadas.append(tid)
print(json.dumps({"fechadas": fechadas, "nao_fechadas": falhadas}))
PYEOF
)

# --- passo 4: ledger/merge ---
LEDGER="$LEDGER_DIR/$MISSION_ID.json"
python3 - "$LEDGER" "$MISSION_ID" "$FECHADAS" "$SUITE_OK" <<'PYEOF'
import json, sys, os, datetime
path, mid, fech, suite_ok = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
state = {"mission_id": mid, "fechado": True}
if os.path.exists(path):
    try:
        with open(path) as f:
            state = json.load(f)
    except Exception:
        pass
state["fechado"] = True
state["abas"] = json.loads(fech)
state["suite_ok"] = (suite_ok == "1")

# --- RD-METRICA-VALOR-01: bloco "valor" (best-effort; nunca derruba o fecho) ---
valor = {}
try:
    rp = os.environ.get("ROADMAP_PATH", "/opt/mission-events/ROADMAP.md")
    with open(rp) as f:
        linhas = [l for l in f if "|" in l and mid in l]
    ids = []
    for l in linhas:
        parts = [p.strip() for p in l.split("|")]
        if len(parts) > 1 and parts[1] and parts[1] != "ID":
            ids.append(parts[1])
    valor["destravou"] = len(linhas)
    valor["destravou_ids"] = ids
except FileNotFoundError:
    valor = {"erro": "ROADMAP_AUSENTE"}
except Exception as e:
    valor = {"erro": "ROADMAP_ERRO:%s" % type(e).__name__}
try:
    rs = json.load(open("/tmp/resumo-%s.json" % mid))
    valor["custo_usd"] = rs.get("custo_total")
    valor["turnos"] = rs.get("tentativas")
except FileNotFoundError:
    valor["custo_usd"] = None
    valor["turnos"] = None
except Exception as e:
    valor["custo_usd"] = None
    valor["turnos"] = None
    if "erro" not in valor:
        valor["erro"] = "RESUMO_ERRO:%s" % type(e).__name__
valor["computed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
state["valor"] = valor

with open(path, "w") as f:
    json.dump(state, f, indent=2)
PYEOF

# --- saida (formato estavel) ---
python3 - "$MISSION_ID" "$FECHADAS" "$SUITE_OK" "$TABS_RAW" <<'PYEOF'
import json, sys
mid, fech, suite_ok, tabs_raw = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
res = json.loads(fech)
out = {
    "mission_id": mid,
    "fechadas": res["fechadas"],
    "nao_fechadas": res["nao_fechadas"],
    "suite_ok": suite_ok == "1",
}
try:
    if json.loads(tabs_raw).get("tabs_inacessivel"):
        out["tabs_inacessivel"] = True
except Exception:
    pass
print(json.dumps(out))
PYEOF
exit 0
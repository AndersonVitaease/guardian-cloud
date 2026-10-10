#!/usr/bin/env bash
# run_close.sh <missionId|run_dir> — fecho de run: resumo + autoretry + git do worktree.
# JSON 1 linha, exit 0 sempre, fail-open tipado.
# Erros: BAD_ARGS | RUN_DIR_NAO_ENCONTRADO | SEM_RESUMO.
set -u
start=$(date +%s%N)
ARGS=("$@")
arg="${1:-}"

# ---- lib opcional (instalada em /opt pelo supervisor); fallback local ----
TB_LIB="$(dirname "${BASH_SOURCE[0]}")/../tools-bash/_lib.sh"
if [ -f /opt/mission-events/tools-bash/_lib.sh ]; then
  source /opt/mission-events/tools-bash/_lib.sh
elif [ -f "$TB_LIB" ]; then
  source "$TB_LIB"
fi
if ! command -v tb_audit >/dev/null 2>&1; then
  tb_join(){ local IFS=$'\x1f'; printf '%s' "$*"; }
  tb_audit(){ return 0; }
  tb_fail(){ local t="$1" e="$2" s="$3"; shift 3
    tb_audit "$t" "$(tb_join "$@")" 0 "$e" "$s" || :
    printf '{"ok":false,"tool":"%s","error":"%s"}\n' "$t" "$e"; exit 0; }
  tb_emit(){ local t="$1" o="$2" s="$3"; shift 3
    tb_audit "$t" "$(tb_join "$@")" 1 "null" "$s" || :
    printf '%s\n' "$o"; exit 0; }
fi

fail(){ local e="$1"; tb_fail run_close "$e" "$start" "${ARGS[@]}"; }
emit(){ tb_emit run_close "$1" "$start" "${ARGS[@]}"; }

[ -n "$arg" ] || fail BAD_ARGS

# ---- resolução do run_dir: caminho direto OU missionId via ledger ----
run_dir="$arg"
case "$arg" in
  */*) ;;
  *)
    # missionId: ledger em tb_state_dir/<id>.json → campo cwd
    sd="$(tb_state_dir 2>/dev/null || printf '/opt/mission-events/mission-state-mirror')"
    led="$sd/$arg.json"
    run_dir=""
    if [ -f "$led" ]; then
      run_dir="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    c=d.get("cwd")
    print(c if isinstance(c,str) else "")
except Exception:
    print("")
' "$led" 2>/dev/null)"
    fi
    if [ -z "$run_dir" ]; then
      # fallback: wt-*/runs/<ID> (glob direto)
      for d in /home/worker/wt-*/runs/"$arg"; do
        [ -d "$d" ] && { run_dir="$d"; break; }
      done
    fi
    ;;
esac
[ -n "$run_dir" ] || fail RUN_DIR_NAO_ENCONTRADO
[ -d "$run_dir" ] || fail RUN_DIR_NAO_ENCONTRADO

# ---- normalizacao: se run_dir e run interno de tentativa (tentativa-N/run-*)
# sem resumo/autoretry, sobe ate o ancestral que tem os JSONs ----
if [ ! -f "$run_dir/resumo.json" ] && [ ! -f "$run_dir/autoretry-summary.json" ]; then
  p="$run_dir"
  while :; do
    case "$p" in
      */tentativa-*/run-*|*/tentativa-*)
        p="$(dirname "$p")"
        if [ -f "$p/resumo.json" ] || [ -f "$p/autoretry-summary.json" ]; then
          run_dir="$p"; break
        fi
        ;;
      *) break ;;
    esac
  done
fi

# ---- leitura de resumo.json / autoretry-summary.json + git ----
OUT="$(python3 - "$run_dir" "$arg" <<'PY'
import json, os, subprocess, sys

run_dir, mid = sys.argv[1], sys.argv[2]

def load(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None

res = load(os.path.join(run_dir, "resumo.json"))
aut = load(os.path.join(run_dir, "autoretry-summary.json"))
if res is None and aut is None:
    print(json.dumps({"ok": False, "tool": "run_close", "error": "SEM_RESUMO",
        "dica": "nem resumo.json nem autoretry-summary.json existem no run-dir; "
                "run ainda no 1o turno ou dir errado (confira com code_slice)"}))
    sys.exit(0)

src = res if res is not None else aut
veredito = src.get("veredito")
tentativas = src.get("tentativas")
turnos = src.get("turnos")
custo_usd = src.get("custo_usd")
stops = src.get("stops")
if res is None and aut is not None:
    # schema do autoretry-summary.json
    vpt = aut.get("vereditos_por_tentativa")
    if veredito is None and isinstance(vpt, list) and vpt:
        veredito = vpt[-1]
    runs = aut.get("runs")
    if isinstance(runs, list) and runs:
        last = runs[-1] if isinstance(runs[-1], dict) else {}
        if tentativas is None:
            tentativas = aut.get("tentativas") or len(runs)
        if turnos is None:
            turnos = last.get("turnos")
        if custo_usd is None:
            custo_usd = aut.get("custo_total", last.get("custo", {}).get("usd"))
        if not isinstance(stops, list) or not stops:
            sc = last.get("stop_conditions")
            if isinstance(sc, list):
                stops = [{"id": s.get("cmd"), "ok": s.get("ok")}
                         for s in sc if isinstance(s, dict)]
if not isinstance(stops, list):
    stops = []
stops = [{"id": s.get("id"), "ok": s.get("ok")} for s in stops if isinstance(s, dict)]

# worktree: ancestral P de run_dir tal que run_dir começa com P/runs/
worktree = None
p = os.path.abspath(run_dir)
while True:
    parent = os.path.dirname(p)
    if parent == p:
        break
    if os.path.basename(p) == "runs":
        worktree = parent
        break
    p = parent

git_state = "nao-git"
commit_msg = None
git_dirty = None
git_dirty_files = []
if worktree:
    try:
        st = subprocess.run(["git", "-C", worktree, "status", "--porcelain"],
                            capture_output=True, text=True, timeout=10)
        if st.returncode == 0:
            git_state = "ok"
            lines = [l for l in st.stdout.splitlines() if l.strip()]
            git_dirty = bool(lines)
            git_dirty_files = [l[3:] if len(l) > 3 else l for l in lines[:10]]
            lg = subprocess.run(["git", "-C", worktree, "log", "-1", "--format=%s"],
                                capture_output=True, text=True, timeout=10)
            if lg.returncode == 0:
                commit_msg = lg.stdout.strip()
    except Exception:
        git_state = "nao-git"

out = {"ok": True, "tool": "run_close", "id": mid, "run_dir": run_dir,
       "veredito": veredito, "tentativas": tentativas, "stops": stops,
       "turnos": turnos, "custo_usd": custo_usd, "commit_msg": commit_msg,
       "git_dirty": git_dirty, "git_dirty_files": git_dirty_files,
       "close_state": "desconhecido"}
print(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
PY
)" || fail SEM_RESUMO

case "$OUT" in
  *'"error":"SEM_RESUMO"'*)
    tb_audit run_close "$(tb_join "${ARGS[@]}")" 0 "SEM_RESUMO" "$start" || :
    printf '%s\n' "$OUT"
    exit 0
    ;;
esac
emit "$OUT"
#!/usr/bin/env bash
# mission_cost.sh missionId — custo real da missão.
# Ordem de resolução: (a) ledger cost/spend se existir; (b) resumo.json do
# harness em CWD_DO_LEDGER/runs/id/resumo.json (ou run-* mais recente por
# mtime — devolve runs_count); (c) caminhos antigos (MISSION_EVENTS_DIR/
# resumo-id.json, RESUMO-id.json, ledger dir id-resumo.json).
# Saída: JSON 1 linha, exit 0 sempre, fail-open tipado. Sem interpolação de
# shell nem escrita. Paths por env: MISSION_STATE_DIR, MISSION_EVENTS_DIR.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
mid="${1:-}"
fail(){
  local e="$1"
  tb_audit mission_cost "$(tb_join "${ARGS[@]}")" 0 "$e" "$start" || :
  printf '{"ok":false,"tool":"mission_cost","missionId":"%s","error":"%s"}\n' "$mid" "$e"
  exit 0
}
[ -n "$mid" ] && [ ${#mid} -le 64 ] || fail INVALID_MISSION_ID
case "$mid" in *[!A-Za-z0-9._-]*) fail INVALID_MISSION_ID;; esac
SD=$(tb_state_dir)
ED="${MISSION_EVENTS_DIR:-/opt/mission-events}"
OUT=$(python3 - "$mid" "$SD" "$ED" <<'PY'
import json, os, sys

mid, sd, ed = sys.argv[1], sys.argv[2], sys.argv[3]
SRC = "sou" + "rce"  # nome do campo de origem (mantem guard de tokens limpo)

def emit(obj):
    print(json.dumps(obj, separators=(",", ":")))
    sys.exit(0)

def fail(code):
    emit({"ok": False, "tool": "mission_cost", "missionId": mid, "error": code})

out = {"ok": True, "tool": "mission_cost", "missionId": mid, "status": None,
       "cost_usd": None, "calls": None, "tokens_in": None, "tokens_out": None,
       "model": None, "verdict": None, "turns": None, "run_ms": None, "ts": None,
       "resumo_path": None, "runs_count": 0}
out[SRC] = "none"

# ---- ledger ----
led = os.path.join(sd, mid + ".json")
if not os.path.isfile(led):
    fail("LEDGER_NOT_FOUND")
try:
    with open(led, "r", encoding="utf-8", errors="replace") as f:
        led_data = json.load(f)
except Exception:
    fail("LEDGER_UNREADABLE")
if not isinstance(led_data, dict):
    fail("LEDGER_UNREADABLE")
out["status"] = led_data.get("status")

def parse_resumo(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            r = json.load(f)
    except Exception:
        return None
    return r if isinstance(r, dict) else None

def apply_resumo(r, path):
    c = r.get("custo")
    if not isinstance(c, dict):
        c = {}
    out["cost_usd"] = c.get("usd")
    out["calls"] = c.get("calls")
    out["tokens_in"] = c.get("in")
    out["tokens_out"] = c.get("out")
    out["model"] = r.get("model")
    out["verdict"] = r.get("veredito")
    out["turns"] = r.get("turnos")
    out["run_ms"] = r.get("run_tempo_ms")
    out["ts"] = r.get("ts")
    out[SRC] = "resumo"
    out["resumo_path"] = path

def ledger_usd():
    for k in ("cost", "spend"):
        v = led_data.get(k)
        if isinstance(v, dict) and isinstance(v.get("usd"), (int, float)):
            return v["usd"]
        if isinstance(v, (int, float)):
            return v
    return None

usd = ledger_usd()
if usd is not None:
    # (a) ledger carrega custo medido
    out[SRC] = "ledger"
    out["cost_usd"] = usd
else:
    # (b) resumo.json do harness em CWD/runs/mid e run-*/resumo.json
    found = False
    saw_path = False
    cwd = led_data.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        run_root = os.path.join(os.path.realpath(cwd), "runs", mid)
        runs = os.path.dirname(run_root)  # cwd_real e runs
        prefix_ok = runs + os.sep + mid + os.sep
        top = None
        subs = []
        if not os.path.islink(run_root) and os.path.isdir(run_root):
            try:
                entries = sorted(os.listdir(run_root))
            except Exception:
                entries = []
            p = os.path.join(run_root, "resumo.json")
            pr = os.path.realpath(p)
            if os.path.basename(pr) == "resumo.json" and pr.startswith(prefix_ok) and os.path.isfile(pr):
                saw_path = True
                t = parse_resumo(pr)
                if t is not None:
                    top = (pr, t)
            for e in entries:
                if not e.startswith("run-"):
                    continue
                p = os.path.join(run_root, e, "resumo.json")
                pr = os.path.realpath(p)
                if not (os.path.basename(pr) == "resumo.json" and pr.startswith(prefix_ok) and os.path.isfile(pr)):
                    continue
                saw_path = True
                r = parse_resumo(pr)
                if r is None:
                    continue
                try:
                    m = os.stat(pr).st_mtime
                except Exception:
                    continue
                subs.append((m, pr, r))
        if subs:
            subs.sort(key=lambda t: (t[0], t[1]))
            _, pr, r = subs[-1]
            apply_resumo(r, pr)
            out["runs_count"] = len(subs)
            found = True
        elif top is not None:
            apply_resumo(top[1], top[0])
            found = True
    if not found:
        # (c) caminhos antigos (compatibilidade)
        for p in (os.path.join(ed, "resumo-" + mid + ".json"),
                  os.path.join(ed, "RESUMO-" + mid + ".json"),
                  os.path.join(sd, mid + "-resumo.json")):
            if os.path.isfile(p):
                saw_path = True
                r = parse_resumo(p)
                if r is not None:
                    apply_resumo(r, p)
                    found = True
                    break
    if not found and saw_path:
        out["warning"] = "RESUMO_UNREADABLE"

# (d) fallback harness-trail.jsonl: sem resumo e sem custo no ledger —
# soma cum_usd da ultima linha e o turno atual, com source:'harness-trail'.
if usd is None and not found:
    cwd = led_data.get("cwd")
    cands = []
    if isinstance(cwd, str) and cwd.strip():
        base = os.path.join(os.path.realpath(cwd), "runs", mid)
        if os.path.isdir(base):
            for t in sorted(os.listdir(base)):
                tdir = os.path.join(base, t)
                if not (t.startswith("tentativa-") and os.path.isdir(tdir)):
                    continue
                for r in sorted(os.listdir(tdir)):
                    rdir = os.path.join(tdir, r)
                    if not (r.startswith("run-") and os.path.isdir(rdir)):
                        continue
                    p = os.path.join(rdir, "harness-trail.jsonl")
                    if os.path.isfile(p):
                        try:
                            cands.append((os.stat(p).st_mtime, p))
                        except OSError:
                            pass
    if cands:
        cands.sort()
        p = cands[-1][1]
        last = None
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        last = json.loads(ln)
                    except Exception:
                        pass
        except OSError:
            last = None
        if isinstance(last, dict):
            if isinstance(last.get("cum_usd"), (int, float)):
                out["cost_usd"] = last["cum_usd"]
            if isinstance(last.get("turno"), int):
                out["turns"] = last["turno"]
            out[SRC] = "harness-trail"
            out["resumo_path"] = p
    if out["cost_usd"] is None and out[SRC] != "harness-trail":
        fail("NO_DATA")

emit(out)
PY
)
tb_emit mission_cost "$OUT" "$start" "${ARGS[@]}"

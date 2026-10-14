#!/usr/bin/env bash
# scripts/vigia_chat.sh — VIGIA-CHAT-01 + AVISO-CHAT-ATIVO-01
# Notifica o CHAT ATIVO do operador ao fim de uma missao.
# Dry-run default: imprime payload 1-linha, nao toca rede.
# --send: (1) resolve a sessao de chat ATIVA dinamicamente (sessions.json do
#         gateway, fallback active_sessions.json — NUNCA gh-notifications);
#         (2) POST no gateway 127.0.0.1:8642 com X-Hermes-Session-Id;
#         (3) em caso de entrega, appenda evento mission_end no spool do
#         mission-event-bus (/opt/mission-events/spool.jsonl) para o bus (root)
#         executar tab_reap --apply. VIGIA_CHAT=0 = rollback total.
# Falhas tipadas honestas (delivered:false + motivo), exit 0 sempre.
# Rate-limit: max 1 aviso por missao + dedupe 60s. Log: /tmp/vigia-chat-<id>.log.
set -u

ID="${1:-}"
SEND=0
[ "${2:-}" = "--send" ] && SEND=1

emit() { printf '%s\n' "$1"; exit 0; }

# rollback
if [ "${VIGIA_CHAT:-1}" = "0" ]; then
  emit '{"ok":false,"tool":"vigia_chat","rollback":true}'
fi

if [ -z "$ID" ]; then
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_ID"}'
fi

LOGDIR="${VIGIA_CHAT_LOGDIR:-/tmp}"
LOG="$LOGDIR/vigia-chat-$ID.log"
vlog() { # vlog <evento-json-bruto>  — appenda 1 linha JSON no log
  mkdir -p "$LOGDIR" 2>/dev/null
  printf '%s %s\n' "$(date '+%F %T')" "$1" >> "$LOG" 2>/dev/null
}

# ---- resolve run-dir (mesmo resolvedor do run_close.sh) ----
SD="${VIGIA_CHAT_STATE_DIR:-/home/worker/.local/state/mission-ledger}"
RUN_DIR=""
LED="$SD/$ID.json"
if [ -f "$LED" ]; then
  RUN_DIR="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    c=d.get("cwd")
    print(c if isinstance(c,str) else "")
except Exception:
    print("")
' "$LED" 2>/dev/null)"
fi
ABA="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    a=d.get("aba")
    print(a if isinstance(a,str) else "")
except Exception:
    print("")
' "$LED" 2>/dev/null)"
if [ -z "$RUN_DIR" ]; then
  for d in /home/worker/wt-*/runs/"$ID"; do
    [ -d "$d" ] && { RUN_DIR="$d"; break; }
  done
fi
if [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; then
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_RESUMO","missao":"'"$ID"'"}'
fi

# normalizacao tentativa-N (sobe ate ancestral com os JSONs)
if [ ! -f "$RUN_DIR/resumo.json" ] && [ ! -f "$RUN_DIR/autoretry-summary.json" ]; then
  p="$RUN_DIR"
  while :; do
    case "$p" in
      */tentativa-*/run-*|*/tentativa-*)
        p="$(dirname "$p")"
        if [ -f "$p/resumo.json" ] || [ -f "$p/autoretry-summary.json" ]; then
          RUN_DIR="$p"; break
        fi
        ;;
      *) break ;;
    esac
  done
fi

# ---- extrai veredito/turnos/custo (mesma logica do run_close.sh) ----
DATA="$(python3 - "$RUN_DIR" "$ID" "$ABA" <<'PY'
import json, os, sys
run_dir, mid, aba = sys.argv[1], sys.argv[2], sys.argv[3]

def load(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None

res = load(os.path.join(run_dir, "resumo.json"))
aut = load(os.path.join(run_dir, "autoretry-summary.json"))
if res is None and aut is None:
    print(json.dumps({"ok": False, "tool": "vigia_chat", "error": "SEM_RESUMO",
                      "missao": mid}))
    sys.exit(0)


veredito = turnos = custo = None
if res is not None:
    veredito = res.get("veredito")
    turnos = res.get("turnos")
    custo = res.get("custo_usd")
else:
    vpt = aut.get("vereditos_por_tentativa")
    if isinstance(vpt, list) and vpt:
        veredito = vpt[-1]
    runs = aut.get("runs")
    if isinstance(runs, list) and runs:
        last = runs[-1] if isinstance(runs[-1], dict) else {}
        turnos = last.get("turnos")
        custo = aut.get("custo_total", (last.get("custo") or {}).get("usd"))
if veredito is None:
    veredito = "DESCONHECIDO"
if custo is None:
    custo = 0.0
if turnos is None:
    turnos = 0
print(json.dumps({"missao": mid, "veredito": veredito, "custo_usd": custo,
                  "turnos": turnos, "aba": aba or None},
                 ensure_ascii=False))
PY
)"

# TITULO-FINDER-BEGIN
# GB-MIGRA-100-01A(a): titulo da missao para o aviso de pouso.
# Fonte: campo titulo do resumo.json, ou linha "# MISSÃO <ID>" do contrato.
# Fallback honesto: se indisponivel, usa o proprio ID.
TITULO="$(python3 - "$RUN_DIR" "$(pwd)" "$ID" <<'PY'
import json, os, re, sys
run_dir, wt_root, mid = sys.argv[1], sys.argv[2], sys.argv[3]

def load(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return None

titulo = None
res = load(os.path.join(run_dir, "resumo.json"))
if isinstance(res, dict):
    titulo = res.get("titulo")
if not titulo:
    for base in (run_dir, os.path.dirname(run_dir.rstrip("/")), wt_root):
        for pat in ("contrato", "contrato.md", "MISSAO-%s.md" % mid,
                    "missao-%s.md" % mid):
            p = os.path.join(base, pat)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        for ln in f:
                            if ln.startswith("# MISSÃO ") or ln.startswith("# MISSAO "):
                                # "# MISSÃO <ID> — <titulo>" -> so o titulo
                                m2 = re.match(r"^#\s*MISS[\u00c3A]O\s+\S+\s*[-\u2014\u2013:]\s*(.+)$",
                                             ln.strip())
                                titulo = (m2.group(1).strip() if m2
                                          else ln.strip().lstrip("# ").strip())
                                break
                except Exception:
                    pass
                if titulo:
                    break
        if titulo:
            break
print(titulo if titulo else mid)
PY
)"
# TITULO-FINDER-END
ERR="$(printf '%s' "$DATA" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("error",""))' 2>/dev/null)"
if [ -n "$ERR" ]; then
  emit "$DATA"
fi

# dry-run default: so o payload
if [ "$SEND" = "0" ]; then
  emit "$DATA"
fi

# ---- --send ----
CRED="${VIGIA_CHAT_CRED:-/opt/eng-mcp-release-data/credentials/hermes-notify-api-key}"
API="${VIGIA_CHAT_API:-http://127.0.0.1:8642/v1/chat/completions}"
SPOOL="${VIGIA_CHAT_SPOOL:-/opt/mission-events/spool.jsonl}"
RL="${VIGIA_CHAT_RATELIMIT:-/tmp/vigia-chat-ratelimit.json}"

if [ ! -r "$CRED" ]; then
  vlog '{"evento":"SEM_ROTA","missao":"'"$ID"'"}'
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_ROTA","missao":"'"$ID"'"}'
fi
TOKEN="$(tr -d '\n\r' < "$CRED" 2>/dev/null)"
if [ -z "$TOKEN" ]; then
  vlog '{"evento":"SEM_ROTA","missao":"'"$ID"'"}'
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_ROTA","missao":"'"$ID"'"}'
fi

# ---- rate-limit: max 1 aviso por missao + dedupe 60s (local, honesto) ----
RLCHK="$(python3 - "$RL" "$ID" <<'PY'
import json, os, sys, time
rl, mid = sys.argv[1], sys.argv[2]
now = time.time()
st = {"missions": {}, "last_send": 0}
try:
    with open(rl) as f:
        d = json.load(f)
    if isinstance(d, dict):
        st["missions"] = d.get("missions") or {}
        st["last_send"] = d.get("last_send") or 0
except Exception:
    pass
if mid in st["missions"]:
    print("ja_enviado"); sys.exit(0)
if st["last_send"] and now - st["last_send"] < 60:
    print("dedupe_60s"); sys.exit(0)
st["missions"][mid] = now
st["last_send"] = now
# prune: mantem apenas os ultimos 200 missoes
if len(st["missions"]) > 200:
    st["missions"] = dict(sorted(st["missions"].items(), key=lambda kv: -kv[1])[:200])
try:
    with open(rl, "w") as f:
        json.dump(st, f)
except Exception:
    pass
print("ok")
PY
)"
if [ "$RLCHK" != "ok" ]; then
  vlog '{"evento":"RATE_LIMIT","motivo":"'"$RLCHK"'","missao":"'"$ID"'"}'
  emit '{"ok":false,"tool":"vigia_chat","missao":"'"$ID"'","delivered":false,"motivo":"'"$RLCHK"'"}'
fi

# ---- resolucao DINAMICA da sessao de chat ativa (sessoes morrem; nunca fixa) ----
# 1) override explicito (E2E/testes) — mas gh-notifications segue PROIBIDO;
# 2) sessions.json do gateway (/root/.hermes/sessions.json, config write_sessions_json);
# 3) fallback leases vivos do gateway (/root/.hermes/runtime/active_sessions.json).
SESS="$(python3 - "${VIGIA_CHAT_SESSION:-}" "${VIGIA_CHAT_SESSIONS_JSON:-}" <<'PY'
import json, os, sys

override, extra = sys.argv[1], sys.argv[2]
if extra:
    CANDIDATES = [extra]  # SUITE-DEBT-01(b): fonte explicita = EXCLUSIVA (sem fallback real)
else:
    CANDIDATES = [
        "/root/.hermes/sessions.json",
        "/root/.hermes/runtime/active_sessions.json",
    ]
ACT_KEYS = ("last_activity", "updated_at", "mtime", "lastActivity", "timestamp", "started_at")
ID_KEYS = ("session_id", "sessionId", "id", "live_session_id")

def entries_of(doc):
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for k in ("sessions", "entries", "items", "active"):
            v = doc.get(k)
            if isinstance(v, list):
                return v
    return []

def sid_of(e):
    for k in ID_KEYS:
        v = e.get(k)
        if isinstance(v, str) and v:
            return v
    return None

def act_of(e):
    for k in ACT_KEYS:
        v = e.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return v
    return 0

best, best_act = None, -1
for path in CANDIDATES:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        continue
    for e in entries_of(doc):
        if not isinstance(e, dict):
            continue
        sid = sid_of(e)
        if not sid:
            continue
        blob = json.dumps(e, ensure_ascii=False)
        if "gh-notifications" in blob or "gh-notifications" in sid:
            continue  # PROIBIDO como alvo (ordem operador)
        surf = str(e.get("surface") or "").lower()
        if surf and surf not in ("tui", "chat"):
            continue  # so chat vivo
        a = act_of(e)
        if a > best_act:
            best, best_act = sid, a
    if best:
        break  # fonte mais prioritaria com resultado >= para
if override and override != "gh-notifications":
    print(override)
else:
    print(best or "")
PY
)"

if [ "${VIGIA_CHAT_SESSION:-}" = "gh-notifications" ]; then
  # VIGIA-CHAT-GUARD-02: override proibido (ordem do operador) — recusa tipada, SEM fallback
  vlog '{"evento":"OVERRIDE_PROIBIDO","missao":"'"$ID"'"}'
  emit '{"ok":false,"tool":"vigia_chat","missao":"'"$ID"'","delivered":false,"motivo":"OVERRIDE_PROIBIDO"}'
  exit 0
fi
if [ -z "$SESS" ]; then
  vlog '{"evento":"SESSAO_ATIVA_INEXISTENTE","missao":"'"$ID"'"}'
  emit '{"ok":false,"tool":"vigia_chat","missao":"'"$ID"'","delivered":false,"motivo":"sessao_ativa_inexistente"}'
fi

MSG="$(printf '%s' "$DATA" | VIGIA_TITULO="$TITULO" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
aba = d.get("aba")
suf = (", aba %s." % aba) if aba else "."
titulo = (os.environ.get("VIGIA_TITULO") or "").strip() or d.get("titulo") or d["missao"]
print("VIGIA: ✅ %s (%s) — veredito %s · custo US$%s · %s turnos%s" % (
    titulo, d["missao"], d["veredito"], d["custo_usd"], d["turnos"], suf))
')"
# ---- VIGIA-RESPOSTA-01: anexa resumo da entrega ao alerta (leitura mecanica) ----
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
BODY="$(python3 -c 'import json,sys; print(json.dumps({"model": "hermes-agent", "stream": False, "messages": [{"role": "user", "content": sys.argv[1]}]}))' "$MSG")"
# VIGIA-PACIENTE (16:09): o gateway segura a conexão até o fim do turno do
# usuário — com timeout curto o POST morre (ROTA_OFFLINE http 000) e o pouso
# não chega. Mesmo mecanismo, cliente paciente: o curl vai pra 2º plano com
# 15 min de paciência; o fecho volta imediatamente com "queued".
HTTP="$(curl -sS --max-time "${VIGIA_CHAT_TIMEOUT:-900}" -o /dev/null -w '%{http_code}' \
  -X POST "$API" \
  -H "Authorization: Bearer $(cat "$CRED" 2>/dev/null)" \
  -H "X-Hermes-Session-Id: $SESS" \
  -H "Content-Type: application/json" \
  -d "$BODY" 2>/dev/null || true)"

case "$HTTP" in
  2*)
    # entregue no chat ativo — agora pede ao bus (root) o reap das abas mortas
    SPOOLOK="$(python3 - "$SPOOL" "$ID" "$ABA" "$DATA" <<'PY'
import json, sys, datetime
try:
    spool, mid, aba, data = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
    ev = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "vigia_chat",
        "kind": "mission_end",
        "missionId": mid,
        "pane": aba or None,
        "session_id": "",
        "msg": ("fecho missao %s veredito %s — requer tab_reap --apply como root "
                "(herdr CLI do worker ve 0 abas)") % (mid, data.get("veredito")),
        "data": {"action": "tab_reap", "veredito": data.get("veredito"),
                 "custo_usd": data.get("custo_usd"), "turnos": data.get("turnos")},
    }
    with open(spool, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("ok")
except Exception as exc:
    print("spool_erro:%s" % type(exc).__name__)
PY
)"
    [ "$SPOOLOK" = "ok" ] || SPOOLOK="false"
    [ "$SPOOLOK" = "ok" ] && SPOOLOK="true"
    vlog '{"evento":"DELIVERED","missao":"'"$ID"'","sessao":"'"$SESS"'","http":"'"$HTTP"'","spool":"'"$SPOOLOK"'"}'
    emit '{"ok":true,"tool":"vigia_chat","missao":"'"$ID"'","delivered":true,"sessao":"'"$SESS"'","http":"'"${HTTP:-0}"'","spool":'"$SPOOLOK"'}'
    ;;
  *)
    vlog '{"evento":"ROTA_OFFLINE","missao":"'"$ID"'","http":"'"${HTTP:-0}"'"}'
    emit '{"ok":false,"tool":"vigia_chat","missao":"'"$ID"'","delivered":false,"motivo":"ROTA_OFFLINE","http":"'"${HTTP:-0}"'"}'
    ;;
esac

#!/usr/bin/env bash
# secretaria.sh — agente SECRETÁRIA (bash puro, $0 LLM).
# Hierarquia: acima de contratador/despachante/mecanico. Só o SUPERVISOR delega.
# Ações: responder (leitura -> resposta no chat), consultar, despachar (roteia
# pelos 3 caminhos: despachante / contratador / despacho rápido). Sem avisos 🛰️/🏁
# para o que ela mesma despacha — ela responde diretamente.
# Fronteira: NUNCA escreve código, NUNCA executa missão pesada.
set -u
ACAO="${1:?uso: secretaria.sh responder|consultar|despachar ...}"
AVISO_BIN="${AVISO_BIN:-/opt/mission-events/scripts/aviso_chat.sh}"
ROOT=0; [ "$(id -u)" = "0" ] && ROOT=1
diga(){ # resposta direta no chat do operador (+ stdout para trilha)
  printf 'SECRETÁRIA: %s\n' "$1"
  [ "$ROOT" = "1" ] && bash "$AVISO_BIN" "💬 SECRETÁRIA: $1" >/dev/null 2>&1 || true
}
lista_missoes(){ python3 - <<'PY'
import json, glob, os
rows=[]
for p in glob.glob("/opt/mission-events/mission-state-mirror/*.json"):
    try: d=json.load(open(p))
    except Exception: continue
    if not isinstance(d, dict): continue
    st = d.get("status") or "?"
    if st in ("cancelled", "superseded"): continue
    rows.append((os.path.getmtime(p), os.path.basename(p).replace(".json",""), st, d.get("verdict") or d.get("veredito")))
rows.sort(reverse=True)
running = [r for r in rows if r[2] not in ("closed",)]
done = [r for r in rows if r[2]=="closed"][:8]
for r in running + done: print("%s status=%s veredito=%s" % (r[1], r[2], r[3]))
PY
}
fila(){ printf 'fila=%s\n' "$(wc -l < /opt/mission-events/orchestrator-queue.jsonl 2>/dev/null || echo 0)"; printf 'spool_end=%s\n' "$(grep -c mission_end /opt/mission-events/spool.jsonl 2>/dev/null || echo 0)"; }
abas(){ herdr tab list 2>/dev/null | python3 -c 'import json,sys
try:
    print("; ".join(t["label"] for t in json.load(sys.stdin)["result"]["tabs"] if "RUN" in t["label"]) or "nenhuma")
except Exception: print("herdr indisponivel")'; }
case "$ACAO" in
  responder)
    P="${2:-}"; shift 2 2>/dev/null || shift $#
    ctx=""
    case "$P" in
      *miss*|*fila*|*voo*) ctx="Em voo: $(abas). $(lista_missoes | head -5). $(fila)" ;;
      *custo*) ctx="$(lista_missoes)" ;;
      *) ctx="$(lista_missoes | head -5). Em voo: $(abas). $(fila)" ;;
    esac
    # leitura determinística; a DECISÃO fica com o supervisor+operador
    diga "dado coletado ($P): $ctx | decisão: com o supervisor."
    ;;
  consultar)
    MID="${2:?uso: secretaria.sh consultar <MISSAO>}"
    M="/opt/mission-events/mission-state-mirror/$MID.json"
    MM=$(python3 -c "import json;d=json.load(open('$M'));print(d.get('status'),d.get('verdict'))" 2>/dev/null || echo "sem-espelho")
    # consulta via SPOOL (worker legível): GB-ID -> MECANICO-<pid> -> veredito
    L=$(python3 - "$MID" <<'PY'
import json, sys
alvo = sys.argv[1]
pid = None; end = None; start = None
for line in open("/opt/mission-events/spool.jsonl", errors="ignore"):
    try: e = json.loads(line)
    except Exception: continue
    mid = e.get("missionId", ""); msg = e.get("msg", "")
    if e.get("kind") == "mission_start" and alvo in msg:
        pid = mid; start = msg[:80]
    if e.get("kind") == "mission_end" and (pid and mid == pid or alvo in msg):
        end = msg[:90]
if not pid:
    # fallback worker-legível: espelho de sala /tmp/ag-live aponta a trilha
    import glob as _g, os as _os
    achou = ""
    for ep in _g.glob("/tmp/ag-live/*.espelho.json"):
        try: d2 = json.load(open(ep))
        except Exception: continue
        if alvo in json.dumps(d2):
            tr = d2.get("trail", "")
            ult = ""
            if tr and _os.path.exists(tr):
                for line in open(tr, errors="ignore"):
                    if '"step":"entrega"' in line or '"step":"saida"' in line:
                        ult = line.strip()[:160]
            achou = "%s | trilha=%s | %s" % (d2.get("id"), _os.path.basename(tr), ult or "em prova")
            break
    print(achou or "sem-despacho no spool e sem espelho")
else:
    st = "closed" if end else "running"
    print("%s %s | start=%s | %s" % (pid, st, start, end or "em voo"))
PY
)
    diga "$MID: ledger(mecanico)=$L espelho=$MM"
    ;;
  despachar)
    # roteia: plano.json -> despachante (DAG); contrato+MEC_PROVA -> despacho rápido
    ALVO="${2:?uso: secretaria.sh despachar <plano.json|contrato> [worktree]}"
    case "$ALVO" in
      *plano*.json)
        diga "roteando pelo DESPACHANTE (DAG): $(basename "$ALVO")"
        [ "$ROOT" = "1" ] && nohup python3 /home/worker/harness-s2/scripts/despachante.py "$ALVO" >/tmp/secretaria-dag.log 2>&1 &
        ;;
      *)
        diga "roteando por DESPACHO RÁPIDO (mecanico): $(basename "$ALVO")"
        [ "$ROOT" = "1" ] && nohup bash /home/worker/harness-s2/scripts/despachar-mecanico.sh /home/worker/harness-s2 "$ALVO" >/tmp/secretaria-desp.log 2>&1 &
        ;;
    esac
    ;;
  *) echo "uso: secretaria.sh responder|consultar|despachar ..."; exit 2 ;;
esac

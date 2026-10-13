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
for p in glob.glob("/root/.hermes/mission-state/*.json"):
    try: d=json.load(open(p))
    except Exception: continue
    if not isinstance(d, dict): continue
    rows.append((d.get("missionId") or os.path.basename(p), d.get("status"), d.get("veredito"), d.get("custo_usd")))
rows=rows[-12:]
for r in reversed(rows): print("%s status=%s veredito=%s custo=%s" % r)
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
    L="/root/.hermes/mission-state/$MID.json"; M="/opt/mission-events/mission-state-mirror/$MID.json"
    S=$(python3 -c "import json;d=json.load(open('$L'));print(d.get('status'),d.get('veredito'),d.get('custo_usd'))" 2>/dev/null || echo "sem-ledger")
    MM=$(python3 -c "import json;d=json.load(open('$M'));print(d.get('status'),d.get('verdict'))" 2>/dev/null || echo "sem-espelho")
    diga "$MID: ledger=$S espelho=$MM"
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

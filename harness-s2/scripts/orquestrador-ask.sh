#!/bin/bash
# orquestrador-ask.sh — fachada de SOLICITACAO do orquestrador mecanico (ORQ-ASK-01)
# Sempre somente pede (fire-and-forget): nunca espera a execucao, nunca trava o chat.
# Roteamento 3-andares (v1): andar 1 = regex/casamento exato da acao; andar 2 (Jev,
# pedido em linguagem natural) e andar 3 (decisao/verificacao) = evolucao, ver GUIA.
#
# Uso: orquestrador-ask.sh "<pedido>"
#   secretaria "<consulta>"        -> scripts/secretaria.sh (background, responde 💬)
#   mecanico <repo> "<missao>" [VAR=v ...] -> scripts/despachar-mecanico.sh (background)
#   status <GB-ID> | fila          -> secretaria (consulta)
#   dag <plano.json>               -> scripts/despachante.py --executar (background)
#
# Env sobrescriveis para prova hermetica:
#   ORQ_LOG (default /tmp/orquestrador-ask.log)
#   ORQ_SECRETARIA_BIN (default <REPO>/scripts/secretaria.sh)
#   ORQ_DESPACHO_BIN   (default <REPO>/scripts/despachar-mecanico.sh)
#   ORQ_DESPACHANTE_BIN (default python3 <REPO>/scripts/despachante.py)
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${ORQ_LOG:-/tmp/orquestrador-ask.log}"
SECRETARIA_BIN="${ORQ_SECRETARIA_BIN:-$REPO/scripts/secretaria.sh}"
DESPACHO_BIN="${ORQ_DESPACHO_BIN:-$REPO/scripts/despachar-mecanico.sh}"
DESPACHANTE_BIN="${ORQ_DESPACHANTE_BIN:-python3 $REPO/scripts/despachante.py}"

PEDIDO="${1:-}"
if [ -z "$PEDIDO" ]; then
  echo '{"ok":false,"error":"PEDIDO_VAZIO"}'
  exit 1
fi

log(){ printf '{"ts":"%s","pid":"%s","pedido":"%s","acao":"%s"}\n' "$(date -Is)" "$$" "$PEDIDO" "$1" >> "$LOG"; }

# helper: dispara fire-and-forget e registra
ask(){
  local acao="$1"; shift
  nohup "$@" >/dev/null 2>&1 &
  log "$acao"
  echo "{\"ok\":true,\"acao\":\"$acao\",\"modo\":\"fire-and-forget\",\"pid\":$!}"
  return 0
}

ACAO="${PEDIDO%% *}"
RESTO="${PEDIDO#* }"
[ "$RESTO" = "$PEDIDO" ] && RESTO=""

case "$ACAO" in
  secretaria)
    [ -z "$RESTO" ] && { echo '{"ok":false,"error":"CONSULTA_VAZIA"}'; exit 1; }
    ask secretaria bash "$SECRETARIA_BIN" "$RESTO"
    ;;
  mecanico)
    REPO_ALVO="${RESTO%% *}"
    if [ -z "$REPO_ALVO" ] || [ "$REPO_ALVO" = "$RESTO" ]; then
      echo '{"ok":false,"error":"MECANICO_USO","uso":"mecanico <repo> \"<missao>\" [VAR=v ...]"}'
      exit 1
    fi
    ARG_RESTO="${RESTO#* }"
    ask mecanico bash "$DESPACHO_BIN" "$REPO_ALVO" "$ARG_RESTO"
    ;;
  status|fila)
    CONSULTA="$PEDIDO"
    [ "$ACAO" = "status" ] && [ -z "$RESTO" ] && { echo '{"ok":false,"error":"STATUS_USO","uso":"status <GB-ID>"}'; exit 1; }
    ask "$ACAO" bash "$SECRETARIA_BIN" "$CONSULTA"
    ;;
  dag)
    PLANO="$RESTO"
    [ -z "$PLANO" ] && { echo '{"ok":false,"error":"DAG_USO","uso":"dag <plano.json>"}'; exit 1; }
    ask dag bash -c "$DESPACHANTE_BIN --executar '$PLANO'"
    ;;
  *)
    log "desconhecida"
    echo "{\"ok\":false,\"error\":\"ACAO_DESCONHECIDA\",\"acao\":\"$ACAO\",\"andar2\":\"evolucao-jev\"}"
    exit 1
    ;;
esac
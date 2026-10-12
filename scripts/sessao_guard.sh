#!/usr/bin/env bash
# sessao_guard.sh — GB-SESSAO-GUARD-01: mata par TUI(node ui-tui/dist/entry.js)+gateway(python -m tui_gateway.entry) orfao
# que segura lock de sessao. Fail-open: duvida = pular par. Nunca matar por tempo de inicio sozinho.
# Env: GUARD_PS_CMD (default "ps aux"), GUARD_PSTREE_CMD (default "pstree -p"), GUARD_STALE_MIN (default 120),
#      GUARD_LOG (default stdout), GUARD_DRY_RUN=1, GUARD_ENV_DIR (prova: environ fake por pid),
#      GUARD_AGENT_LOG (log p/ frescor de "tui prompt accepted").
set -u
PS_CMD="${GUARD_PS_CMD:-ps aux}"
PSTREE_CMD="${GUARD_PSTREE_CMD:-pstree -p}"
STALE_MIN="${GUARD_STALE_MIN:-120}"
LOG="${GUARD_LOG:-}"
DRY="${GUARD_DRY_RUN:-0}"
ENV_DIR="${GUARD_ENV_DIR:-/proc}"

log() { if [ -n "$LOG" ]; then echo "$*" >>"$LOG"; else echo "$*"; fi; }

PS_OUT=$($PS_CMD 2>/dev/null) || { log "GUARD_FAIL_OPEN leitura_ps"; exit 0; }
TREE_OUT=$($PSTREE_CMD 2>/dev/null) || TREE_OUT=""

node_pids=$(echo "$PS_OUT" | awk '/ui-tui\/dist\/entry\.js/ && !/awk/ {print $2}')
gw_pids=$(echo "$PS_OUT" | awk '/tui_gateway\.entry/ && !/awk/ {print $2}')
[ -n "$node_pids" ] || [ -n "$gw_pids" ] || { log "GUARD_SEM_PARES"; exit 0; }

ppid_of() { echo "$PS_OUT" | awk -v p="$1" '$2==p {print $3; exit}'; }
state_of() { echo "$PS_OUT" | awk -v p="$1" '$2==p {print $4; exit}'; }
cmdline_of() { echo "$PS_OUT" | awk -v p="$1" '$2==p {$1=$2=$3=$4=$5=$6=""; sub(/^ +/,""); print; exit}'; }
alive() { echo "$PS_OUT" | awk -v p="$1" '$2==p {found=1} END{exit !found}'; }
env_of() {
  if [ -f "$ENV_DIR/$1/environ" ]; then tr '\0' '\n' <"$ENV_DIR/$1/environ" 2>/dev/null | awk -F= '/^HERMES_SESSION_ID=/{print $2}'
  else tr '\0' '\n' <"/proc/$1/environ" 2>/dev/null | awk -F= '/^HERMES_SESSION_ID=/{print $2}'; fi
}

tem_filho_chat() {
  local p="$1" kids kid cl
  [ -n "$p" ] || return 1
  kids=$(echo "$PS_OUT" | awk -v p="$1" '$3==p {print $2}')
  [ -n "$kids" ] || return 1
  for kid in $kids; do
    cl=$(cmdline_of "$kid")
    case "$cl" in *Hermes*snap*|*snap*Hermes*|*hermes-scratch*) return 0 ;; esac
  done
  return 1
}

sessao_par() { local s; s=$(env_of "$1"); [ -n "$s" ] && { echo "$s"; return; }; s=$(env_of "$2"); [ -n "$s" ] && { echo "$s"; return; }; echo ""; }

prompt_fresco() {
  local f="${GUARD_AGENT_LOG:-$HOME/.hermes/logs/agent.log}"
  [ -f "$f" ] || return 0
  local last; last=$(stat -c %Y "$f" 2>/dev/null) || return 0
  [ $(( $(date +%s) - last )) -lt $(( STALE_MIN * 60 )) ]
}

declare -A PAIR_PY=()
for np in $node_pids; do
  npp=$(ppid_of "$np"); best=""
  for gp in $gw_pids; do
    gpp=$(ppid_of "$gp")
    if [ "$gpp" = "$npp" ] || [ "$gpp" = "$np" ] || [ "$npp" = "$gp" ]; then best="$gp"; break; fi
  done
  PAIR_PY[$np]="$best"
done

for np in "${!PAIR_PY[@]}"; do
  gp="${PAIR_PY[$np]}"
  alive "$np" || { log "GUARD_SKIP node=$np sumiu (fail-open)"; continue; }
  [ -n "$gp" ] && alive "$gp" || gp=""

  if tem_filho_chat "$gp" || tem_filho_chat "$np"; then
    log "GUARD_PAR_VIVO node=$np gw=$gp causa=FILHO_CHAT_VIVO"
    continue
  fi

  sess=$(sessao_par "$gp" "$np")
  colide=0
  if [ -n "$sess" ]; then
    for other_np in "${!PAIR_PY[@]}"; do
      [ -n "$other_np" ] && [ "$other_np" != "$np" ] || continue
      osess=$(sessao_par "${PAIR_PY[$other_np]}" "$other_np")
      [ -n "$osess" ] && [ "$osess" = "$sess" ] && colide=1
    done
  fi
  stale=0
  prompt_fresco || stale=1

  if [ $colide -eq 1 ] || [ $stale -eq 1 ]; then
    causa=$([ $colide -eq 1 ] && echo LOCK_COLIDINDO || echo ORFAO_SEM_FILHOS)
    if [ "$DRY" = "1" ]; then
      log "GUARD_DRY_RUN mataria node=$np gw=$gp causa=$causa sess=$sess"
      continue
    fi
    log "GUARD_KILL node=$np gw=$gp causa=$causa sess=$sess"
    [ -n "$gp" ] && kill -TERM "$gp" 2>/dev/null
    kill -TERM "$np" 2>/dev/null
    sleep 5
    for pid in $gp $np; do
      [ -n "$pid" ] || continue
      if alive "$pid"; then
        st=$(state_of "$pid")
        if [ "$st" = "R" ]; then kill -9 "$pid" 2>/dev/null; log "GUARD_ESCALADO pid=$pid KILL9"; fi
      fi
    done
  else
    log "GUARD_PAR_OK node=$np gw=$gp"
  fi
done
exit 0
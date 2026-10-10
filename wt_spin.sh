#!/usr/bin/env bash
# wt_spin.sh — spin-up de worktree de missão (0 LLM).
# Uso: wt_spin.sh <ID> [base] [--no-probe]
# Cria branch rd-<slug-do-ID> e worktree /home/worker/wt-<ID> a partir de base
# (default rd-segue-01) no repo /home/worker/harness-s2 (env WT_SPIN_REPO).
# WT_SPIN_WT_ROOT muda a raiz do worktree (default /home/worker).
# Nunca destrói branch/worktree existente; se já existe, emite NAO_CRIADO tipado.
# JSON 1 linha; exit 0 sempre; falha tipada {ok:false,error:...}.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh" 2>/dev/null || {
  TB_LIB_PATH="${TB_LIB_PATH:-/opt/mission-events/tools-bash}"
  source "$TB_LIB_PATH/_lib.sh"
}
start=$(date +%s%N)
TOOL=wt_spin

REPO="${WT_SPIN_REPO:-/home/worker/harness-s2}"
WT_ROOT="${WT_SPIN_WT_ROOT:-/home/worker}"
BASE_DEFAULT="rd-segue-01"

# ---- parse de args ----
ID=""
BASE="$BASE_DEFAULT"
PROBE=1
for a in "$@"; do
  case "$a" in
    --no-probe) PROBE=0 ;;
    -*) tb_fail "$TOOL" BAD_ARGS "$start" "$@" ;;
    *) if [ -z "$ID" ]; then ID="$a"; elif [ "$BASE" = "$BASE_DEFAULT" ]; then
         BASE="$a"; else tb_fail "$TOOL" BAD_ARGS "$start" "$@"; fi ;;
  esac
done
[ -n "$ID" ] || tb_fail "$TOOL" BAD_ARGS "$start" "$@"

SLUG="$(printf '%s' "$ID" | tr '[:upper:]' '[:lower:]')"
BRANCH="rd-$SLUG"
WT="$WT_ROOT/wt-$ID"

# ---- repo válido? ----
git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || tb_fail "$TOOL" REPO_INEXISTENTE "$start" "$@"

# ---- já existe? nunca destrói ----
if git -C "$REPO" show-ref --verify --quiet "refs/heads/$BRANCH" \
   || git -C "$REPO" show-ref --verify --quiet "refs/remotes/origin/$BRANCH" \
   || git -C "$REPO" worktree list --porcelain | grep -q "^worktree $WT\$"; then
  tb_audit "$TOOL" "$(tb_join "$@")" 0 "NAO_CRIADO" "$start" || :
  printf '{"ok":false,"tool":"%s","error":"NAO_CRIADO","id":"%s","worktree":"%s","branch":"%s","dica":"branch rd-%s ou worktree %s ja existe; nada foi alterado"}\n' \
    "$TOOL" "$ID" "$WT" "$BRANCH" "$SLUG" "$WT"
  exit 0
fi

# ---- base existe? ----
git -C "$REPO" show-ref --verify --quiet "refs/heads/$BASE" \
  || git -C "$REPO" show-ref --verify --quiet "refs/remotes/origin/$BASE" \
  || tb_fail "$TOOL" BASE_INEXISTENTE "$start" "$@"

# ---- criação ----
if ! git -C "$REPO" worktree add -b "$BRANCH" "$WT" "$BASE" >/dev/null 2>&1; then
  tb_fail "$TOOL" WORKTREE_ADD_FALHOU "$start" "$@"
fi

# ---- permissões: chown para worker ----
if [ "$(id -u)" = "0" ] && id worker >/dev/null 2>&1; then
  chown -R worker:worker "$WT" || { tb_fail "$TOOL" CHOWN_FALHOU "$start" "$@"; }
fi

# ---- prova de commit como worker (única exceção de reset) ----
PROBE_STATUS="pulada"
if [ "$PROBE" = "1" ]; then
  if [ "$(id -u)" = "0" ] && id worker >/dev/null 2>&1; then
    if sudo -u worker git -C "$WT" commit -q --allow-empty -m "wt-spin-probe $ID" \
       && sudo -u worker git -C "$WT" reset -q --hard HEAD~1; then
      PROBE_STATUS="ok"
    else
      tb_fail "$TOOL" PROBE_FALHOU "$start" "$@"
    fi
  else
    # sem root/sudo: prova direta (usuário corrente)
    if git -C "$WT" commit -q --allow-empty -m "wt-spin-probe $ID" \
       && git -C "$WT" reset -q --hard HEAD~1; then
      PROBE_STATUS="ok"
    else
      tb_fail "$TOOL" PROBE_FALHOU "$start" "$@"
    fi
  fi
fi

ms=$(( ( $(date +%s%N) - start ) / 1000000 ))
OUT=$(printf '{"ok":true,"tool":"%s","id":"%s","worktree":"%s","branch":"%s","base":"%s","probe":"%s","ms":%d}' \
  "$TOOL" "$ID" "$WT" "$BRANCH" "$BASE" "$PROBE_STATUS" "$ms")
tb_emit "$TOOL" "$OUT" "$start" "$@"
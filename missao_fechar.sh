#!/usr/bin/env bash
# missao_fechar.sh — fecho de missão do supervisor em 1 comando (0 LLM).
# Uso: missao_fechar.sh <ID|runs_dir> [--apply]
# DRY-RUN por padrão: só imprime o plano (JSON 1 linha, exit 0 sempre).
# --apply: merge --no-ff na base rd-segue-01 + suíte + fechar abas RUN:<ID>#.
# Falhas tipadas com dica: RUN_DIR_NAO_ENCONTRADO, NAO_PASS, CONFLITO,
# SUITE_VERMELHA (rollback:"feito"), MERGE_FALHOU, BAD_ARGS.
set -u
TOOL="missao_fechar"
start=$(date +%s%N)
# lib opcional (instalada em /opt pelo supervisor); fallback local
TB_LIB="$(dirname "${BASH_SOURCE[0]}")/../tools-bash/_lib.sh"
if [ -f /opt/mission-events/tools-bash/_lib.sh ]; then
  source /opt/mission-events/tools-bash/_lib.sh
elif [ -f "$TB_LIB" ]; then
  source "$TB_LIB"
fi
if ! command -v tb_audit >/dev/null 2>&1; then
  tb_join(){ local IFS=$'\x1f'; printf '%s' "$*"; }
  tb_audit(){ return 0; }
  tb_emit(){ local t="$1" o="$2" s="$3"; shift 3
    tb_audit "$t" "$(tb_join "$@")" 1 "null" "$s" || :
    printf '%s\n' "$o"; exit 0; }
fi

fail(){ local e="$1" dica="${2:-}"; dica="$(printf '%s' "$dica" | tr '
	' '   ')"; dica="$(printf '%s' "$dica" | tr '\n\r\t' '   ')"; local d=""
  [ -n "$dica" ] && d=",\"dica\":\"$dica\""
  tb_audit "$TOOL" "$(tb_join "$@")" 0 "$e" "$start" || :
  printf '{"ok":false,"tool":"%s","error":"%s"%s}\n' "$TOOL" "$e" "$d"
  exit 0; }
emit(){ tb_emit "$TOOL" "$1" "$start" "$@"; }
step(){ tb_audit "$TOOL" "$(tb_join "$@")" 1 null "$start" || :; }

ID="${1:-}"; APPLY=0
[ -n "$ID" ] || fail BAD_ARGS "uso: missao_fechar.sh <ID|runs_dir> [--apply]"
[ "${2:-}" = "--apply" ] && APPLY=1

# ---- 1. resolver runs dir: caminho direto OU ID via ledger/glob ----
RUNS_DIR=""
case "$ID" in
  */*) [ -d "$ID" ] && RUNS_DIR="$ID" ;;
  *)
    sd="$(tb_state_dir 2>/dev/null || printf '/opt/mission-events/mission-state-mirror')"
    led="$sd/$ID.json"
    if [ -f "$led" ]; then
      RUNS_DIR="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1])); c=d.get("cwd")
    print(c if isinstance(c,str) else "")
except Exception: print("")
' "$led" 2>/dev/null)"
    fi
    if [ -z "$RUNS_DIR" ]; then
      for d in /home/worker/wt-*/runs/"$ID"; do
        [ -d "$d" ] && { RUNS_DIR="$d"; break; }
      done
    fi
    ;;
esac
[ -n "$RUNS_DIR" ] && [ -d "$RUNS_DIR" ] || fail RUN_DIR_NAO_ENCONTRADO "procure o runs dir do ID no mission-state-mirror (ledger <ID>.json campo cwd) ou /home/worker/wt-*/runs/<ID>"
# normaliza tentativa interna: sobe até ancestral com resumo/autoretry
if [ ! -f "$RUNS_DIR/resumo.json" ] && [ ! -f "$RUNS_DIR/autoretry-summary.json" ]; then
  p="$RUNS_DIR"
  while :; do
    case "$p" in
      */tentativa-*/run-*|*/tentativa-*)
        p="$(dirname "$p")"
        if [ -f "$p/resumo.json" ] || [ -f "$p/autoretry-summary.json" ]; then RUNS_DIR="$p"; break; fi
        ;;
      *) break ;;
    esac
  done
fi
WT="$(dirname "$RUNS_DIR")"
BRANCH="$(git -C "$WT" branch --show-current 2>/dev/null)"
[ -n "$BRANCH" ] || fail BRANCH_NAO_RESOLVIDA "git -C $WT branch --show-current vazio; runs dir fora de um worktree?"
step resolve "$ID" "$RUNS_DIR" "$BRANCH"

# ---- veredito do resumo/autoretry deve ser PASS ----
VERDICT=""
for f in "$RUNS_DIR/resumo.json" "$RUNS_DIR/autoretry-summary.json"; do
  if [ -f "$f" ]; then
    VERDICT="$(python3 -c '
import json,sys
try: d=json.load(open(sys.argv[1])); print(d.get("veredito") or d.get("verdict") or "")
except Exception: print("")
' "$f" 2>/dev/null)"
    [ -n "$VERDICT" ] && break
  fi
done
[ "$VERDICT" = "PASS" ] || fail NAO_PASS "veredito=${VERDICT:-ausente} em $RUNS_DIR/resumo.json|autoretry-summary.json; fecho exige PASS"
step verdict "$ID" "$VERDICT"

BASE="rd-segue-01"
NCOMMITS="$(git -C "$WT" rev-list --count "$BASE..$BRANCH" 2>/dev/null || printf '?')"

# ---- 2. DRY-RUN: nada executa ----
if [ "$APPLY" != "1" ]; then
  emit "{\"ok\":true,\"tool\":\"$TOOL\",\"id\":\"$ID\",\"branch\":\"$BRANCH\",\"base\":\"$BASE\",\"arquivos\":$NCOMMITS,\"acao\":\"merge+suite+close_tab\",\"modo\":\"dry-run\"}"
fi

# ---- 3. --apply ----
COMMON="$(git -C "$WT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || git -C "$WT" rev-parse --git-common-dir)"
BASE_REPO="$(dirname "$COMMON")"
[ -d "$BASE_REPO/.git" ] || BASE_REPO="$COMMON"
step merge_start "$BRANCH" "$BASE_REPO"

MERGE_OUT="$(git -C "$BASE_REPO" -c user.name="${GIT_IDENT_NAME:-fecho}" -c user.email="${GIT_IDENT_EMAIL:-fecho@local}" merge --no-ff "$BRANCH" 2>&1)" || {
  case "$MERGE_OUT" in
    *CONFLICT*|*conflict*)
      git -C "$BASE_REPO" merge --abort >/dev/null 2>&1
      step merge_abort "$BRANCH"
      fail CONFLITO "merge --no-ff $BRANCH conflitou; merge --abort executado, estado intacto"
      ;;
    *)
      git -C "$BASE_REPO" merge --abort >/dev/null 2>&1
      fail MERGE_FALHOU "$MERGE_OUT"
      ;;
  esac
}
MERGED_AS="$(git -C "$BASE_REPO" rev-parse --short HEAD)"
BACKUP="$(git -C "$BASE_REPO" rev-parse ORIG_HEAD)"
step merge_ok "$BRANCH" "$MERGED_AS"

# ---- suíte (TEST_SUITE_CMD sobrepõe pytest p/ testes herméticos) ----
SUITE_CMD="${TEST_SUITE_CMD:-/usr/bin/python3 -m pytest tests/ -q}"
if ( cd "$BASE_REPO" && eval "$SUITE_CMD" >/dev/null 2>&1 ); then
  step suite_ok "$SUITE_CMD"
else
  git -C "$BASE_REPO" reset --hard ORIG_HEAD >/dev/null 2>&1
  step suite_rollback "$BACKUP"
  tb_audit "$TOOL" "$(tb_join "$ID" --apply)" 0 SUITE_VERMELHA "$start" || :
  printf '{"ok":false,"tool":"%s","error":"SUITE_VERMELHA","dica":"suite falhou em %s; git reset --hard ORIG_HEAD executado","rollback":"feito","backup_ref":"%s"}\n' "$TOOL" "$BASE_REPO" "$BACKUP"
  exit 0
fi

# ---- fechar abas RUN:<ID># ----
TABS_RAW="$(herdr tab list 2>/dev/null)"
if [ -n "$TABS_RAW" ] && printf '%s' "$TABS_RAW" | python3 -c 'import sys,json;json.load(sys.stdin)["result"]["tabs"]' >/dev/null 2>&1; then
  TAB_CLOSED="$(ID="$ID" TABS_RAW="$TABS_RAW" HERDR="${HERDR_BIN:-herdr}" python3 -c '
import os, json, subprocess
tabs = json.loads(os.environ["TABS_RAW"])["result"]["tabs"]
needle = "RUN:%s#" % os.environ["ID"]
fechadas = []
for t in tabs:
    lbl = t.get("label") or ""
    if lbl.startswith(needle):
        r = subprocess.run([os.environ["HERDR"],"tab","close",t.get("tab_id","")], capture_output=True)
        if r.returncode == 0:
            fechadas.append(lbl)
print(json.dumps(fechadas, separators=(",",":")))
')"
  step tabs_closed "$ID" "$TAB_CLOSED"
else
  TAB_CLOSED="inacessivel_fora_operador"
  step tabs_inacessivel "$ID"
fi

emit "{\"ok\":true,\"tool\":\"$TOOL\",\"id\":\"$ID\",\"merged_as\":\"$MERGED_AS\",\"suite\":\"verde\",\"tab_closed\":$TAB_CLOSED,\"backup_ref\":\"$BACKUP\",\"modo\":\"apply\"}"

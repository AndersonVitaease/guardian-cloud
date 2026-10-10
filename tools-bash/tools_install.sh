#!/usr/bin/env bash
# tools_install.sh — instalacao governada de tools bash (RD-INSTALL-MANIFEST-01 / TOOLS-INSTALL-01)
# Uso: tools_install.sh ORIGEM [--apply] [--com-agent-bash]
# Padrao: dry-run. --apply: backup -> copia atomica -> MANIFEST -> verify -> E2E -> rollback se falhar.
# Saida: 1 linha JSON. Destino/backups sobrescriveis por TOOLS_INSTALL_DEST / TOOLS_INSTALL_BACKUP_DIR.
set -u

ORIGEM=""
APPLY=0
COM_AGENT=0
for _a in "$@"; do
  case "$_a" in
    --apply) APPLY=1 ;;
    --com-agent-bash) COM_AGENT=1 ;;
    --*) ;;
    *) if [ -z "$ORIGEM" ]; then ORIGEM="$_a"; fi ;;
  esac
done

DEST="${TOOLS_INSTALL_DEST:-/opt/mission-events/tools-bash}"
TS="$(date +%Y%m%d-%H%M)"
BK="${TOOLS_INSTALL_BACKUP_DIR:-${DEST}.bak-${TS}}"

T0=$(date +%s%N)
emit() { # emit ok erro etapa dry_run backup instalados identicos manifest_ok verify_ok rollback tools_json
  local _ms=$(( ($(date +%s%N) - T0) / 1000000 ))
  TOOLS_I_EMITTED_OK="$1" TOOLS_I_ERRO="$2" TOOLS_I_ETAPA="$3" TOOLS_I_DRY="$4" \
  TOOLS_I_BK="$5" TOOLS_I_INST="$6" TOOLS_I_IDENT="$7" TOOLS_I_MOK="$8" TOOLS_I_VOK="$9" \
  TOOLS_I_RB="${10}" TOOLS_I_TJ="${11}" TOOLS_I_MS="$_ms" python3 - <<'PY'
import json, os
def lst(v):
    return [x for x in (v or "").split("\n") if x]
out = {
    "ok": os.environ["TOOLS_I_EMITTED_OK"] == "1",
    "tool": "tools_install",
    "dry_run": os.environ["TOOLS_I_DRY"] == "1",
    "backup": os.environ["TOOLS_I_BK"] or None,
    "instalados": lst(os.environ.get("TOOLS_I_INST", "")),
    "identicos": lst(os.environ.get("TOOLS_I_IDENT", "")),
    "manifest_ok": os.environ["TOOLS_I_MOK"] == "1",
    "verify_ok": os.environ["TOOLS_I_VOK"] == "1",
    "rollback": os.environ["TOOLS_I_RB"] == "1",
    "ms": int(os.environ["TOOLS_I_MS"]),
}
if os.environ.get("TOOLS_I_ERRO"):
    out["error"] = os.environ["TOOLS_I_ERRO"]
    out["etapa"] = os.environ["TOOLS_I_ETAPA"]
tj = os.environ.get("TOOLS_I_TJ", "")
if tj:
    out["tools_json"] = lst(tj)
print(json.dumps(out, separators=(",", ":")))
PY
  exit 0
}

fail() { emit 0 "$1" "$2" "$APPLY" "" "" "" 0 0 0 ""; }

if [ -z "$ORIGEM" ]; then fail USO "origem"; fi
if [ ! -d "$ORIGEM" ]; then fail ORIGEM_INEXISTENTE "origem"; fi

# ---- varredura da origem: nomes validos, shebang, hashes ----
NOME_RE='^[a-z0-9_.-]+$'
declare -A H_ORIG=()
FILES=""
for f in "$ORIGEM"/*; do
  [ -f "$f" ] || continue
  b=$(basename "$f")
  case "$b" in *.sh) ;; *) continue ;; esac
  if ! printf '%s' "$b" | grep -Eq "$NOME_RE"; then fail NOME_INVALIDO "varredura"; fi
  if ! head -n 1 "$f" | grep -q '^#!'; then fail SEM_SHEBANG "varredura"; fi
  FILES="$FILES $b"
  H_ORIG[$b]=$(sha256sum "$f" | cut -d' ' -f1)
done
[ -n "$FILES" ] || fail ORIGEM_VAZIA "varredura"
if [ -f "$ORIGEM/tools.json" ]; then
  H_ORIG[tools.json]=$(sha256sum "$ORIGEM/tools.json" | cut -d' ' -f1)
fi

# ---- classificacao vs destino ----
NOVOS=""; ALTERADOS=""; IDENTICOS=""
for b in $FILES; do
  if [ "$b" = "agent_bash.sh" ] && [ "$COM_AGENT" != "1" ]; then continue; fi
  h_dest=""
  [ -f "$DEST/$b" ] && h_dest=$(sha256sum "$DEST/$b" | cut -d' ' -f1)
  if [ -z "$h_dest" ]; then NOVOS="${NOVOS}${b}"$'\n'
  elif [ "$h_dest" = "${H_ORIG[$b]}" ]; then IDENTICOS="${IDENTICOS}${b}"$'\n'
  else ALTERADOS="${ALTERADOS}${b}"$'\n'; fi
done
TJ_MUDAM=""
if [ -f "$ORIGEM/tools.json" ]; then
  TJ_MUDAM=$(TOOLS_I_O="$ORIGEM/tools.json" TOOLS_I_D="$DEST/tools.json" python3 - <<'PY'
import json, os, sys
try:
    o = json.load(open(os.environ["TOOLS_I_O"]))
except Exception:
    print("tools_json_invalido"); sys.exit(0)
try:
    d = json.load(open(os.environ["TOOLS_I_D"]))
except Exception:
    d = {}
chg = []
if isinstance(o, dict):
    for k, v in o.items():
        if d.get(k) != v:
            chg.append(k)
elif o != d:
    chg.append("(raiz)")
print("\n".join(chg))
PY
)
fi

if [ "$APPLY" != "1" ]; then
  emit 1 "" "" 1 "" "$NOVOS$ALTERADOS" "$IDENTICOS" 0 0 0 "$TJ_MUDAM"
fi

# ---- APPLY ----
# (1) backup — snapshot exato do destino (BK unico por timestamp; slot de teste e resetado)
rm -rf "$BK"
cp -a "$DEST" "$BK" || fail BACKUP_FALHOU "backup"

rollback() { # rollback <etapa> <erro> — restaura snapshot exato (remove o que a instalacao adicionou)
  if [ -d "$BK" ] && [ -n "$(ls -A "$BK" 2>/dev/null)" ] && rm -rf "$DEST" && cp -a "$BK" "$DEST" 2>/dev/null; then
    emit 0 "$2" "$1" 0 "$BK" "" "" 0 0 1 ""
  else
    emit 0 "$2" "$1" 0 "$BK" "" "" 0 0 2 ""
  fi
}

# (2) copia atomica .new -> mv; root:root 755 (tools.json 644); agent_bash.sh so com --com-agent-bash
INST=""
for b in $NOVOS $ALTERADOS; do
  b=$(printf '%s' "$b" | sed '/^$/d')
  [ -n "$b" ] || continue
  if [ "$b" = "agent_bash.sh" ] && [ "$COM_AGENT" != "1" ]; then continue; fi
  cp "$ORIGEM/$b" "$DEST/$b.new" || rollback "instalacao" "COPIA_FALHOU"
  chown root:root "$DEST/$b.new" 2>/dev/null || true
  if [ "$b" = "tools.json" ]; then chmod 644 "$DEST/$b.new"; else chmod 755 "$DEST/$b.new"; fi
  mv -f "$DEST/$b.new" "$DEST/$b" || rollback "instalacao" "MV_FALHOU"
  INST="${INST}${b}"$'\n'
done
if [ -f "$ORIGEM/tools.json" ]; then
  h_dest=""
  [ -f "$DEST/tools.json" ] && h_dest=$(sha256sum "$DEST/tools.json" | cut -d' ' -f1)
  if [ "$h_dest" != "${H_ORIG[tools.json]}" ]; then
    cp "$ORIGEM/tools.json" "$DEST/tools.json.new" || rollback "instalacao" "COPIA_FALHOU"
    chown root:root "$DEST/tools.json.new" 2>/dev/null || true
    chmod 644 "$DEST/tools.json.new"
    mv -f "$DEST/tools.json.new" "$DEST/tools.json" || rollback "instalacao" "MV_FALHOU"
    INST="${INST}tools.json"$'\n'
  fi
fi

# (3) MANIFEST.sha256 regenerado: 'sha256  nome' para todo .sh exceto verify_tools.sh/_lib.sh, mais tools.json.
#     Nunca apaga o manifest antes de ter o novo: escreve MANIFEST.new e mv.
: > "$DEST/MANIFEST.new" || rollback "manifest" "MANIFEST_FALHOU"
for f in "$DEST"/*; do
  [ -f "$f" ] || continue
  b=$(basename "$f")
  case "$b" in *.sh) ;; tools.json) ;; *) continue ;; esac
  case "$b" in verify_tools.sh|_lib.sh) continue ;; esac
  h=$(sha256sum "$f" | cut -d' ' -f1)
  printf '%s  %s\n' "$h" "$b" >> "$DEST/MANIFEST.new" || rollback "manifest" "MANIFEST_FALHOU"
done
mv -f "$DEST/MANIFEST.new" "$DEST/MANIFEST.sha256" || rollback "manifest" "MANIFEST_FALHOU"

# (4) verify_tools.sh exige ok:true
VOUT=$(cd "$DEST" && bash verify_tools.sh 2>&1) || true
if ! printf '%s' "$VOUT" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
  rollback "verify" "VERIFY_FALHOU"
fi

# (5) E2E rapido: flights.sh e runs_historico.sh exigem JSON ok:true
for e in flights.sh runs_historico.sh; do
  EOUT=$(cd "$DEST" && bash "$e" 2>&1) || true
  if ! printf '%s' "$EOUT" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    rollback "e2e:$e" "E2E_FALHOU"
  fi
done

# (6) sucesso
MOK=1; [ -f "$DEST/MANIFEST.sha256" ] || MOK=0
emit 1 "" "" 0 "$BK" "$INST" "$IDENTICOS" "$MOK" 1 0 "$TJ_MUDAM"

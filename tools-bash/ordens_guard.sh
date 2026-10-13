#!/usr/bin/env bash
# GB-JAULA-01 — guard allowlist v2: stdin JSON {tool_name, tool_input}; stdout JSON de decisão.
# Silêncio (exit 0 sem stdout) = allow. Kill switch: ORDENS_POLICY=operator.
set -u
if [ "${ORDENS_POLICY:-}" = "operator" ]; then
  echo '{"action":"allow","notice":"policy operator — guard desligado pelo operador"}'
  exit 0
fi

PAYLOAD="$(cat)"
TOOL="$(printf '%s' "$PAYLOAD" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_name",""))')"
INPUT="$(printf '%s' "$PAYLOAD" | python3 -c 'import sys,json;print(json.dumps(json.load(sys.stdin).get("tool_input",{})))')"
CMD="$(printf '%s' "$INPUT" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("command") or d.get("code") or d.get("task") or "")')"
DIR="$(cd "$(dirname "$0")" && pwd)"

# BUG B (GB-CANAL-UNICO-01): definições no TOPO — o bloco (g) usa block() ANTES
# da definição antiga (bash: função indefinida = "command not found" = ALLOW).
block() { echo "{\"action\":\"block\",\"message\":\"$1\",\"rule_key\":\"$2\"}"; exit 0; }
approve() { echo "{\"action\":\"approve\",\"message\":\"$1\",\"rule_key\":\"$2\"}"; exit 0; }

# (g) Ordens dinâmicas do Guardian: fetch com cache 60s; regex dinâmico casa → block
if [ "$TOOL" = "terminal" ] || [ "$TOOL" = "execute_code" ]; then
  DYN="$(ORDENS_URL="${ORDENS_URL:-http://127.0.0.1:8140/api/ordens}" ORDENS_TOKEN_FILE="${ORDENS_TOKEN_FILE:-$DIR/ordens-token}" \
        ORDENS_CACHE_FILE="${ORDENS_CACHE_FILE:-$DIR/ordens-cache.json}" \
        python3 "$DIR/ordens_dynamic.py" "$CMD" 2>/dev/null || true)"
  if [ -n "$DYN" ]; then
    block "ordem dinâmica do Guardian: $DYN" "ordens:dinamica"
  fi
fi

# defs de block()/approve() movidas para o topo (BUG B GB-CANAL-UNICO-01)

# (e) Delegação
case "$TOOL" in
  delegate_task) block "toda delegação = pipeline mission-ops (ORD-010)" "ordens:delegacao" ;;
  skill_manage|memory)
    printf '%s' "$INPUT" | grep -q '"action"[[:space:]]*:[[:space:]]*"delete"' && \
      approve "delete estrutural exige aprovação do operador" "ordens:estrutura" ;;
esac

# (c) execute_code vigiado — só parse de dados
if [ "$TOOL" = "execute_code" ]; then
  if printf '%s' "$CMD" | grep -Eq 'terminal\(|subprocess|os\.system|shell_quote|sh_run|shell_run|pty'; then
    block "execute_code = só parse de dados (ORD-3)" "ordens:execute_code"
  fi
  exit 0
fi

# (g) Ordens dinâmicas do Guardian (fetch com cache 60s; falha → cache; sem cache → nada)
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${ORDENS_URL:-}" ]; then
  DYN_ID="$(timeout 8 python3 "$DIR/ordens_dynamic.py" "$CMD" 2>/dev/null || true)"
  if [ -n "$DYN_ID" ]; then
    block "comando casa ordem dinâmica do Guardian ($DYN_ID)" "ordens:dinamica"
  fi
fi

# (b/f) TERMINAL = SÓ DESPACHO (allowlist) + regras duras v1
if [ "$TOOL" = "terminal" ]; then
  # leitura fora das tools governadas
  printf '%s' "$CMD" | grep -Eq '(^|[;&| ])(grep -r|cat /root|cat /opt|find /opt|find /root|ls -la /root|ls -la /opt)' && \
    block "leitura fora das tools governadas" "ordens:leitura"
  # git destrutivo
  printf '%s' "$CMD" | grep -Eq 'git (push --force|reset --hard|clean -fd|rebase)' && \
    block "git destrutivo bloqueado" "ordens:git"
  # rm -rf wt-
  printf '%s' "$CMD" | grep -Eq 'rm -rf .*wt-' && block "rm -rf de worktree bloqueado" "ordens:rm"
  # systemctl vital
  printf '%s' "$CMD" | grep -Eq 'systemctl (stop|kill|restart)' && block "systemctl de serviço vital bloqueado" "ordens:systemctl"
  # (d) guard imutável — escrita em caminho protegido
  PROTECTED="${ORDENS_PROTECTED:-}"
  if [ -n "$PROTECTED" ]; then
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      if printf '%s' "$CMD" | grep -Fq "$p"; then
        if printf '%s' "$CMD" | grep -Eq '(>|>>|tee|sed -i|cp |patch|write_file|rm |mv )'; then
          approve "editar o carcere exige aprovação do operador" "ordens:estrutura"
        fi
      fi
    done <<< "$PROTECTED"
  fi
  # ALLOWLIST de despacho
  if printf '%s' "$CMD" | grep -Eq '(^|[;&| ])(timeout [0-9]+ )?(bash /opt/mission-events/tools-bash/[a-z_]+\.sh|timeout [0-9]+ bash /opt/mission-events/tools-bash/[a-z_]+\.sh|python3 .*despachar_missao\.py|bash /opt/mission-events/tools-bash/missao_fechar\.sh|bash /opt/mission-events/tools-bash/ship_gapp\.sh|herdr (tab|run)|code_find\.sh|code_slice\.sh|mission_cost\.sh|trail_tail\.sh|flights\.sh|queue_peek\.sh|queue_eye\.sh|runs_status\.sh|runs_historico\.sh|git_peek\.sh|docker_peek\.sh|proc_peek\.sh|ciclo_status\.sh|file_peek\.sh|run_stream\.sh|run_close\.sh|verify_tools\.sh)'; then
    exit 0  # silêncio = allow
  fi
  block "terminal = só despacho (ORD-2): comando fora da allowlist" "ordens:terminal"
fi

exit 0
#!/usr/bin/env bash
# release_pipeline.sh — wrapper argv-safe do canal oficial do release runner
# (eng-mcp-release-runner.service) via Unix socket.
# Uso: release_pipeline.sh <operation> [deployJobId]
#   operation (allowlist): status | test | pipeline
#     pipeline exige deployJobId (argv 2, UUID).
# Socket: env RELEASE_RUNNER_SOCKET, default
#   /opt/eng-mcp-release-data/run/release-runner.sock (nome confirmado pelo
#   supervisor 11/10 20:50 BRT). O worker so le o valor da env, nunca o dir.
# Chamada: curl --unix-socket <SOCKET> -X POST /v1/release -d <json>
#   timeout curto (RELEASE_PIPELINE_TIMEOUT, default 10s) via curl -m.
# Saida: JSON 1 linha {ok,tool,operation,deployJobId?,http,body?,error?}.
# Motivos tipados: BAD_ARGS | BAD_OPERATION | BAD_DEPLOY_JOB_ID | SOCKET_MISSING
#   | SOCKET_UNREACHABLE | TIMEOUT | HTTP_<code> | BAD_RESPONSE.
# Exit 0 sempre (padrao das tools bash).
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
TOOL=release_pipeline

op="${1:-}"
job="${2:-}"

case "$op" in
  status|test|pipeline) :;;
  ""|*) tb_fail "$TOOL" "BAD_OPERATION${op:+:$op}" "$start" "$op" "$job";;
esac

if [ "$op" = "pipeline" ]; then
  # dois modos: pipeline <commitSha40> (novo deploy; envia acknowledgeRelease)
  #            pipeline <deployJobId> (retomada de job enfileirado)
  if printf '%s' "${1:-}" | grep -qE '^[0-9a-f]{40}$'; then
    job="$1"; MODE=commit
  elif printf '%s' "${1:-}" | grep -qE '^[0-9a-fA-F-]{8,64}$'; then
    job="$1"; MODE=resume
  else
    tb_fail "$TOOL" "BAD_DEPLOY_JOB_ID" "$start" "$op" "${1:-}"
  fi
fi

SOCKET="${RELEASE_RUNNER_SOCKET:-/opt/eng-mcp-release-data/run/release-runner.sock}"
if [ ! -S "$SOCKET" ]; then
  tb_fail "$TOOL" "SOCKET_MISSING" "$start" "$op" "$job"
fi

TMO="${RELEASE_PIPELINE_TIMEOUT:-10}"
case "$op" in
  status)   payload='{"operation":"status"}';;
  test)     payload='{"operation":"test"}';;
  pipeline) if [ "${MODE:-resume}" = "commit" ]; then
              payload="{\\\"operation\\\":\\\"pipeline\\\",\\\"commitSha\\\":\\\"$job\\\",\\\"acknowledgeRelease\\\":true}"
            else
              payload="{\\\"operation\\\":\\\"pipeline\\\",\\\"deployJobId\\\":\\\"$job\\\"}"
            fi;;
esac

body=$(curl -sS -m "$TMO" --unix-socket "$SOCKET" \
  -X POST http://localhost/v1/release -d "$payload" 2>&1)
rc=$?

case "$rc" in
  0) :;;
  7) tb_fail "$TOOL" "SOCKET_UNREACHABLE" "$start" "$op" "$job";;
  28) tb_fail "$TOOL" "TIMEOUT" "$start" "$op" "$job";;
  *) tb_fail "$TOOL" "CURL_ERR_$rc" "$start" "$op" "$job";;
esac

# valida JSON 1 linha da resposta
if ! printf '%s' "$body" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' 2>/dev/null; then
  tb_fail "$TOOL" "BAD_RESPONSE" "$start" "$op" "$job"
fi

if [ "$op" = "pipeline" ]; then
  out=$(printf '{"ok":true,"tool":"%s","operation":"%s","deployJobId":"%s","body":%s}' \
    "$TOOL" "$op" "$job" "$body")
else
  out=$(printf '{"ok":true,"tool":"%s","operation":"%s","body":%s}' "$TOOL" "$op" "$body")
fi
tb_emit "$TOOL" "$out" "$start" "$op" "$job"
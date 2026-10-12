#!/usr/bin/env bash
# release_pipeline.sh — wrapper de release (status/test/job/pipeline)
set -uo pipefail

CURL_BIN="${CURL_BIN:-curl}"
BASE_URL="${BASE_URL:-http://localhost:8080}"

usage() {
  echo "uso: release_pipeline.sh {status|test|job <id>|pipeline <commitSha40>}"
  exit 2
}

# http_post <url> <payload> -> imprime "STATUS<tab>CORPO"
http_post() {
  local url="$1" payload="$2" out code
  out="$("$CURL_BIN" -sS -X POST -H 'Content-Type: application/json' \
    -d "$payload" -w '\n%{http_code}' "$url")" || {
    echo "STEP_TRANSPORTE_FALHOU: $out" >&2
    return 99
  }
  code="$(printf '%s' "$out" | tail -n1)"
  local body
  body="$(printf '%s' "$out" | sed '$d')"
  printf '%s\t%s\n' "$code" "$body"
}

cmd="${1:-}"
case "$cmd" in
  status)
    exec "$CURL_BIN" -sS "$BASE_URL/status"
    ;;
  test)
    exec "$CURL_BIN" -sS "$BASE_URL/test"
    ;;
  job)
    [ $# -ge 2 ] || usage
    exec "$CURL_BIN" -sS "$BASE_URL/jobs/$2"
    ;;
  pipeline)
    [ $# -ge 2 ] || usage
    sha="$2"
    if ! [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then
      echo "INPUT_INVALID: commitSha40 esperado, recebi: $sha" >&2
      exit 2
    fi
    for passo in test build candidate deploy; do
      res="$(http_post "$BASE_URL/pipeline/$passo" "{\"operation\":\"$passo\",\"commit\":\"$sha\"}")" || {
        echo "STEP_${passo^^}_FALHOU: transporte" >&2
        exit 1
      }
      code="${res%%$'\t'*}"
      body="${res#*$'\t'}"
      if [[ "$code" =~ ^2 ]]; then
        echo "$body"
      else
        echo "STEP_${passo^^}_FALHOU: httpStatus=$code corpo=$body" # STEP_TEST_FALHOU STEP_BUILD_FALHOU STEP_CANDIDATE_FALHOU STEP_DEPLOY_FALHOU
        exit 1
      fi
    done
    ;;
  *)
    usage
    ;;
esac
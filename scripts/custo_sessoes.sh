#!/usr/bin/env bash
# custo_sessoes.sh — MOPS-CUSTO-REAL-01: custo EXATO por sessao do state.db.
# Fonte: tabela session_model_usage do Hermes (estimated_cost_usd via provider
# models API). LEITURA SOMENTE-LEITURA (sqlite mode=ro, uri) — nunca escreve.
# Saida: JSON de 1 linha, deterministico.
#   custo_sessoes.sh --data AAAA-MM-DD   -> sessoes do dia (last_seen, BRT) + total_usd
#   custo_sessoes.sh --sessao <ID>       -> custo daquela sessao
#   sessao inexistente                   -> {"ok":false,"error":"CUSTO_SESSAO_AUSENTE",...} (exit 3)
# Override de teste: GUARDIAN_STATE_DB aponta outro db (prova hermetica).
# Chamado como root com db do worker: tenta direto; se falhar, fallback
# `sudo -u worker` re-executando este mesmo script (unico uso de sudo aqui).
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# default: hoje em BRT quando nenhum --data/--sessao é dado
if [ $# -eq 0 ]; then
  set -- --data "$(TZ=America/Sao_Paulo date +%F)"
fi

custo__query() {
  python3 - "$@" <<'PYEOF'
import json, os, sqlite3, sys

args = sys.argv[1:]
modo = ""
valor = ""
i = 0
while i < len(args):
    if args[i] == "--data":
        modo = "data"; valor = args[i + 1]; i += 2
    elif args[i] == "--sessao":
        modo = "sessao"; valor = args[i + 1]; i += 2
    else:
        i += 1
if modo not in ("data", "sessao") or not valor:
    print(json.dumps({"ok": False, "error": "USO_INVALIDO"}))
    sys.exit(2)

db = os.environ.get("GUARDIAN_STATE_DB") or "/home/worker/.hermes/state.db"
try:
    conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
except sqlite3.Error as exc:
    print(json.dumps({"ok": False, "error": "DB_INDISPONIVEL", "detail": str(exc)}))
    sys.exit(4)

try:
    if modo == "sessao":
        rows = conn.execute(
            "SELECT COALESCE(SUM(api_call_count),0), COALESCE(SUM(input_tokens),0),"
            " COALESCE(SUM(output_tokens),0), COALESCE(SUM(cache_read_tokens),0),"
            " COALESCE(SUM(estimated_cost_usd),0), COUNT(*)"
            " FROM session_model_usage WHERE session_id = ?", (valor,)
        ).fetchone()
        if not rows[5]:
            print(json.dumps({"ok": False, "error": "CUSTO_SESSAO_AUSENTE", "sessao": valor}))
            sys.exit(3)
        print(json.dumps({"ok": True, "id": valor, "calls": rows[0],
                          "tokens_in": rows[1], "tokens_out": rows[2],
                          "cache": rows[3], "custo_usd": round(rows[4], 6)},
                         separators=(",", ":")))
    else:
        # data de last_seen convertida para BRT (UTC-3, sem horario de verao)
        rows = conn.execute(
            "SELECT session_id, SUM(api_call_count), SUM(input_tokens), SUM(output_tokens),"
            " SUM(cache_read_tokens), SUM(estimated_cost_usd)"
            " FROM session_model_usage"
            " WHERE strftime('%Y-%m-%d', last_seen, 'unixepoch', '+3 hours') = ?"
            " GROUP BY session_id ORDER BY session_id", (valor,)
        ).fetchall()
        sessoes = [{"id": r[0], "calls": r[1] or 0, "tokens_in": r[2] or 0,
                    "tokens_out": r[3] or 0, "cache": r[4] or 0,
                    "custo_usd": round(r[5] or 0.0, 6)} for r in rows]
        total = round(sum(s["custo_usd"] for s in sessoes), 6)
        print(json.dumps({"ok": True, "data": valor, "sessoes": sessoes,
                          "total_usd": total}, separators=(",", ":")))
finally:
    conn.close()
PYEOF
}

OUT="$(custo__query "$@" 2>&1)" && RC=0 || RC=$?
printf '%s\n' "$OUT"
if [ "$RC" -ne 0 ] && [ "$(id -u)" = "0" ]; then
  # db e do worker: fallback como worker (unico sudo permitido desta tool)
  OUT="$(sudo -u worker env GUARDIAN_STATE_DB="${GUARDIAN_STATE_DB:-/home/worker/.hermes/state.db}" bash "$SELF" "$@" 2>&1)" && RC=0 || RC=$?
  printf '%s\n' "$OUT"
fi
exit "$RC"

#!/usr/bin/env bash
# custo_sessoes.sh — MOPS-CUSTO-REAL-01/02: custo EXATO por sessao do state.db.
# Fonte: tabela session_model_usage do Hermes (estimated_cost_usd via provider
# models API). LEITURA SOMENTE-LEITURA (sqlite mode=ro, uri) — nunca escreve.
# Saida: JSON de 1 linha, deterministico.
#   custo_sessoes.sh --data AAAA-MM-DD   -> sessoes do dia (last_seen, BRT) + total_usd
#   custo_sessoes.sh --sessao <ID>       -> custo daquela sessao
#   sessao inexistente                   -> {"ok":false,"error":"CUSTO_SESSAO_AUSENTE",...} (exit 3)
# Override de teste: GUARDIAN_STATE_DB aponta outro db (prova hermetica,
# varre SOMENTE esse db).
# Desde MOPS-CUSTO-REAL-02: varre $HERMES_HOME/state.db + glob
# $HERMES_HOME/profiles/*/state.db (default HERMES_HOME=/home/worker/.hermes).
# Agrega por session_id; se o mesmo id aparecer em 2 bases, soma na que tiver
# last_seen mais recente (nao duplica).
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
import glob, json, os, sqlite3, sys

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

home = os.environ.get("HERMES_HOME") or "/home/worker/.hermes"
override = os.environ.get("GUARDIAN_STATE_DB")
if override:
    dbs = [override]
else:
    dbs = [os.path.join(home, "state.db")]
    dbs += sorted(glob.glob(os.path.join(home, "profiles", "*", "state.db")))

# rows[sid] = [calls, tin, tout, cache, custo, max_last_seen]
rows = {}
abertos = 0
for db in dbs:
    if not os.path.exists(db):
        continue
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    except sqlite3.Error:
        continue
    try:
        try:
            q = conn.execute(
                "SELECT session_id, SUM(api_call_count), SUM(input_tokens),"
                " SUM(output_tokens), SUM(cache_read_tokens), SUM(estimated_cost_usd),"
                " MAX(last_seen) FROM session_model_usage GROUP BY session_id")
        except sqlite3.Error:
            continue  # tabela ausente nessa base
        abertos += 1
        for sid, calls, tin, tout, cache, custo, last in q.fetchall():
            prev = rows.get(sid)
            if prev is None:
                rows[sid] = [calls or 0, tin or 0, tout or 0, cache or 0,
                             custo or 0.0, last]
            elif (last is not None and prev[5] is not None and last > prev[5]) \
                    or (last is not None and prev[5] is None):
                # base mais recente vence (sessao contada 1x)
                rows[sid] = [calls or 0, tin or 0, tout or 0, cache or 0,
                             custo or 0.0, last]
    finally:
        conn.close()

if abertos == 0:
    print(json.dumps({"ok": False, "error": "DB_INDISPONIVEL"}))
    sys.exit(4)

if modo == "sessao":
    r = rows.get(valor)
    if r is None:
        print(json.dumps({"ok": False, "error": "CUSTO_SESSAO_AUSENTE", "sessao": valor}))
        sys.exit(3)
    print(json.dumps({"ok": True, "id": valor, "calls": r[0],
                      "tokens_in": r[1], "tokens_out": r[2],
                      "cache": r[3], "custo_usd": round(r[4], 6)},
                     separators=(",", ":")))
else:
    # data de last_seen convertida para BRT (UTC-3, sem horario de verao)
    sessoes = [{"id": sid, "calls": r[0], "tokens_in": r[1],
                "tokens_out": r[2], "cache": r[3],
                "custo_usd": round(r[4], 6)}
               for sid, r in sorted(rows.items())
               if r[5] is not None
               and __import__("datetime").datetime.utcfromtimestamp(r[5] + 10800)
               .strftime("%Y-%m-%d") == valor]
    total = round(sum(s["custo_usd"] for s in sessoes), 6)
    print(json.dumps({"ok": True, "data": valor, "sessoes": sessoes,
                      "total_usd": total}, separators=(",", ":")))
PYEOF
}

OUT="$(custo__query "$@" 2>&1)" && RC=0 || RC=$?
printf '%s\n' "$OUT"
if [ "$RC" -ne 0 ] && [ "$(id -u)" = "0" ]; then
  # db e do worker: fallback como worker (unico sudo permitido desta tool)
  OUT="$(sudo -u worker env GUARDIAN_STATE_DB="${GUARDIAN_STATE_DB:-}" bash "$SELF" "$@" 2>&1)" && RC=0 || RC=$?
  printf '%s\n' "$OUT"
fi
exit "$RC"
#!/usr/bin/env bash
# espelho-segue.sh <BASE> — segue o run mais novo entre tentativas.
# ESPELHO-02: o stream passa pelo filtro do espelho.sh (--filtro-stream).
# GB-STREAM-CRU-01: o streamer volta a ver o TRANSCRIPT CRU do agente —
# tail -F do harness-trail.jsonl do run dir, convertido a texto puro legível
# (uma ação por linha: fala do agente + "preparing <tool>..." + resultado curto)
# via scripts/_trail_cru.py. O harness-pane.log estruturado continua acessível
# em trilha separada (arquivo pane, nunca apagado) — fail-open: sem trail, o
# stream cru simplesmente não emite, nada derruba.
BASE="${1:?uso: espelho-segue.sh <BASE>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
last=''
pid=''
pid_cru=''
while :; do
  f=$(ls -t "$BASE"/tentativa-*/run-*/harness-pane.log "$BASE"/run-*/harness-pane.log 2>/dev/null | head -1)
  if [ -n "$f" ] && [ "$f" != "$last" ]; then
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
    [ -n "$pid_cru" ] && kill "$pid_cru" 2>/dev/null
    echo "=== $(date +%H:%M:%S) acompanhando: $f ==="
    # trilha estruturada (pane log) — mantida, como antes
    tail -n 40 -F "$f" | bash "$DIR/espelho.sh" --filtro-stream &
    pid=$!
    # GB-STREAM-CRU-01: transcript cru do agente (trail jsonl -> texto puro)
    t="${f%harness-pane.log}harness-trail.jsonl"
    if [ -f "$t" ]; then
      tail -n 40 -F "$t" | python3 "$DIR/_trail_cru.py" &
      pid_cru=$!
    else
      pid_cru=''  # fail-open: transcript ausente = trilha ausente, sem erro
    fi
    last="$f"
  fi
  sleep 3
done
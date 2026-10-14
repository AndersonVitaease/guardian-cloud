#!/usr/bin/env bash
# espelho-segue.sh <BASE> — segue o harness-pane.log mais novo entre tentativas.
# ESPELHO-02: o stream agora passa pelo filtro do espelho.sh (--filtro-stream),
# destacando apenas fala do agente, patches, provas e veredito — sem lixo de terminal.
BASE="${1:?uso: espelho-segue.sh <BASE>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
last=''
pid=''
while :; do
  f=$(ls -t "$BASE"/tentativa-*/run-*/harness-pane.log "$BASE"/run-*/harness-pane.log 2>/dev/null | head -1)
  if [ -n "$f" ] && [ "$f" != "$last" ]; then
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
    echo "=== $(date +%H:%M:%S) acompanhando: $f ==="
    tail -n 40 -F "$f" | bash "$DIR/espelho.sh" --filtro-stream &
    pid=$!
    last="$f"
  fi
  sleep 3
done

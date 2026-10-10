#!/usr/bin/env bash
# espelho-segue.sh <BASE> — segue o harness-pane.log mais novo entre tentativas.
BASE="${1:?uso: espelho-segue.sh <BASE>}"
last=''
pid=''
while :; do
  f=$(ls -t "$BASE"/tentativa-*/run-*/harness-pane.log "$BASE"/run-*/harness-pane.log 2>/dev/null | head -1)
  if [ -n "$f" ] && [ "$f" != "$last" ]; then
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
    echo "=== $(date +%H:%M:%S) acompanhando: $f ==="
    tail -n 15 -F "$f" &
    pid=$!
    last=$f
  fi
  sleep 3
done

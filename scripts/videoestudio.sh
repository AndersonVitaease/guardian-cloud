#!/usr/bin/env bash
# MISSAO VIDEO-ESTUDIO-01 — fala -> edicao de video (embrulho video_tools.sh)
set -u
TRAIL=/home/worker/harness-s2/runs/videoestudio/videoestudio-trail.jsonl
TOOLS=/opt/mission-events/tools-bash/video_tools.sh
T0=$(date +%s%N)
mkdir -p "$(dirname "$TRAIL")"
ev(){ local step="$1" ok="$2" data="$3"; local ms=$(( ($(date +%s%N)-T0)/1000000 )); printf '{"t":"%s","ms":%s,"step":"%s","ok":%s,"data":%s}\n' "$(date -u +%FT%TZ)" "$ms" "$step" "$ok" "$data" >> "$TRAIL"; }
jout(){ printf '{"ok":%s,"error":"%s"}\n' "$1" "$2"; }

FRASE="${1:-}"; [ $# -ge 1 ] && shift || true
[ -n "$FRASE" ] && [ $# -ge 1 ] || { jout false ARGS_AUSENTES; exit 0; }
[ -n "${OPENROUTER_API_KEY:-}" ] || OPENROUTER_API_KEY=$(grep -m1 '^OPENROUTER_API_KEY=' /home/worker/.hermes/.env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
emit(){ printf '{"ok":false,"error":"%s"}\n' "$1"; exit 0; }
trap 'rc=$?; [ $rc -eq 0 ] || printf "{\"ok\":false,\"error\":\"VE_CRASH:rc=$rc\"}\n"' EXIT
OUT="${@: -1}"
ARQS=("${@:1:$#-1}")
[ -n "$FRASE" ] && [ ${#ARQS[@]} -ge 1 ] && [ -n "$OUT" ] || { jout false ARGS_AUSENTES; exit 0; }

for a in "${ARQS[@]}"; do
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$a" 2>/dev/null || true)
  ok=$(awk -v d="$d" 'BEGIN{print (d+0>0)?1:0}')
  [ "$ok" = "1" ] || { jout false "ARQ_INVALIDO:$a"; ev arq false "\"$a\""; exit 0; }
  ev arq true "\"$a dur=$d\""
done

# PLANO (1 chamada glm)
durs=""
for a in "${ARQS[@]}"; do
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$a" 2>/dev/null)
  durs="$durs $a duracao=$d;"
done
SYS='Você converte a frase em UMA lista JSON de operações para a tool video_tools.sh (ops: cut INI FIM IN OUT | concat OUT IN1 IN2 [INN...] | render TIMELINE_XML OUT — caminhos EXATOS dos arquivos fornecidos, saída em OUT; tempos relativos à duração real informada; NÃO invente arquivos). Responda SÓ o JSON: {"ops":[{"op":"cut","args":[...]}],"mudanca":"..."}'
USR="FRASE: $FRASE
ARQUIVOS:$durs
OUT: $OUT"
RESP=$(curl -sS --max-time 60 -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" \
  -d "$(jq -n --arg m "z-ai/glm-5.3-flash" --arg s "$SYS" --arg u "$USR" '{model:$m,max_tokens:2000,temperature:0,messages:[{role:"system",content:$s},{role:"user",content:$u}]}')" 2>/dev/null)
PLAN=$(printf '%s' "$RESP" | jq -r '.choices[0].message.content // empty' 2>/dev/null | tr -d '\n' | sed 's/^```json//;s/```$//')
[ -n "$PLAN" ] || PLAN=$(printf '%s' "$RESP" | jq -r '[.choices[0].message.reasoning // "", .choices[0].message.content // ""] | join("") | capture("(?<j>\\{\"ops\".*\\})") | .j' 2>/dev/null | tr -d '\n')
OPS=$(printf '%s' "$PLAN" | jq -c '.ops' 2>/dev/null)
MUD=$(printf '%s' "$PLAN" | jq -r '.mudanca // ""' 2>/dev/null)
[ -n "$OPS" ] && [ "$OPS" != "null" ] || { jout false VE_GLM_INUTIL; ev glm false '"parse"'; exit 0; }
ev glm true "\"$MUD\""

# EXECUTAR
TMPD="$PWD/tmp_ve_$$"; mkdir -p "$TMPD"
N=$(printf '%s' "$OPS" | jq 'length')
i=0
while [ $i -lt $N ]; do
  OP=$(printf '%s' "$OPS" | jq -r ".[$i].op")
  ARGS_JSON=$(printf '%s' "$OPS" | jq -c ".[$i].args")
  mapfile -t A < <(printf '%s' "$ARGS_JSON" | jq -r '.[]')
  RES=$(bash "$TOOLS" "$OP" "${A[@]}" 2>&1)
  LINE=$(printf '%s\n' "$RES" | grep -m1 '^{"ok"')
  OK=$(printf '%s' "$LINE" | jq -r '.ok // empty' 2>/dev/null)
  if [ "$OK" != "true" ]; then
    ev "op:$OP" false "\"$RES\""
    printf '{"ok":false,"error":"VE_OP_FALHOU:%s"}\n' "$OP"
    rm -rf "$TMPD"; exit 0
  fi
  ev "op:$OP" true "\"$LINE\""
  i=$((i+1))
done
rmdir "$TMPD" 2>/dev/null

# PROVA
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" 2>/dev/null)
SZ=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
OKD=$(awk -v d="$DUR" -v s="$SZ" 'BEGIN{print (d+0>0 && s+0>0)?1:0}')
[ "$OKD" = "1" ] || { jout false VE_OUT_INVALIDO; ev prova false "\"dur=$DUR sz=$SZ\""; exit 0; }
ev prova true "\"dur=$DUR\""
MS=$(( ($(date +%s%N)-T0)/1000000 ))
DURI=$(awk -v d="$DUR" 'BEGIN{printf "%d",(d*1000+500)/1000}')
printf '{"ok":true,"mudanca":"%s","out":"%s","dur":%s,"ms":%s}\n' "$MUD" "$OUT" "$DURI" "$MS"
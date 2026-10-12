#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
KEY=$(grep -m1 "^OPENROUTER_API_KEY=" /home/worker/.hermes/.env 2>/dev/null | cut -d= -f2-)
KEY=${KEY//\"/}; KEY=${KEY//\'/}
export OPENROUTER_API_KEY=$KEY
mkdir -p tmp
ffmpeg -y -v error -f lavfi -i testsrc=duration=4:size=320x240:rate=25 tmp/A.mp4
ffmpeg -y -v error -f lavfi -i smptebars=duration=4:size=320x240:rate=25 tmp/B.mp4
ffmpeg -y -v error -f lavfi -i color=c=red:duration=4:size=320x240:rate=25 tmp/C.mp4
FAIL=0
OUT=$(bash scripts/videoestudio.sh "corta os 2 primeiros segundos do clipe A e do clipe B e junta os dois cortes" tmp/A.mp4 tmp/B.mp4 tmp/final.mp4 | tail -1)
echo "$OUT" | grep -q '"ok":true' || { echo "FALHA1: $OUT"; FAIL=$((FAIL+1)); }
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 tmp/final.mp4 2>/dev/null)
awk -v d="$D" 'BEGIN{exit !(d>3.5 && d<4.5)}' || { echo "FALHA1 dur=$D"; FAIL=$((FAIL+1)); }
OUT2=$(bash scripts/videoestudio.sh "mantenha apenas 1 segundo do meio do final.mp4" tmp/final.mp4 tmp/final2.mp4 | tail -1)
echo "$OUT2" | grep -q '"ok":true' || { echo "FALHA2: $OUT2"; FAIL=$((FAIL+1)); }
D2=$(ffprobe -v error -show_entries format=duration -of csv=p=0 tmp/final2.mp4 2>/dev/null)
awk -v d="$D2" 'BEGIN{exit !(d>0.5 && d<1.5)}' || { echo "FALHA2 dur=$D2"; FAIL=$((FAIL+1)); }
echo "RESUMO: $FAIL falhas"

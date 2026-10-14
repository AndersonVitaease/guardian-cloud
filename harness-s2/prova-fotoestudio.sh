#!/usr/bin/env bash
# MISSAO FOTO-ESTUDIO-01 — prova do fotoestudio.sh
set -u
cd "$(dirname "$0")"
KEY=$(grep -m1 "^OPENROUTER_API_KEY=" /home/worker/.hermes/.env 2>/dev/null | cut -d= -f2-)
KEY=${KEY//\"/}; KEY=${KEY//\'/}
export OPENROUTER_API_KEY=$KEY
mkdir -p tmp
dim(){ ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$1" 2>/dev/null; }

# 1. PNG de teste 800x600
ffmpeg -y -v error -f lavfi -i color=c=blue:s=800x600 -frames:v 1 tmp/foto.png
FAIL=0

# 2. resize 400x300 + corta faixa de 50px do topo -> 400x250
OUT=$(bash scripts/fotoestudio.sh "redimensiona para 400x300 e corta uma faixa de 50px do topo" tmp/foto.png tmp/final.png | tail -1)
echo "$OUT" | grep -q '"ok":true' || { echo "FALHA2: $OUT"; FAIL=$((FAIL+1)); }
D=$(dim tmp/final.png)
AW=${D%%x*}; AH=${D##*x}
awk -v w="$AW" -v h="$AH" 'BEGIN{exit !(w>=398&&w<=402&&h>=248&&h<=252)}' || { echo "FALHA2 dim=$D"; FAIL=$((FAIL+1)); }

# 3. gira 90 graus + webp -> 250x400 webp
OUT2=$(bash scripts/fotoestudio.sh "gira 90 graus e converte para webp" tmp/final.png tmp/girado.webp | tail -1)
echo "$OUT2" | grep -q '"ok":true' || { echo "FALHA3: $OUT2"; FAIL=$((FAIL+1)); }
file tmp/girado.webp 2>/dev/null | grep -qi webp || { echo "FALHA3: nao-webp"; FAIL=$((FAIL+1)); }
D2=$(dim tmp/girado.webp)
AW2=${D2%%x*}; AH2=${D2##*x}
awk -v w="$AW2" -v h="$AH2" 'BEGIN{exit !(w>=248&&w<=252&&h>=398&&h<=402)}' || { echo "FALHA3 dim=$D2"; FAIL=$((FAIL+1)); }

echo "RESUMO: $FAIL falhas"

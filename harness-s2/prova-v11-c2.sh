#!/usr/bin/env bash
# prova-v11-c2.sh — prova da MISSAO V11-FAMILIA-C2
# Mata o filho (curl glm) no meio de 1 execução de cada agente
# (videoestudio.sh e fotoestudio.sh). Cada um precisa devolver JSON tipado
# {"ok":false,"error":"FILHO_MORTO"} em <10s (nunca wait eterno),
# padrão mecanico v1.1 (f402d8cb). Última linha: `RESUMO: X falhas`.
set -u
REPO=/home/worker/harness-s2
VID="$REPO/scripts/videoestudio.sh"
FOT="$REPO/scripts/fotoestudio.sh"
WORK="$REPO/runs/v11-c2"
FAILS=0
chk(){ if [ "$2" = "0" ]; then echo "[OK] $1"; else echo "[FAIL] $1 ($3)"; FAILS=$((FAILS+1)); fi; }

rm -rf "$WORK"; mkdir -p "$WORK"

# ---------- 1. sintaxe ----------
bash -n "$VID"; chk "bash -n scripts/videoestudio.sh" $? "sintaxe"
bash -n "$FOT"; chk "bash -n scripts/fotoestudio.sh" $? "sintaxe"

# ---------- 2. mídia de teste real (via ffmpeg) ----------
IN_V="$WORK/in.mp4"; OUT_V="$WORK/out.mp4"
IN_F="$WORK/in.png"; OUT_F="$WORK/out.png"
ffmpeg -y -v error -f lavfi -i color=c=black:s=64x64:d=0.5 -f lavfi -i anullsrc=r=8000:cl=mono -shortest -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$IN_V" 2>&1
ffmpeg -y -v error -f lavfi -i color=c=gray:s=64x64:d=0.1 -frames:v 1 "$IN_F" 2>&1
[ -s "$IN_V" ]; chk "mídia de teste video criada (mp4)" $? "ffmpeg falhou"
[ -s "$IN_F" ]; chk "mídia de teste foto criada (png)" $? "ffmpeg falhou"

# mata_filho <pid_pai> <var_saida_T0> — espera filho curl nascer e mata (-9)
mata_filho(){
  local PAI="$1"
  for _ in $(seq 1 100); do
    CP=$(pgrep -P "$PAI" -x curl 2>/dev/null | head -1)
    if [ -n "$CP" ]; then
      kill -9 "$CP" 2>/dev/null
      return 0
    fi
    kill -0 "$PAI" 2>/dev/null || return 1
    sleep 0.1
  done
  return 1
}

espera_json(){
  local PAI="$1" T0="$2"
  for _ in $(seq 1 100); do
    kill -0 "$PAI" 2>/dev/null || break
    sleep 0.1
  done
  kill -0 "$PAI" 2>/dev/null && { kill -9 "$PAI" 2>/dev/null; return 1; }
  local DT=$(( $(date +%s) - T0 ))
  [ "$DT" -lt 10 ] || return 1
  return 0
}

# ---------- 3. videoestudio: mata o filho (curl glm) no meio ----------
V_OUT="$WORK/saida-videoestudio.json"
bash "$VID" "prova filho morto v11-c2" "$IN_V" "$OUT_V" > "$V_OUT" 2>&1 &
VPID=$!
T_KILL_V=0
if mata_filho "$VPID"; then T_KILL_V=$(date +%s); V_MORTO=0; else V_MORTO=1; fi
chk "videoestudio: filho (curl glm) nasceu e foi morto no meio da execução" "$V_MORTO" "nenhum curl apareceu em 10s"

if [ "$V_MORTO" = "0" ]; then
  if espera_json "$VPID" "$T_KILL_V"; then V_RAPIDO=0; else V_RAPIDO=1; fi
  chk "videoestudio: saiu com JSON tipado em <10s" "$V_RAPIDO" "travou ou >10s"
  tail -1 "$V_OUT" | grep -qF '{"ok":false,"error":"FILHO_MORTO"}'
  chk "videoestudio: última linha = {\"ok\":false,\"error\":\"FILHO_MORTO\"}" $? "saída: $(tail -2 "$V_OUT" 2>/dev/null | tr '\n' ';')"
  grep -q 'FILHO_MORTO' "$REPO/runs/videoestudio/videoestudio-trail.jsonl" 2>/dev/null
  chk "videoestudio: trilha registra FILHO_MORTO" $? "sem FILHO_MORTO na trilha"
else
  chk "videoestudio: saiu com JSON tipado em <10s" 1 "sem filho para observar"
  chk "videoestudio: última linha = FILHO_MORTO" 1 "sem filho para observar"
  chk "videoestudio: trilha registra FILHO_MORTO" 1 "sem filho para observar"
fi

# ---------- 4. fotoestudio: mata o filho (curl glm) no meio ----------
F_OUT="$WORK/saida-fotoestudio.json"
bash "$FOT" "prova filho morto v11-c2" "$IN_F" "$OUT_F" > "$F_OUT" 2>&1 &
FPID=$!
T_KILL_F=0
if mata_filho "$FPID"; then T_KILL_F=$(date +%s); F_MORTO=0; else F_MORTO=1; fi
chk "fotoestudio: filho (curl glm) nasceu e foi morto no meio da execução" "$F_MORTO" "nenhum curl apareceu em 10s"

if [ "$F_MORTO" = "0" ]; then
  if espera_json "$FPID" "$T_KILL_F"; then F_RAPIDO=0; else F_RAPIDO=1; fi
  chk "fotoestudio: saiu com JSON tipado em <10s" "$F_RAPIDO" "travou ou >10s"
  tail -1 "$F_OUT" | grep -qF '{"ok":false,"error":"FILHO_MORTO"}'
  chk "fotoestudio: última linha = {\"ok\":false,\"error\":\"FILHO_MORTO\"}" $? "saída: $(tail -2 "$F_OUT" 2>/dev/null | tr '\n' ';')"
  grep -q 'FILHO_MORTO' "$REPO/runs/fotoestudio/fotoestudio-trail.jsonl" 2>/dev/null
  chk "fotoestudio: trilha registra FILHO_MORTO" $? "sem FILHO_MORTO na trilha"
else
  chk "fotoestudio: saiu com JSON tipado em <10s" 1 "sem filho para observar"
  chk "fotoestudio: última linha = FILHO_MORTO" 1 "sem filho para observar"
  chk "fotoestudio: trilha registra FILHO_MORTO" 1 "sem filho para observar"
fi

echo "RESUMO: $FAILS falhas"
exit $(( FAILS > 0 ? 1 : 0 ))
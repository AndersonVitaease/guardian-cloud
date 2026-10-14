#!/usr/bin/env bash
# prova-v11-c1.sh — prova da MISSAO V11-FAMILIA-C1
# Mata o filho no meio de 1 execução de cada agente (estudio.sh e sala.sh).
# Cada um precisa devolver JSON tipado {"ok":false,"error":"FILHO_MORTO"}
# em <10s (nunca wait eterno), padrão mecanico v1.1 (f402d8cb).
# Última linha: `RESUMO: X falhas`.
set -u
REPO=/home/worker/harness-s2
EST="$REPO/scripts/estudio.sh"
SAL="$REPO/scripts/sala.sh"
WORK="$REPO/runs/v11-c1"
FAILS=0
chk(){ if [ "$2" = "0" ]; then echo "[OK] $1"; else echo "[FAIL] $1 ($3)"; FAILS=$((FAILS+1)); fi; }

rm -rf "$WORK"; mkdir -p "$WORK"

# ---------- 1. sintaxe ----------
bash -n "$EST"; chk "bash -n scripts/estudio.sh" $? "sintaxe"
bash -n "$SAL"; chk "bash -n scripts/sala.sh" $? "sintaxe"

# ---------- 2. estudio: mata o filho (curl glm) no meio ----------
EST_OUT="$WORK/saida-estudio.json"
T_KILL_EST=0
bash "$EST" "prova filho morto v11-c1" > "$EST_OUT" 2>&1 &
EPID=$!
# espera um filho nascer (máx 10s) e mata; segue matando filhos até o guard pegar
EST_CHILD_MORTO=1
for _ in $(seq 1 100); do
  CP=$(pgrep -P "$EPID" 2>/dev/null | head -1)
  if [ -n "$CP" ]; then
    # prefere o curl (chamada glm, filho longo); senão mata o que houver
    CP2=$(pgrep -P "$EPID" -x curl 2>/dev/null | head -1)
    CP="${CP2:-$CP}"
    kill -9 "$CP" 2>/dev/null
    T_KILL_EST=$(date +%s)
    EST_CHILD_MORTO=0
    break
  fi
  kill -0 "$EPID" 2>/dev/null || break
  sleep 0.1
done
chk "estudio: filho nasceu e foi morto no meio da execução" "$EST_CHILD_MORTO" "nenhum filho apareceu em 10s"

# estudio deve sair sozinho com JSON tipado em <10s
EST_RAPIDO=0
if [ "$EST_CHILD_MORTO" = "0" ]; then
  for _ in $(seq 1 100); do
    kill -0 "$EPID" 2>/dev/null || { EST_RAPIDO=0; break; }
    sleep 0.1
  done
  kill -0 "$EPID" 2>/dev/null && { kill -9 "$EPID" 2>/dev/null; EST_RAPIDO=1; }
  DT=$(( $(date +%s) - T_KILL_EST ))
  [ "$DT" -lt 10 ] || EST_RAPIDO=1
  chk "estudio: saiu com JSON tipado em <10s (${DT}s)" "$EST_RAPIDO" "travou ou >10s"
  tail -1 "$EST_OUT" | grep -qF '{"ok":false,"error":"FILHO_MORTO"}'
  chk "estudio: última linha = {\"ok\":false,\"error\":\"FILHO_MORTO\"}" $? "saída: $(tail -2 "$EST_OUT" 2>/dev/null | tr '\n' ';')"
  grep -q 'FILHO_MORTO' "$REPO/runs/estudio/estudio-trail.jsonl" 2>/dev/null
  chk "estudio: trilha registra FILHO_MORTO" $? "sem FILHO_MORTO na trilha"
else
  chk "estudio: saiu com JSON tipado em <10s" 1 "sem filho para observar"
  chk "estudio: última linha = FILHO_MORTO" 1 "sem filho para observar"
  chk "estudio: trilha registra FILHO_MORTO" 1 "sem filho para observar"
fi

# ---------- 3. sala: mata o filho (subcomando status) no meio ----------
SAL_OUT="$WORK/saida-sala.json"
T_KILL_SAL=0
bash "$SAL" status > "$SAL_OUT" 2>&1 &
SPID=$!
SAL_CHILD_MORTO=1
for _ in $(seq 1 100); do
  CP=$(pgrep -P "$SPID" 2>/dev/null | head -1)
  if [ -n "$CP" ]; then
    kill -9 "$CP" 2>/dev/null
    T_KILL_SAL=$(date +%s)
    SAL_CHILD_MORTO=0
    break
  fi
  kill -0 "$SPID" 2>/dev/null || break
  sleep 0.1
done
chk "sala: filho nasceu e foi morto no meio da execução" "$SAL_CHILD_MORTO" "nenhum filho apareceu em 10s"

if [ "$SAL_CHILD_MORTO" = "0" ]; then
  SAL_RAPIDO=0
  for _ in $(seq 1 100); do
    kill -0 "$SPID" 2>/dev/null || { SAL_RAPIDO=0; break; }
    sleep 0.1
  done
  kill -0 "$SPID" 2>/dev/null && { kill -9 "$SPID" 2>/dev/null; SAL_RAPIDO=1; }
  DT=$(( $(date +%s) - T_KILL_SAL ))
  [ "$DT" -lt 10 ] || SAL_RAPIDO=1
  chk "sala: saiu com JSON tipado em <10s (${DT}s)" "$SAL_RAPIDO" "travou ou >10s"
  tail -1 "$SAL_OUT" | grep -qF '{"ok":false,"error":"FILHO_MORTO"}'
  chk "sala: última linha = {\"ok\":false,\"error\":\"FILHO_MORTO\"}" $? "saída: $(tail -2 "$SAL_OUT" 2>/dev/null | tr '\n' ';')"
else
  chk "sala: saiu com JSON tipado em <10s" 1 "sem filho para observar"
  chk "sala: última linha = FILHO_MORTO" 1 "sem filho para observar"
fi

echo "RESUMO: $FAILS falhas"
exit $(( FAILS > 0 ? 1 : 0 ))

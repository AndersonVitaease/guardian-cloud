#!/usr/bin/env bash
# mecanico.sh — agente MECÂNICO: cura determinística de misses com prova objetiva.
# MISSAO MECANICO-01 (contrato Entrega 1). bash puro; quem cura é o próprio script
# com 1 chamada glm por ciclo (máx 3 ciclos, budget $0.10). Todo caminho emite JSON
# (nunca morre calado). set -u com ${VAR:-}. SÓ escreve no REPO.
#
# Uso: mecanico.sh REPO "MISSAO_RESUMO"
#   Ações embutidas (5):
#     mapa    — inventário do alvo via find/grep (custo zero)
#     patch   — aplica diff por âncora exata (python3 heredoc, backup antes,
#               âncora ausente = MEC_ANCORA; script de patch atual: $MEC_PATCH_FILE)
#     prova   — executa o comando de prova e colhe saída REAL
#     decide  — prova falhou → 1 chamada glm (z-ai/glm-5.3-flash) com evidências
#               → próxima cura; 3 ciclos sem PASS → {"ok":false,"error":"MEC_ESCALADO"}
#     entrega — trilha JSONL + relatório + veredito tipado
#
# Cura PINTOR (Entrega 2, embutida como patch/prova default):
#   modelo: FLUX.1-schnell GGUF Q4_0 (second-state/FLUX.1-schnell-GGUF) em wt/models/,
#   models.json com single_file=false + vae ae.safetensors, prova prova-img-mcp.py
#   (prompt apple, 4 steps, 384x384, timeout 1800). PASS = PNG >0 bytes em images/.
set -u

REPO="${1:-}"
MISSAO="${2:-MECANICO}"
# V11: o JOB do argumento manda — cura do PINTOR só se o job for o pintor
PAINT=0
case "$MISSAO" in *[Pp]intor*) PAINT=1;; esac
[ -n "$REPO" ] && [ -d "$REPO" ] || { printf '{"ok":false,"error":"MEC_REPO_AUSENTE"}\n'; exit 0; }

TRAIL_DIR="$REPO/runs/mecanico"
# V11: trilha POR INSTÂNCIA (nunca compartilhada entre instâncias)
TRAIL="$TRAIL_DIR/mecanico-trail-$$.jsonl"
mkdir -p "$TRAIL_DIR"
T0=$(date +%s%N)
ev(){ local step="$1" ok="$2" data="$3"; local ms=$(( ($(date +%s%N)-T0)/1000000 ));
  printf '{"t":"%s","ms":%s,"step":"%s","ok":%s,"data":%s}\n' "$(date -u +%FT%TZ)" "$ms" "$step" "$ok" \
    "$(printf '%s' "$data" | tr '\n' ' ' | tr '"' "'" | cut -c1-300)" >> "$TRAIL"; }
jout(){ printf '{"ok":%s,"error":"%s"}\n' "$1" "$2"; ev saida "$1" "\"$2\""; }
trap 'rc=$?; [ $rc -eq 0 ] || { ev crash false "\"rc=$rc\""; printf "{\"ok\":false,\"error\":\"MEC_CRASH:rc=$rc\"}\n"; }' EXIT

# ---- cura configurável (defaults = conserto do PINTOR) ----
WT="${MEC_WT:-/home/worker/wt-RD-SUBJ-AUDIT-01}"
PROVA_PY="${MEC_PROVA:-$WT/prova-img-mcp.py}"
PROVA_TIMEOUT="${MEC_PROVA_TIMEOUT:-1800}"
PATCH_FILE="${MEC_PATCH_FILE:-$TRAIL_DIR/patch-pintor.py}"
EVID="$TRAIL_DIR/ultima-evidencia.txt"

# ---------- PATCH (embutido): âncora exata em prova-img-mcp.py + models.json ----------
# Backup antes; âncora ausente => MEC_ANCORA; idempotente.
cat > "$PATCH_FILE" <<'PYEOF'
import json, os, shutil, sys
WT = "/home/worker/wt-RD-SUBJ-AUDIT-01"
REPO = "/home/worker/harness-s2"
BK = os.path.join(REPO, "runs", "mecanico", "backup")
os.makedirs(BK, exist_ok=True)
def ancorepo(path, anchor, new, tag):
    """patch por âncora exata; âncora ausente = MEC_ANCORA"""
    if not os.path.isfile(path):
        print(f'{{"step":"patch","ok":false,"error":"MEC_ARQ_AUSENTE:{tag}"}}'); return False
    src = open(path).read()
    if new in src:
        print(f'{{"step":"patch","ok":true,"data":"{tag}: ja aplicado"}}'); return True
    if anchor not in src:
        print(f'{{"step":"patch","ok":false,"error":"MEC_ANCORA:{tag}"}}'); return False
    bkp = os.path.join(BK, os.path.basename(path) + ".bak")
    if not os.path.exists(bkp):
        shutil.copy2(path, bkp)
    open(path, "w").write(src.replace(anchor, new, 1))
    print(f'{{"step":"patch","ok":true,"data":"{tag}: aplicado"}}'); return True

ok1 = ancorepo(
    os.path.join(WT, "prova-img-mcp.py"),
    'MODEL = "flux2-klein-4b"',
    'MODEL = "flux1-schnell"', "prova-model")
ok2 = ancorepo(
    os.path.join(WT, "prova-img-mcp.py"),
    'resp = recv(p, 600)\ndt = time.time() - t0',
    'resp = recv(p, 1800)\ndt = time.time() - t0', "prova-timeout")
# models.json: single_file=false + vae ae.safetensors (idempotente)
ok3 = True
MJP = "/home/worker/.config/mcp-image-gen/models.json"
try:
    ms = json.load(open(MJP))
    hit = False
    for m in ms:
        if m.get("id") == "flux1-schnell":
            hit = True
            m["single_file"] = False
            m["vae"] = {"repo": "second-state/FLUX.1-schnell-GGUF", "file": "ae.safetensors"}
            m.setdefault("steps", 4); m.setdefault("width", 384); m.setdefault("height", 384)
    if not hit:
        print('{"step":"patch","ok":false,"error":"MEC_ANCORA:models.json flux1-schnell"}'); ok3 = False
    else:
        bkp = os.path.join(BK, "models.json.bak")
        if not os.path.exists(bkp): shutil.copy2(MJP, bkp)
        json.dump(ms, open(MJP, "w"), indent=2)
        print('{"step":"patch","ok":true,"data":"models.json: single_file=false + vae ae.safetensors"}')
except Exception as e:
    print(f'{{"step":"patch","ok":false,"error":"MEC_MODELS_JSON:{e}"}}'); ok3 = False
sys.exit(0 if (ok1 and ok2 and ok3) else 3)
PYEOF

# ---------- mapa ----------
mapa(){
  local inv
  inv=$( { find "$WT" -maxdepth 2 \( -name '*.gguf' -o -name '*.safetensors' -o -name 'models.json' -o -name 'prova-img-mcp*.py' \) 2>/dev/null | head -12
           grep -n 'MODEL = ' "$PROVA_PY" 2>/dev/null | head -2; } )
  ev mapa true "\"$(printf '%s' "$inv" | tr '\n' ';')\""
}

# ---------- modelo presente? (baixar só se ausente) ----------
GGUF="$WT/models/flux1-schnell-Q4_0.gguf"
VAE="$WT/models/models--second-state--FLUX.1-schnell-GGUF/snapshots/main/ae.safetensors"
ensure_model(){
  if [ -s "$GGUF" ] && [ -s "$VAE" ]; then
    ev modelo true "\"gguf=$(stat -c %s "$GGUF")B vae=presente\""; return 0
  fi
  ev modelo false "\"ausente: iniciando download second-state/FLUX.1-schnell-GGUF\""
  local url="https://huggingface.co/second-state/FLUX.1-schnell-GGUF/resolve/main/flux1-schnell-Q4_0.gguf"
  mkdir -p "$WT/models"
  if curl -L --fail -o "$WT/models/tmp-dl/flux1-schnell-Q4_0.gguf.part" "$url" 2>>"$TRAIL" \
     && mv "$WT/models/tmp-dl/flux1-schnell-Q4_0.gguf.part" "$GGUF"; then
    ev modelo true "\"download ok $(stat -c %s "$GGUF")B\""; return 0
  fi
  ev modelo false "\"download falhou\""
  jout false MEC_DOWNLOAD_FALHOU; exit 0
}

# ---------- decide: 1 chamada glm por ciclo ----------
decide(){
  [ -n "${OPENROUTER_API_KEY:-}" ] || OPENROUTER_API_KEY=$(grep -m1 '^OPENROUTER_API_KEY=' /home/worker/.hermes/.env 2>/dev/null | cut -d= -f2- | tr -d '"')
  if [ -z "${OPENROUTER_API_KEY:-}" ]; then ev decide false "\"sem key\""; return 1; fi
  local SYS='Você é o mecânico. Recebe a falha REAL da prova e devolve a PRÓXIMA CURA. Responda SÓ JSON: {"diagnostico":"...","acao":"uma das: patch|modelo|timeout|escalar","detalhe":"..."}'
  local USR="MISSAO: $MISSAO
EVIDENCIAS (últimas 30 linhas da prova):
$(tail -30 "$EVID" 2>/dev/null | cut -c1-2000)"
  local RESP
  RESP=$(curl -sS --max-time 90 -X POST https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" \
    -d "$(printf '{"model":"z-ai/glm-5.3-flash","max_tokens":400,"temperature":0,"messages":[{"role":"system","content":%s},{"role":"user","content":%s}]}' \
         "$(printf '%s' "$SYS" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
         "$(printf '%s' "$USR" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')")" 2>/dev/null)
  local DIAG
  DIAG=$(printf '%s' "$RESP" | python3 -c 'import json,sys
try: print(json.loads(sys.stdin.read())["choices"][0]["message"]["content"][:600])
except Exception: print("")' 2>/dev/null)
  ev decide true "\"${DIAG:-glm-sem-resposta}\""
  [ -n "$DIAG" ] || return 1
}

# ---------- V11: guard de interrupção — nunca esperar filho morto ----------
# Espera um PID com guarda: se já está morto, ou morreu por sinal (rc>=128,
# exceto 124=timeout e 143=SIGTERM do timeout), emite JSON tipado FILHO_MORTO
# e SEGUE (nunca trava esperando filho morto).
guard_wait(){
  local pid="$1" rc=0
  if ! kill -0 "$pid" 2>/dev/null; then
    ev filho_morto false "\"FILHO_MORTO:pid=$pid (ja morto)\""
    printf '{"event":"FILHO_MORTO","pid":%s}\n' "$pid"
    return 137
  fi
  wait "$pid"; rc=$?
  if [ "$rc" -eq 137 ]; then
    ev filho_morto false "\"FILHO_MORTO:pid=$pid (morto por sinal)\""
    printf '{"event":"FILHO_MORTO","pid":%s}\n' "$pid"
    return 137
  fi
  ev filho true "\"pid=$pid rc=$rc\""
  return $rc
}

# ---------- prova ----------
prova(){
  ev prova true "\"iniciando: python3 $PROVA_PY (timeout $PROVA_TIMEOUT s)\""
  # V11: filho spawnado com guard — se morrer no meio, FILHO_MORTO e segue
  timeout "$PROVA_TIMEOUT" python3 "$PROVA_PY" > "$EVID" 2>&1 &
  local fp=$!
  guard_wait "$fp"; local rc=$?
  if [ "$rc" -eq 0 ]; then
    ev prova true "\"$(tail -3 "$EVID" | tr '\n' ';')\""; return 0
  fi
  ev prova false "\"rc=$rc $(tail -3 "$EVID" | tr '\n' ';')\""; return 1
}

# ---------- entrega ----------
entrega(){
  local verdict="$1" motivo="$2"
  local PNG
  PNG=$(find "$WT/images" -maxdepth 1 -name '*.png' -size +0c 2>/dev/null | head -1)
  local REL="$TRAIL_DIR/relatorio-MECANICO-01.md"
  {
    echo "# MECANICO-01 — relatório"
    echo "- missao: $MISSAO"
    echo "- veredito: $verdict ($motivo)"
    echo "- png: ${PNG:-nenhum}"
    echo "- evidência (cauda da prova):"
    echo '```'
    tail -15 "$EVID" 2>/dev/null
    echo '```'
  } > "$REL"
  ev entrega true "\"verdict=$verdict motivo=$motivo\""
  printf '%s\n' "$REL"
}

# ---------- ciclo principal ----------
mapa

if [ "$PAINT" -eq 1 ]; then
  # cura do PINTOR (só quando o job $2 é o pintor)
  ensure_model
  CICLO=1
  while [ "$CICLO" -le 3 ]; do
    ev ciclo true "\"$CICLO/3\""
    if python3 "$PATCH_FILE" >> "$TRAIL" 2>&1; then
      ev patch true "\"ciclo=$CICLO\""
    else
      ev patch false "\"ciclo=$CICLO (ver erro MEC_ANCORA na trilha)\""
    fi
    if prova; then
      PNG=$(find "$WT/images" -maxdepth 1 -name '*.png' -size +0c 2>/dev/null | head -1)
      if [ -n "$PNG" ] && [ -s "$PNG" ]; then
        jout true "MEC_PASS"
        entrega PASS "PNG=$PNG"
        exit 0
      fi
      ev prova false "\"sem PNG em images/\""
    fi
    if [ "$CICLO" -lt 3 ]; then
      decide || ev decide false "\"glm indisponível — repete cura\""
    fi
    CICLO=$((CICLO+1))
  done

  jout false MEC_ESCALADO
  entrega FAIL "MEC_ESCALADO: 3 ciclos sem PASS"
  printf '{"ok":false,"error":"MEC_ESCALADO","evidencia":"%s"}\n' "$EVID"
  exit 0
fi

# ---------- job NÃO-pintor: o job do argumento manda — NÃO reprocessar o pintor ----------
ev job true "\"job nao-pintor: cura do pintor NAO executada\""
if [ -z "${MEC_PROVA:-}" ] || [ ! -f "$PROVA_PY" ]; then
  ev entrega true "\"job nao-pintor sem MEC_PROVA — nada a curar\""
  jout true "MEC_PASS_SEM_PROVA"
  entrega PASS "job nao-pintor sem prova configurada"
  exit 0
fi
if prova; then
  jout true "MEC_PASS"
  entrega PASS "prova do job ok"
  exit 0
fi
jout false MEC_PROVA_FALHOU
entrega FAIL "prova do job falhou (ver FILHO_MORTO na trilha se aplicável)"
printf '{"ok":false,"error":"MEC_PROVA_FALHOU","evidencia":"%s"}\n' "$EVID"
exit 0

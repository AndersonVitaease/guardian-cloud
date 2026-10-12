#!/usr/bin/env bash
# MISSAO FOTO-ESTUDIO-01 — fala -> edicao de foto (embrulho img_tools.sh + ImageMagick)
set -u
TRAIL=/home/worker/harness-s2/runs/fotoestudio/fotoestudio-trail.jsonl
TOOLS=/opt/mission-events/tools-bash/img_tools.sh
T0=$(date +%s%N)
mkdir -p "$(dirname "$TRAIL")"
ev(){ local step="$1" ok="$2" data="$3"; local ms=$(( ($(date +%s%N)-T0)/1000000 )); printf '{"t":"%s","ms":%s,"step":"%s","ok":%s,"data":%s}\n' "$(date -u +%FT%TZ)" "$ms" "$step" "$ok" "$data" >> "$TRAIL"; }
jout(){ printf '{"ok":%s,"error":"%s"}\n' "$1" "$2"; }
die(){ printf '{"ok":false,"error":"%s"}\n' "$1"; ev "${2:-fim}" false "\"$1\""; exit 0; }

# --- V11: guard de interrupção (padrão v1.1 do mecanico, f402d8cb) ---
# Filho morto/sinal → JSON tipado {"ok":false,"error":"FILHO_MORTO"} e veredito
# (nunca wait eterno).
guard_wait(){
  local pid="$1" rc=0
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" 2>/dev/null; rc=$?
    if [ "$rc" -eq 0 ]; then return 0; fi
    ev filho_morto false "\"FILHO_MORTO:pid=$pid (ja morto)\""
    jout false FILHO_MORTO
    exit 0
  fi
  wait "$pid"; rc=$?
  if [ "$rc" -ge 128 ]; then
    ev filho_morto false "\"FILHO_MORTO:pid=$pid (morto por sinal rc=$rc)\""
    jout false FILHO_MORTO
    exit 0
  fi
  return $rc
}
trap 'rc=$?; [ $rc -eq 0 ] || printf "{\"ok\":false,\"error\":\"FE_CRASH:rc=$rc\"}\n"' EXIT

FRASE="${1:-}"; [ $# -ge 1 ] && shift || true
[ -n "$FRASE" ] && [ $# -ge 1 ] || { jout false ARGS_AUSENTES; exit 0; }
[ -n "${OPENROUTER_API_KEY:-}" ] || OPENROUTER_API_KEY=$(grep -m1 '^OPENROUTER_API_KEY=' /home/worker/.hermes/.env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
OUT="${@: -1}"
IN="${1:-}"
[ -n "$IN" ] && [ -n "$OUT" ] || { jout false ARGS_AUSENTES; exit 0; }

# IN deve existir e ser imagem (png|jpeg|webp)
MIME=$(file -b --mime-type "$IN" 2>/dev/null || true)
case "$MIME" in
  image/png|image/jpeg|image/webp) : ;;
  *) die IN_INVALIDO in ;;
esac
DIM_IN=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$IN" 2>/dev/null || echo '?x?')
ev in true "\"$IN mime=$MIME dim=$DIM_IN\""

# PLANO (1 chamada glm, trava dura)
TMPD="tmp_fe_$$"; mkdir -p "$TMPD"
trap 'rc=$?; rm -rf "$TMPD" 2>/dev/null; [ $rc -eq 0 ] || printf "{\"ok\":false,\"error\":\"FE_CRASH:rc=$rc\"}\n"' EXIT
SYS='NÃO raciocine: responda DIRETAMENTE e só o JSON pedido, sem pensar. Converta a frase em UMA lista JSON de operações de edição de imagem usando APENAS: resize WxH, crop LxT WxH (recorte), rotate GRAUS, flip h|v, webp, thumb. Caminhos: só os fornecidos; primeiro comando lê IN e escreve OUT (intermediário tmp se >1 op). NÃO invente operações fora dessa lista. Formato dos args: resize -> [W,H,IN,OUT]; webp -> [IN,OUT]; thumb -> [IN,OUT]; crop -> [L,T,W,H,IN,OUT]; rotate -> [GRAUS,IN,OUT]; flip -> [h|v,IN,OUT]. Responda SÓ o JSON: {"ops":[{"op":"resize","args":[...]}],"mudanca":"..."}'
USR="FRASE: $FRASE
IN: $IN (dimensoes reais: $DIM_IN)
OUT: $OUT
TMP intermediarios disponiveis: $TMPD/i1.png (use se houver mais de 1 op; a ultima op DEVE escrever em OUT)"
# V11: curl spawnado com guard — filho morto no meio → FILHO_MORTO e veredito
RFILE="$TMPD/resp.json"
curl -sS --max-time 60 -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Content-Type: application/json" \
  -d "$(jq -n --arg m "z-ai/glm-5.3-flash" --arg s "$SYS" --arg u "$USR" '{model:$m,max_tokens:300,temperature:0,messages:[{role:"system",content:$s},{role:"user",content:$u}]}')" > "$RFILE" 2>/dev/null &
guard_wait "$!"
RESP=$(cat "$RFILE" 2>/dev/null)
PLAN=$(printf '%s' "$RESP" | jq -r '[.choices[0].message.reasoning // "", .choices[0].message.content // ""] | join("\n")' 2>/dev/null | python3 -c '
import sys, json
s = sys.stdin.read()
best = None
i = 0
while True:
    i = s.find("{", i)
    if i < 0: break
    try:
        o, _ = json.JSONDecoder().raw_decode(s[i:])
        ops = o.get("ops") if isinstance(o, dict) else None
        if isinstance(ops, list) and ops and all(isinstance(x, dict) and isinstance(x.get("op"), str) for x in ops):
            args = [a for x in ops for a in (x.get("args") or [])]
            if not any(isinstance(a, str) and a.strip() == "..." for a in args):
                best = o
    except Exception:
        pass
    i += 1
if best is None:
    j = s.rfind("{\"ops\"")
    if j >= 0:
        sub = s[j:]
        ops2 = []
        k = sub.find("{\"op\"")
        while k >= 0:
            try:
                o, _ = json.JSONDecoder().raw_decode(sub[k:])
                if isinstance(o, dict) and isinstance(o.get("op"), str) and isinstance(o.get("args"), list):
                    if not any(isinstance(a, str) and a.strip() == "..." for a in o["args"]):
                        ops2.append(o)
            except Exception:
                pass
            k = sub.find("{\"op\"", k + 1)
        if ops2:
            m2 = ""
            try:
                p = sub.find("\"mudanca\"")
                if p >= 0:
                    c = sub.find(":", p) + 1
                    v, _ = json.JSONDecoder().raw_decode(sub[c:])
                    if isinstance(v, str):
                        m2 = v
            except Exception:
                pass
            best = {"ops": ops2, "mudanca": m2}
print(json.dumps(best, ensure_ascii=False) if best else "")
'
)
OPS=$(printf '%s' "$PLAN" | jq -c '.ops' 2>/dev/null)
MUD=$(printf '%s' "$PLAN" | jq -r '.mudanca // ""' 2>/dev/null)
[ -n "$OPS" ] && [ "$OPS" != "null" ] || { jout false FE_GLM_INUTIL; ev glm false '"parse"'; rm -rf "$TMPD"; exit 0; }
ev glm true "\"$MUD\""

# EXECUTAR em ordem
N=$(printf '%s' "$OPS" | jq 'length')
i=0
while [ $i -lt "$N" ]; do
  OP=$(printf '%s' "$OPS" | jq -r ".[$i].op" 2>/dev/null)
  ARGS_JSON=$(printf '%s' "$OPS" | jq -c ".[$i].args" 2>/dev/null)
  mapfile -t A < <(printf '%s' "$ARGS_JSON" | jq -r '.[]' 2>/dev/null)
  RES=""
  case "$OP" in
    resize) RES=$(bash "$TOOLS" resize "${A[0]}" "${A[1]}" "${A[2]}" "${A[3]}" 2>&1) ;;
    webp)   RES=$(bash "$TOOLS" webp "${A[0]}" "${A[1]}" 2>&1) ;;
    thumb)  RES=$(bash "$TOOLS" thumb "${A[0]}" "${A[1]}" 2>&1) ;;
    crop)   RES=$(ffmpeg -y -v error -i "${A[4]}" -vf "crop=${A[2]}:${A[3]}:${A[0]}:${A[1]}" "${A[5]}" 2>&1 && echo '{"ok":true}') ;;
    rotate) G="${A[0]}"
            if [ "$G" = "90" ] || [ "$G" = "-270" ]; then RES=$(ffmpeg -y -v error -i "${A[1]}" -vf transpose=1 "${A[2]}" 2>&1 && echo '{"ok":true}')
            elif [ "$G" = "270" ] || [ "$G" = "-90" ]; then RES=$(ffmpeg -y -v error -i "${A[1]}" -vf transpose=2 "${A[2]}" 2>&1 && echo '{"ok":true}')
            else RES=$(ffmpeg -y -v error -i "${A[1]}" -vf "rotate=${G}*PI/180" "${A[2]}" 2>&1 && echo '{"ok":true}'); fi ;;
    flip)   if [ "${A[0]}" = "h" ]; then RES=$(ffmpeg -y -v error -i "${A[1]}" -vf hflip "${A[2]}" 2>&1 && echo '{"ok":true}');
            else RES=$(ffmpeg -y -v error -i "${A[1]}" -vf vflip "${A[2]}" 2>&1 && echo '{"ok":true}'); fi ;;
    *) RES="{\"ok\":false,\"error\":\"OP_DESCONHECIDA:$OP\"}" ;;
  esac
  LINE=$(printf '%s\n' "$RES" | grep -m1 '^{"ok"' || true)
  OK=$(printf '%s' "$LINE" | jq -r '.ok // empty' 2>/dev/null)
  if [ "$OK" != "true" ]; then
    ev "op:$OP" false "\"$RES\""
    printf '{"ok":false,"error":"FE_OP_FALHOU:%s"}\n' "$OP"
    rm -rf "$TMPD"; exit 0
  fi
  ev "op:$OP" true "\"$LINE\""
  i=$((i+1))
done

# PROVA: OUT existe, >0 bytes, imagem valida
SZ=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
MOUT=$(file -b --mime-type "$OUT" 2>/dev/null || true)
case "$MOUT" in image/png|image/jpeg|image/webp) : ;; *) MOUT="" ;; esac
if [ "$SZ" -le 0 ] 2>/dev/null || [ -z "$MOUT" ]; then
  jout false FE_OUT_INVALIDO; ev prova false "\"sz=$SZ mime=$MOUT\""; rm -rf "$TMPD"; exit 0
fi
ev prova true "\"$OUT $MOUT\""
rm -rf "$TMPD"
MS=$(( ($(date +%s%N)-T0)/1000000 ))
DIM_OUT=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$OUT" 2>/dev/null || echo '?x?')
printf '{"ok":true,"mudanca":"%s","out":"%s","dim":"%s","ms":%s}\n' "$MUD" "$OUT" "$DIM_OUT" "$MS"

#!/usr/bin/env bash
# ESTUDIO-01 - loop de design ao vivo: frase PT-BR -> patch em design.html
set -u
FRASE="${1:-}"
if [ -z "$FRASE" ]; then
  echo '{"ok":false,"error":"FRASE_AUSENTE"}'
  exit 0
fi

T0=$(date +%s%N)
TRAIL=/home/worker/harness-s2/runs/estudio/estudio-trail.jsonl
mkdir -p "$(dirname "$TRAIL")"
ev() {
  local step="$1" ok="$2" data="$3"
  local now; now=$(date +%s%N)
  local ms=$(( (now - T0) / 1000000 ))
  printf '{"t":"%s","ms":%s,"step":"%s","ok":%s,"data":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ms" "$step" "$ok" "$data" >> "$TRAIL"
}

DESIGN=/home/worker/guardian-app/design.html
ev "inicio" true "\"$FRASE\""

# --- V11: guard de interrupção (mesmo padrão do mecanico v1.1, f402d8cb) ---
# Filho morto/sinal → JSON tipado {"ok":false,"error":"FILHO_MORTO"} e sair
# com veredito (nunca wait eterno).
guard_wait(){
  local pid="$1" rc=0
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" 2>/dev/null; rc=$?
    if [ "$rc" -eq 0 ]; then return 0; fi
    ev filho_morto false "\"FILHO_MORTO:pid=$pid (ja morto)\""
    printf '{"ok":false,"error":"FILHO_MORTO"}\n'
    exit 0
  fi
  wait "$pid"; rc=$?
  if [ "$rc" -ge 128 ]; then
    ev filho_morto false "\"FILHO_MORTO:pid=$pid (morto por sinal rc=$rc)\""
    printf '{"ok":false,"error":"FILHO_MORTO"}\n'
    exit 0
  fi
  return $rc
}

# --- CONTEXTO: bloco do mascote (ou sidebar/card se a frase citar) ---
if printf '%s' "$FRASE" | grep -qi 'sidebar'; then
  LINHA=$(grep -n 'class="sidebar"' "$DESIGN" | head -1 | cut -d: -f1)
elif printf '%s' "$FRASE" | grep -qi 'card'; then
  LINHA=$(grep -n '\.card' "$DESIGN" | head -1 | cut -d: -f1)
else
  LINHA=$(grep -n 'mascote-v2' "$DESIGN" | head -1 | cut -d: -f1)
fi
if [ -z "${LINHA:-}" ]; then
  ev "contexto" false '"ancora de contexto nao encontrada"'
  echo '{"ok":false,"error":"ESTUDIO_ANCORA"}'
  exit 0
fi
INI=$(( LINHA - 2 )); [ "$INI" -lt 1 ] && INI=1
FIM=$(( LINHA + 30 ))
CONTEXTO=$(sed -n "${INI},${FIM}p" "$DESIGN")
ev "contexto" true "\"linhas $INI-$FIM\""

# --- CHAMADA GLM (1 por execucao, trava dura; ponte local 8103) ---
printf '%s\n' "$CONTEXTO" > /tmp/estudio-ctx.txt
REQ=$(FRASE="$FRASE" python3 - <<'PYEOF'
import json, os
frase = os.environ["FRASE"]
ctx = open('/tmp/estudio-ctx.txt').read()
sys_msg = ("Voce converte a frase do usuario em um patch UNIFIED DIFF minimo sobre o trecho "
           "SVG/CSS fornecido. Responda SO o diff, nada mais. Alvo: design.html. "
           "Proibido inventar ancoras inexistentes.")
print(json.dumps({
  "model": "z-ai/glm-5.3-flash",
  "max_tokens": 4000,
  "temperature": 0,
  "messages": [
    {"role": "system", "content": sys_msg},
    {"role": "user", "content": frase + "\n\nTrecho atual:\n" + ctx}
  ]
}))
PYEOF
)

OR_KEY="${OPENROUTER_API_KEY:-}"
[ -n "$OR_KEY" ] || OR_KEY=$(grep -m1 '^OPENROUTER_API_KEY=' /home/worker/.hermes/.env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
# bridge 8103 normaliza /v1/chat/completions para veredito allow/deny (CLASSNORM-01) ->
# chamada glm vai DIRETO ao OpenRouter (mesmo padrao do videoestudio.sh)
# V11: curl spawnado com guard — filho morto no meio → FILHO_MORTO e veredito
curl -sS --max-time 60 -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OR_KEY" -H 'Content-Type: application/json' \
  -d "$REQ" > /tmp/estudio-resp.json 2>/dev/null &
guard_wait "$!"
RESP=$(cat /tmp/estudio-resp.json 2>/dev/null)

# --- LIMPAR resposta do glm (python3 heredoc): content -> fallback reasoning;
# --- remove cercas ```diff/```; se vier JSON {alvo,patch_unified}, extrai patch_unified.
# --- Invalido/vazio -> ESTUDIO_GLM_INUTIL.
PATCH=$(printf '%s' "$RESP" | RESP_RAW="$RESP" python3 - <<'PYEOF'
import json, os, re, sys
raw = os.environ.get("RESP_RAW", "") or sys.stdin.read() or ""
try:
    m = json.loads(raw)["choices"][0]["message"]
except Exception:
    sys.exit(1)

def limpar(t):
    s = str(t or "").strip()
    if not s:
        return ""
    fm = None
    fences = re.findall(r"```(?:diff|json)?[ \t]*\r?\n?(.*?)```", s, re.S)
    if fences:
        # o reasoning traz rascunhos: prefere (do fim pro inicio) a cerca que
        # parece diff unified (- e +); senao a ultima
        for f in reversed(fences):
            if "\n-" in f and "\n+" in f:
                fm = f; break
        else:
            fm = fences[-1]
        s = fm.strip()
    try:
        j = json.loads(s)
        if isinstance(j, dict) and isinstance(j.get("patch_unified"), str):
            s = j["patch_unified"].strip()
            fj = re.search(r"```(?:diff)?[ \t]*\r?\n?(.*?)```", s, re.S)
            if fj:
                s = fj.group(1).strip()
    except Exception:
        pass
    return s

# content primeiro; glm as vezes devolve content=None com o diff no reasoning
# (mesmo padrao CLASSNORM do bridge) -> candidatos em ordem; prefere o que
# parece diff unified; invalido/vazio -> exit 1 (ESTUDIO_GLM_INUTIL)
cands = [m.get("content"), m.get("reasoning_content") or m.get("reasoning")]
limpos = [limpar(c) for c in cands]
for s in limpos:
    if s and ("@@@" in s or s.startswith(("---", "diff -", "@@")) or "\n@@" in s or "\n--- " in s):
        print(s); sys.exit(0)
for s in limpos:
    if s:
        print(s); sys.exit(0)
sys.exit(1)
PYEOF
) || { ev "glm" false '"resposta inutil"'; echo '{"ok":false,"error":"ESTUDIO_GLM_INUTIL"}'; exit 0; }

if ! printf '%s' "$PATCH" | grep -q '^---\|^@@'; then
  ev "glm" false '"resposta nao e diff"'
  echo '{"ok":false,"error":"ESTUDIO_GLM_INUTIL"}'
  exit 0
fi
ev "glm" true '"diff recebido"'

# --- APLICAR (backup + python3 heredoc, ancora EXATA) ---
cp "$DESIGN" "${DESIGN}.bak-estudio"
printf '%s' "$PATCH" > /tmp/estudio-patch.diff
APPLY_OUT=$(python3 - <<'PYEOF'
import sys
design = '/home/worker/guardian-app/design.html'
patch = open('/tmp/estudio-patch.diff').read()
lines = open(design).read().split('\n')
removals, additions = [], []
for ln in patch.split('\n'):
    if ln.startswith(('---', '+++', 'diff ')):
        continue
    if ln.startswith('@@'):
        continue
    if ln.startswith('-'):
        removals.append(ln[1:])
    elif ln.startswith('+'):
        additions.append(ln[1:])
if not removals or len(additions) != len(removals):
    print('SEM_REMOCAO'); sys.exit(3)
old_anchor = removals[0]
if old_anchor not in lines:
    # ancora pode estar embutida no MEIO de uma linha (SVG de uma linha so):
    # fallback substring: troca cada remocao pela adicao correspondente
    text = open(design).read()
    faltando = [r for r in removals if r not in text]
    if not faltando:
        # ancora embutida no MEIO de uma linha (SVG de uma linha so):
        # troca cada remocao pela adicao correspondente
        for i, r in enumerate(removals):
            add = additions[i] if i < len(additions) else ''
            text = text.replace(r, add, 1)
        if 'mascote-v2' not in text:  # integridade: nunca destruir o mascote
            print('ANCORA_NAO_ENCONTRADA'); sys.exit(2)
        open(design, 'w').write(text)
        print('OK'); sys.exit(0)
    # ancora com DRIFT (glm redigita a linha gigante do svg com variacao):
    # casa a linha de design com maior prefixo comum e a substitui INTEIRA
    # pelas adicoes (remocao~linha antiga, adicao~linha nova)
    def pfx(a, b):
        n = 0
        for x, y in zip(a, b):
            if x != y: break
            n += 1
        return n
    cand, best = -1, 0
    for i, ln in enumerate(lines):
        p = pfx(removals[0], ln)
        if p > best:
            cand, best = i, p
    if cand >= 0 and best >= 30 and best >= 0.9 * len(removals[0]) \
            and 0.5 * len(removals[0]) <= len(lines[cand]) <= 2 * len(removals[0]):
        new_lines = lines[:cand] + additions + lines[cand + 1:]
        out = '\n'.join(new_lines)
        if 'mascote-v2' in out:  # integridade: nunca destruir o mascote
            open(design, 'w').write(out)
            print('OK'); sys.exit(0)
    print('ANCORA_NAO_ENCONTRADA'); sys.exit(2)
idx = lines.index(old_anchor)
for i, r in enumerate(removals):
    if idx + i >= len(lines) or lines[idx + i] != r:
        print('ANCORA_NAO_ENCONTRADA'); sys.exit(2)
new_lines = lines[:idx] + additions + lines[idx + len(removals):]
open(design, 'w').write('\n'.join(new_lines))
print('OK')
PYEOF
) || true
if [ "$APPLY_OUT" != "OK" ]; then
  cp "${DESIGN}.bak-estudio" "$DESIGN"
  ev "aplicar" false "\"$APPLY_OUT\""
  echo '{"ok":false,"error":"ESTUDIO_ANCORA"}'
  exit 0
fi
ev "aplicar" true '"patch aplicado"'

# --- CONFIRMAR ao vivo ---
HTTP=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8140/)
MARCA=$(printf '%s' "$PATCH" | grep '^+' | grep -v '^+++' | head -1 | sed 's/^+//')
if [ -z "$MARCA" ] || [ "$HTTP" != "200" ] || ! curl -s http://127.0.0.1:8140/ | grep -qF "$MARCA"; then
  cp "${DESIGN}.bak-estudio" "$DESIGN"
  ev "confirmar" false "\"http=$HTTP\""
  echo '{"ok":false,"error":"ESTUDIO_NAO_POUSOU"}'
  exit 0
fi
ev "confirmar" true '"200 + marca presente"'

MS=$(( ($(date +%s%N) - T0) / 1000000 ))
MUDANCA=$(printf '%s' "$PATCH" | grep '^+' | grep -v '^+++' | head -3 | sed 's/^+//' | tr '\n' ' ' | cut -c1-120 | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"ok":true,"mudanca":"%s","ms":%s}\n' "$MUDANCA" "$MS"

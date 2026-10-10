#!/usr/bin/env bash
# roadmap_note.sh ID PRIO TEXTO [SECAO] [--apply] [--secao SECAO]
# Anexa item ao ROADMAP.md (default: /opt/mission-events/ROADMAP.md,
# sobrescrevel via env ROADMAP_PATH para teste hermetico).
# Padrao: DRY-RUN (mostra a linha que seria anexada e a linha de destino,
# nao altera o arquivo). Com --apply: backup do arquivo com sufixo
# .bak-YYYYMMDD-HHMM (via shutil.copy2, preserva metadados) e anexa ao fim
# da secao pedida (default: fim da ultima secao numerada) a linha
#   - **ID (prio PRIO)** — TEXTO — estado NAO INICIADO, Fila=nao
# Recusa ID duplicado (ID_DUPLICADO) e TEXTO vazio (TEXTO_VAZIO).
# Crases e pipes no TEXTO/PRIO sao trocados (crase vira apostrofo, pipe vira
# barra) para nao quebrar o markdown; a prova e feita com grep -n devolvendo
# a linha anexada. Saida: JSON 1 linha, exit 0 sempre, falha tipada.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
apply=0
secao=""
prev_secao=0
pos=()
for a in "$@"; do
  if [ "$prev_secao" -eq 1 ]; then secao="$a"; prev_secao=0; continue; fi
  case "$a" in
    --apply) apply=1 ;;
    --secao) prev_secao=1 ;;
    -*) tb_fail roadmap_note ARG_INVALID "$start" "${ARGS[@]}" ;;
    *) pos+=("$a") ;;
  esac
done
[ "$prev_secao" -eq 0 ] || tb_fail roadmap_note ARG_INVALID "$start" "${ARGS[@]}"
ms=$(( ($(date +%s%N) - start) / 1000000 ))
RN_MS="$ms"
export RN_MS
[ ${#pos[@]} -ge 3 ] || tb_fail roadmap_note ARG_INVALID "$start" "${ARGS[@]}"
id="${pos[0]}"
prio="${pos[1]}"
texto="${pos[2]}"
if [ ${#pos[@]} -eq 4 ] && [ -z "$secao" ]; then secao="${pos[3]}"; fi
roadmap="${ROADMAP_PATH:-/opt/mission-events/ROADMAP.md}"
[ ${#pos[@]} -le 4 ] || tb_fail roadmap_note ARG_INVALID "$start" "${ARGS[@]}"

OUT=$(python3 - "$id" "$prio" "$texto" "$secao" "$apply" "$roadmap" <<'PY'
import json, os, re, shutil, subprocess, sys, time

id_, prio, texto, secao, apply, path = (
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4],
    sys.argv[5] == "1", sys.argv[6])

def fail(code):
    sys.stdout.write("ERR:" + code + "\n")
    sys.exit(0)

if not id_ or len(id_) not in range(1, 65) or not re.match(r"^[A-Za-z0-9._-]+$", id_):
    fail("INVALID_ID")
bt = chr(96)
san = lambda s: s.replace(bt, "'").replace("|", "/")
prio = san(prio).strip()
texto = san(texto).strip()
if not prio:
    fail("INVALID_PRIO")
if not texto:
    fail("TEXTO_VAZIO")
if not os.path.isfile(path):
    fail("ROADMAP_NOT_FOUND")
try:
    with open(path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
except Exception:
    fail("ROADMAP_UNREADABLE")

if re.search(r"\*\*" + re.escape(id_) + r"\s*\(", content):
    fail("ID_DUPLICADO")

linha = "- **%s (prio %s)** — %s — estado NAO INICIADO, Fila=nao" % (
    id_, prio, texto)
lines = content.splitlines()
if content and not content.endswith("\n"):
    lines = content.split("\n")
head = re.compile(r"^(#{1,6})\s+(\d+(?:\.\d+)*)\.?\s")
heads = []
for i, l in enumerate(lines):
    m = head.match(l)
    if m:
        heads.append((i, len(m.group(1)), m.group(2)))

def num_eq(a, b):
    pa, pb = a.split("."), b.split(".")
    return pa == pb

if secao:
    alvo = None
    for i, lvl, n in heads:
        if num_eq(n, secao.strip(".")):
            alvo = (i, lvl)
            break
    if alvo is None:
        fail("SECAO_NAO_ENCONTRADA")
else:
    if not heads:
        fail("SECAO_NAO_ENCONTRADA")
    alvo = (heads[-1][0], heads[-1][1])
i0, lvl0 = alvo
idx = len(lines)
for i, lvl, n in heads:
    if i0 < i and lvl <= lvl0:
        idx = i
        break

def emit(dry, backup, grep):
    out = {"ok": True, "tool": "roadmap_note", "dry_run": dry, "id": id_,
           "linha": linha, "linha_destino": idx + 1, "secao": secao or None,
           "backup": backup, "grep": grep,
           "ms": int(float(os.environ.get("RN_MS", "0")))}
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))

if not apply:
    emit(True, None, None)
    sys.exit(0)

backup = None
try:
    ts = time.strftime("%Y%m%d-%H%M")
    backup = path + ".bak-" + ts
    if os.path.exists(backup):
        backup = path + ".bak-" + ts + "-" + str(int(time.time()) % 60)
    shutil.copy2(path, backup)
except Exception:
    fail("BACKUP_FALHOU")
new = lines[:idx] + [linha] + lines[idx:]
try:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(new) + "\n")
except Exception:
    fail("ESCRITA_FALHOU")
grep = None
try:
    p = subprocess.run(["grep", "-nF", "-m1", "**" + id_ + " (prio", path],
                       capture_output=True, text=True, timeout=10)
    if p.returncode == 0 and p.stdout.strip():
        grep = p.stdout.strip().splitlines()[0]
except Exception:
    grep = None
if grep is None:
    fail("PROVA_GREP_FALHOU")
emit(False, backup, grep)
PY
)
case "$OUT" in
  ERR:*)
    tb_audit roadmap_note "$(tb_join "${ARGS[@]}")" 0 "${OUT#ERR:}" "$start" || :
    printf '{"ok":false,"tool":"roadmap_note","error":"%s","ms":%s}\n' "${OUT#ERR:}" "$ms"
    exit 0 ;;
esac
tb_emit roadmap_note "$OUT" "$start" "${ARGS[@]}"
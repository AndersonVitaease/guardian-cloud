"""Memória de curto prazo para o bloco de diagnóstico (RD-HARN-RETRY-MEMORIA-01)."""
import json
import re

MAX_LIDOS = 8
MAX_ESCRITOS = 8
MAX_EDITS_FALHOS = 5

_SLICE_RE = re.compile(r"code_slice\.sh\s+(\S+)")


def _input_dict(ev):
    inp = ev.get("input")
    if isinstance(inp, dict):
        return inp
    if isinstance(inp, str):
        try:
            d = json.loads(inp)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def _dedup(items):
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def arquivos_lidos(recs):
    out = []
    for ev in recs:
        if ev.get("tool") == "Read":
            d = _input_dict(ev)
            p = d.get("path") or d.get("file_path")
            if p:
                out.append(p)
        elif ev.get("tool") == "Bash":
            cmd = _input_dict(ev).get("command") or ""
            m = _SLICE_RE.search(cmd)
            if m:
                out.append(m.group(1))
    return _dedup(out)[:MAX_LIDOS]


def arquivos_escritos(recs):
    out = []
    for ev in recs:
        if ev.get("tool") not in ("Write", "Edit"):
            continue
        if ev.get("is_error"):
            continue
        d = _input_dict(ev)
        p = d.get("path") or d.get("file_path")
        if p:
            out.append(p)
    return _dedup(out)[:MAX_ESCRITOS]


def edits_falhos(recs):
    counts = {}
    for ev in recs:
        if ev.get("tool") != "Edit" or not ev.get("is_error"):
            continue
        d = _input_dict(ev)
        p = d.get("path") or d.get("file_path") or "?"
        counts[p] = counts.get(p, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])[:MAX_EDITS_FALHOS]
    return [{"path": p, "vezes": n} for p, n in ordered]


def secao_memoria(recs):
    linhas = []
    lidos = arquivos_lidos(recs)
    if lidos:
        linhas.append("- arquivos lidos (N+1 recebe): %s" % ", ".join(lidos))
    escritos = arquivos_escritos(recs)
    if escritos:
        linhas.append("- arquivos escritos (N+1 recebe): %s" % ", ".join(escritos))
    falhos = edits_falhos(recs)
    if falhos:
        linhas.append("- Edits falhos (N+1 evita): %s" % (
            
            ", ".join("%s (%dx)" % (f["path"], f["vezes"]) for f in falhos),
        ))
    return linhas
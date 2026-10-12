#!/usr/bin/env python3
"""GB-STREAM-CRU-01 — trail jsonl estruturado -> transcript cru em TEXTO puro.

Lê (stdin) linhas do harness-trail.jsonl do runner e emite, uma ação por linha,
o mesmo formato do espelho antigo (/tmp/ag-*/sessao.log): texto do agente +
"preparing <tool>..." + resultado curto. A tradução PT-BR fica client-side
(_espelho_parse.py ptbr) — aqui NÃO traduzimos.

Fail-open: linha ilegível/corrompida é ignorada, nunca derruba o stream.
"""
import json
import sys

_LIM = 200  # limite de chars por campo na saída


def _curta(s, lim=_LIM):
    s = " ".join(str(s).split())
    return s if len(s) <= lim else s[: lim - 1] + "…"


def linha_crua(ev):
    """Uma linha de texto legível por evento do trail (ou None p/ descartar)."""
    if not isinstance(ev, dict):
        return None
    tool = ev.get("tool", "")
    turno = ev.get("turno", "")
    ts = ev.get("ts", "")
    if tool == "llm":
        # fala/decisão do agente: stop_reason e tamanho da resposta
        return "[%s] agente turno %s: stop=%s bytes=%s" % (
            ts, turno, ev.get("stop_reason", "?"), ev.get("bytes", "?"))
    if tool in ("_inicio", "_config", "_stop_check", "_vagueio_prompt"):
        return None  # ruído do runner, não é transcript do agente
    if tool == "_fim":
        return "[%s] agente fim: veredito=%s" % (ts, ev.get("veredito", "?"))
    # tool call do agente
    inp = ev.get("input")
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except Exception:
            inp = {"raw": inp}
    if isinstance(inp, dict):
        arg = inp.get("command") or inp.get("path") or inp.get("file_path") \
            or inp.get("pattern") or inp.get("old_string") or _curta(json.dumps(inp, ensure_ascii=False), 80)
    else:
        arg = _curta(inp, 80)
    status = "ok" if ev.get("ok", ev.get("erro") is None) else "erro"
    custo = ev.get("custo_usd", 0.0)
    return "[%s] preparing %s... %s | %s | $%.4f" % (ts, tool, _curta(arg), status, custo or 0.0)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue  # fail-open
        out = linha_crua(ev)
        if out:
            sys.stdout.write(out + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
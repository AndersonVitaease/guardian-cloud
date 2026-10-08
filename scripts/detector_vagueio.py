#!/usr/bin/env python3
"""Detector de vagueio para trails do harness-s2.

Regras (contrato detector-vagueio-01):
- Somente eventos `tool` (Bash/Read/Write/Edit); eventos com nome prefixado
  por `_` sao ignorados.
- Um turno e WRITE se a tool e Write/Edit ou se o input Bash contem
  `>`, `tee`, `sed -i`, `cat >`, `patch`, `cp ` (write-shaped); READ caso contrario.
- vagueando=True quando os ultimos N (default 6) eventos de tool sao
  >=83% READ e o mesmo comando (primeiros 80 chars) repete >=3 vezes neles.
- Linhas corrompidas/ausentes sao puladas; trail ausente ->
  vagueando=False, motivo='trail ausente'.
"""
import argparse
import json
import os
import re
import sys

TOOLS_VALIDAS = {"Bash", "Read", "Write", "Edit"}
WRITE_TOOLS = {"Write", "Edit"}
WRITE_TOKENS = (">", "tee", "sed -i", "cat >", "patch", "cp ")


def _extrair_comando(evento):
    """Extrai o comando/input de um evento de tool como string."""
    inp = evento.get("input", "")
    if isinstance(inp, dict):
        inp = inp.get("command") or inp.get("input") or json.dumps(inp, sort_keys=True)
    elif isinstance(inp, str) and inp.lstrip().startswith("{"):
        try:
            d = json.loads(inp)
            if isinstance(d, dict) and "command" in d:
                inp = d["command"]
        except (json.JSONDecodeError, ValueError):
            # input truncado: extrai o valor de "command" na unha
            idx = inp.find('"command"')
            if idx != -1:
                resto = inp[idx + len('"command"'):]
                dois = resto.find('": "')
                if dois == -1:
                    dois = resto.find('":"')
                if dois != -1:
                    inp = resto[dois + 4 if resto[dois + 2] == " " else dois + 3:]
                else:
                    # formato ': "valor' (sem aspas de fechamento)
                    asp = resto.find('"')
                    if asp != -1:
                        inp = resto[asp + 1:]
    if not isinstance(inp, str):
        inp = str(inp)
    return inp


_QUOTE_RE = re.compile(chr(39)+"[^"+chr(39)+"]*"+chr(39)+"|"+chr(34)+"[^"+chr(34)+"]*"+chr(34))
_REDIRECT_RE = re.compile(r"(?<![0-9&])>>?(?!&)")


def _eh_write(evento):
    if evento.get("tool") in WRITE_TOOLS:
        return True
    cmd = _extrair_comando(evento)
    cmd = _QUOTE_RE.sub("", cmd)
    if _REDIRECT_RE.search(cmd):
        return True
    return any(tok in cmd for tok in WRITE_TOKENS)


def analisar_trail(trail_path, janela=6):
    """Analisa um harness-trail.jsonl e retorna o dict de diagnostico."""
    resultado = {
        "vagueando": False,
        "motivo": "",
        "turnos_uteis": 0,
        "leitura_pct": 0.0,
    }
    if not os.path.isfile(trail_path):
        resultado["motivo"] = "trail ausente"
        return resultado

    eventos = []
    with open(trail_path, "r", encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                ev = json.loads(linha)
            except (json.JSONDecodeError, ValueError):
                continue  # linha corrompida: pula
            if not isinstance(ev, dict):
                continue
            tool = ev.get("tool")
            if not isinstance(tool, str) or tool.startswith("_"):
                continue
            if tool not in TOOLS_VALIDAS:
                continue
            eventos.append(ev)

    resultado["turnos_uteis"] = len(eventos)
    if not eventos:
        resultado["motivo"] = "sem eventos de tool"
        return resultado

    cauda = eventos[-janela:]
    reads = [not _eh_write(e) for e in cauda]
    leitura_pct = 100.0 * sum(reads) / len(cauda)
    resultado["leitura_pct"] = round(leitura_pct, 1)

    cmds = [_extrair_comando(e)[:80] for e in cauda]
    # normaliza números (ex.: /tmp/dbg8.py vs /tmp/dbg9.py) para detectar
    # o mesmo comando com contador/índice variando
    import re as _re
    norm = [_re.sub(r"\d+", "N", c) for c in cmds]
    repetido = False
    for c in set(norm):
        if norm.count(c) >= 3:
            repetido = True
            break

    if leitura_pct >= 83.0 and repetido:
        resultado["vagueando"] = True
        resultado["motivo"] = (
            "cauda read-only com comando repetido: "
            "%.0f%% READ na janela de %d" % (leitura_pct, len(cauda))
        )
    else:
        resultado["motivo"] = "ok"
    return resultado


def main(argv=None):
    parser = argparse.ArgumentParser(description="Detector de vagueio de trails")
    parser.add_argument("--trail", required=True, help="caminho do harness-trail.jsonl")
    parser.add_argument("--janela", type=int, default=6, help="tamanho da janela (default 6)")
    parser.add_argument("--json", action="store_true", help="saida em JSON")
    args = parser.parse_args(argv)

    if args.janela < 1:
        parser.error("--janela deve ser >= 1")

    res = analisar_trail(args.trail, janela=args.janela)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print("vagueando=%s motivo=%s turnos_uteis=%d leitura_pct=%.1f" % (
            res["vagueando"], res["motivo"], res["turnos_uteis"], res["leitura_pct"]))
    return 1 if res["vagueando"] else 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""Linter de contrato de missão: barato, regex, custo zero (stdlib)."""
import json
import re
import sys

STOP_BLOCK = re.compile(r"```harness-stop(.*?)```", re.S)
COND_CMD = re.compile(r"^cmd\s+(.+)$", re.M)
WC_L = re.compile(r"\bwc\s+-l\b")
TEST_F_SEM_PATH = re.compile(r"\btest\s+-f\s*(?:&&|$|\n)")
GREP_SEM_QL = re.compile(r"\bgrep\b(?![^\n|;&]*(?:\s-q\b|\s-l\b))")
ORIGIN_SEM_LSREMOTE = re.compile(r"\borigin(?:/\S+)?\b")
LSREMOTE = re.compile(r"\bgit\s+ls-remote\b")
ROOT_PATH = re.compile(r"(?:/opt/|/root/)\S*")


def _condicoes(stop_body):
    return [m.group(1).strip() for m in COND_CMD.finditer(stop_body or "")]


def lint(texto):
    achados = []
    blocos = STOP_BLOCK.findall(texto)
    conds = []
    for b in blocos:
        conds.extend(_condicoes(b))
    if not blocos or not conds:
        achados.append({"codigo": "SEM_STOP", "severidade": "erro",
                        "msg": "nenhum bloco ```harness-stop``` ou 0 condições parseadas"})
    for c in conds:
        linha = None
        for i, l in enumerate(texto.splitlines(), 1):
            if l.strip().startswith("cmd") and c in l:
                linha = i
                break
        if WC_L.search(c):
            achados.append({"codigo": "COND_FRAGIL", "severidade": "erro", "linha": linha,
                            "msg": "condição usa `wc -l` (sempre-True): %s" % c})
        if TEST_F_SEM_PATH.search(c):
            achados.append({"codigo": "COND_FRAGIL", "severidade": "erro", "linha": linha,
                            "msg": "`test -f` sem caminho (sempre-True): %s" % c})
        if GREP_SEM_QL.search(c):
            achados.append({"codigo": "COND_FRAGIL", "severidade": "erro", "linha": linha,
                            "msg": "`grep` sem -q/-l imprime no stdout do worker: %s" % c})
        if ORIGIN_SEM_LSREMOTE.search(c) and not LSREMOTE.search(c):
            achados.append({"codigo": "COND_GITHUB_URL", "severidade": "aviso", "linha": linha,
                            "msg": "condição referencia origin/ sem `git ls-remote` "
                                   "(comparação local==local é sempre-True): %s" % c})
    if len(texto) > 6000:
        achados.append({"codigo": "CONTEXTO_GIGANTE", "severidade": "aviso",
                        "msg": "contrato com %d chars (>6000): considere dividir em 2 missões" % len(texto)})
    if ROOT_PATH.search(texto):
        achados.append({"codigo": "PROIBIDO_ROOT_PATH", "severidade": "erro",
                        "msg": "escrita direta em /opt/ ou /root/ no goal (worker não escreve lá — "
                               "padrão ADENDO: entrega no cwd, supervisor aplica)"})
    return achados


def main():
    if len(sys.argv) != 2:
        print("uso: contrato_lint.py <contrato.md>", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        achados = lint(f.read())
    print(json.dumps(achados, ensure_ascii=False, indent=2))
    return 1 if any(a["severidade"] == "erro" for a in achados) else 0


if __name__ == "__main__":
    sys.exit(main())
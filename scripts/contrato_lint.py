#!/usr/bin/env python3
"""Linter de contrato de missão: barato, regex, custo zero (stdlib)."""
import json
import os
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
FENCE_ERRADA = re.compile(r"^```[^\s`]+\s+harness-stop\s*$", re.M)
CD_ABS = re.compile(r"(?:^|&&\s*)cd\s+(/\S+)")
TRIVIAL = re.compile(r"^(?:test\s+-[fde]\s+\S+|true|:|ls\b.*|echo\b.*)$")
ARQ_CODIGO = re.compile(r"\b[\w./-]+\.(?:js|mjs|py|sh|ts)\b")
ARQ_LINHA = re.compile(r"\b[\w./-]+\.\w+:\d+\b")
SECAO_MAPA = re.compile(r"##\s*MAPA")
TITULO_ID = re.compile(r"^#\s+MISS(?:Ã|A)O\s+(\S+)", re.M | re.I)
REL_ID = re.compile(r"RELATORIO-([A-Z0-9-]+)\.md", re.I)
GITLOG_F = re.compile(r"git\s+log[^\n]*-F\s+'([^']+)'")
PROVA_EXEC = re.compile(r"python3\s+prova-\S+|node\s+server")
ISOLAMENTO = re.compile(r"mktemp|tempfile|GUARDIAN_DB_DIR|(?<!/)tmp\b")
VERBO_ESCRITA = re.compile(r"escrev|grave|crie|criar|write|salve|mv\s|cp\s|>", re.I)


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
    # 1. FENCE_ERRADA: fence com texto entre os crases e harness-stop
    for i, l in enumerate(texto.splitlines(), 1):
        if FENCE_ERRADA.match(l.strip()) and not l.strip().startswith("```harness-stop"):
            achados.append({"codigo": "FENCE_ERRADA", "severidade": "erro", "linha": i,
                            "msg": "fence de stop com texto entre os crases (parser ignora, 0 stops): %s" % l.strip()})
    # 2. STOP_PATH_INEXISTENTE: cd para caminho absoluto que não existe
    for c in conds:
        for m in CD_ABS.finditer(c):
            caminho = m.group(1).rstrip(";")
            if not os.path.isdir(caminho):
                achados.append({"codigo": "STOP_PATH_INEXISTENTE", "severidade": "erro",
                                "msg": "stop faz cd para diretório inexistente: %s" % caminho})
    # 3. STOP_SO_TRIVIAL: todas as condições são triviais
    if conds:
        def _corpo(c):
            m = re.match(r"^cd\s+\S+\s*&&\s*(.*)$", c)
            return m.group(1).strip() if m else c.strip()
        if all(TRIVIAL.match(_corpo(c)) for c in conds):
            achados.append({"codigo": "STOP_SO_TRIVIAL", "severidade": "erro",
                            "msg": "todos os stops são triviais (test -f/-d/-e, true, :, ls, echo) — não provam entrega"})
    # 4. SEM_MAPA: >=3 arquivos de código e sem arquivo:NNN nem ## MAPA
    arqs = set(a.group(0) for a in ARQ_CODIGO.finditer(texto))
    if len(arqs) >= 3 and not ARQ_LINHA.search(texto) and not SECAO_MAPA.search(texto):
        achados.append({"codigo": "SEM_MAPA", "severidade": "erro",
                        "msg": "cita %d arquivos de código sem ## MAPA nem referência arquivo:NNN" % len(arqs)})
    # 5. ID_DIVERGENTE: título vs RELATORIO-<X>.md / git log -F '<X>'
    m = TITULO_ID.search(texto)
    if m:
        tid = m.group(1).rstrip("—-– ")
        for r in REL_ID.finditer(texto):
            if r.group(1) != tid:
                achados.append({"codigo": "ID_DIVERGENTE", "severidade": "erro",
                                "msg": "RELATORIO-%s.md difere do ID do título (%s)" % (r.group(1), tid)})
        for g in GITLOG_F.finditer(texto):
            if g.group(1) != tid:
                achados.append({"codigo": "ID_DIVERGENTE", "severidade": "erro",
                                "msg": "git log -F '%s' difere do ID do título (%s)" % (g.group(1), tid)})
    # 6. PROVA_SEM_ISOLAMENTO
    if any(PROVA_EXEC.search(c) for c in conds) and not ISOLAMENTO.search(texto):
        achados.append({"codigo": "PROVA_SEM_ISOLAMENTO", "severidade": "aviso",
                        "msg": "stop executa prova/node server sem menção a mktemp/tempfile/tmp/GUARDIAN_DB_DIR "
                               "(uma execução envenena a seguinte)"})
    # 7. refino PROIBIDO_ROOT_PATH / LEITURA_ROOT_PATH
    for i, l in enumerate(texto.splitlines(), 1):
        if ROOT_PATH.search(l):
            if VERBO_ESCRITA.search(l):
                achados.append({"codigo": "PROIBIDO_ROOT_PATH", "severidade": "erro", "linha": i,
                                "msg": "escrita em /opt/ ou /root/ (worker não escreve lá — "
                                       "padrão ADENDO: entrega no cwd, supervisor aplica)"})
            else:
                achados.append({"codigo": "LEITURA_ROOT_PATH", "severidade": "aviso", "linha": i,
                                "msg": "menção a /opt/ ou /root/ sem verbo de escrita: confirme que é só leitura"})
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
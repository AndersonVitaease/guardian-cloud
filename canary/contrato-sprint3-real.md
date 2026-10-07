# SPRINT3 REAL — SPRINT3-PYPIN-S{{SEED}} (HARNESS-SPRINT3-01)

Tarefa de higiene REAL (não-canária) num repo existente: no worktree `/tmp/eng-mcp-wt-harness-sprint3-01/eng-mcp`, substituir toda ocorrência de `python3` solto por `/usr/bin/python3` (absoluto) **apenas nos manifestos `verify-*.json`** (arquivos `verify-*.json` na raiz do repo). Nada mais deve ser alterado: não toque em código-fonte, testes, READMEs ou outros arquivos.

## Regras
- Edite SOMENTE arquivos `verify-*.json` do worktree.
- Substitua `python3` solto (não precedido de `/` nem parte de `python3.x`) por `/usr/bin/python3`. Ocorrências já absolutas (`/usr/bin/python3`) ficam como estão.
- Cada `verify-*.json` editado deve continuar JSON válido (`/usr/bin/python3 -c "import json;json.load(open('<arquivo>'))"`).
- Não faça commit, push ou merge — só edite os arquivos no disco do worktree.

## Entregáveis (todos no cwd da run)
1. Os `verify-*.json` do worktree com o pin aplicado.
2. `RELATORIO-sprint3-loop.md` (pt-BR): o que foi alterado (lista de arquivos + nº de substituições), como validou (JSON válido, zero `python3` solto restante), e a linha `Veredito: PASS` + `PARE` — só depois de rodar o verificador abaixo e ele sair 0.

Verificador (rode você mesmo antes do relatório):
`/usr/bin/python3 -c "import glob,re,sys,json; bad=[f for f in glob.glob('verify-*.json') if re.search(r'(?<![\w/.-])python3', open(f).read())]; [json.load(open(f)) for f in glob.glob('verify-*.json')]; sys.exit(1 if bad else 0)"`

```harness-stop
file RELATORIO-sprint3-loop.md
cmd /usr/bin/python3 -c "import glob,re,sys,json; bad=[f for f in glob.glob('verify-*.json') if re.search(r'(?<![\w/.-])python3', open(f).read())]; [json.load(open(f)) for f in glob.glob('verify-*.json')]; sys.exit(1 if bad else 0)"
marker PASS RELATORIO-sprint3-loop.md
```
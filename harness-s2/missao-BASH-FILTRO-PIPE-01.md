# MISSÃO BASH-FILTRO-PIPE-01 — Causa raiz do vagueio em missao grande (visto na RD-GB-ABUSE-01C: 16 de 26 Bash recusados em 0 ms, zero Write/Edit): head/tail usados como FILTRO de pipe sem arquivo sao recusados como FILE_READ, e o split por '|' quebra padroes grep com \| escapado

## MAPA
- harness.py | ~12 linhas | So a funcao _bash_redirect (linhas ~259-304). Maximo 2 turnos de leitura. (1) Linha ~265: troque o split por re.split(r'\|\||&&|;|(?<!\\)\|', cmd) para nao partir um '\|' escapado dentro do padrao do grep (barra invertida antes do pipe). (2) Linhas ~273-280 (o bloco 'if toks[0] in {cat, head, tail}'): so recuse como FILE_READ/STATE_READ quando o segmento tem OPERANDO de arquivo: operandos = [x for x in toks[1:] if not x.startswith('-') and not x.isdigit()]; se operandos for vazio (head/tail/cat usado como filtro de pipe, ex.: 'grep x f | head -5' ou 'tail -n 20') NAO recuse nem classifique aqui: apenas siga (continue) para o proximo segmento e deixe o plan.append(toks) normal. Um 'cat arquivo' ou 'head -5 arquivo' (com operando) continua recusado exatamente como hoje. Nao mude mais nada.

## Regras
- PROIBIDO git reset/checkout/stash/clean; só git add/commit.
- Checkpoint commit como worker ANTES das edições.
- Não toque em routing/bridge nem no dir de produção root-only.
- Sem sudo nos comandos dos stops.

## Stops
```harness-stop
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && python3 -m py_compile harness.py
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && python3 -c "import harness as h; r=h._bash_redirect('cd /x && grep -n \"a\\|b\" db.mjs | head'); assert r['kind']!='refuse', r"
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && python3 -c "import harness as h; r=h._bash_redirect('cat server.js'); assert r['kind']=='refuse' and r['error']=='FILE_READ', r"
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && python3 -c "import harness as h; r=h._bash_redirect('head -5 server.js'); assert r['kind']=='refuse', r"
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && python3 -m unittest tests.test_enforce tests.test_toolbash 2>&1 | tail -1 | grep -q '^OK'
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && git diff --quiet HEAD -- harness.py
cmd cd /home/worker/wt-BASH-FILTRO-PIPE-01 && python3 -m unittest tests.test_enforce tests.test_toolbash 2>&1 | tail -1 | grep -q '^OK'
cmd git log -1 --pretty=%s | grep -q 'BASH-FILTRO-PIPE-01'
```

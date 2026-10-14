# MISSÃO RD-H4-REPORT-01 — Port do lint STOP_RELATIVO para o código atual

## Contexto / lição H4 (wt-H4-VAGUEIO, commit da7004bd)
O H4-JANELA-LEITURA mostrou que o cwd da run precisa atravessar `_bash_redirect`
(hoje `harness.py:293 def _bash_redirect(cmd)` na linhagem atual recebe `cmd`
sem cwd em `harness.py:820`). O lint STOP_RELATIVO nasceu em DESP-CWD-01
(repo desp-rapido, branch H2B-CWD-ABSOLUTO, `scripts/despachar_rapido.py`
`validar_contrato` ~linha 100) e NÃO existe na linhagem rd-segue-01
(0 matches de STOP_RELATIVO em /home/worker/harness-s2 — conferido).
Um stop SEM `cd <abs> && ` deixa o worker solto no cwd da run = vagueio.

## Objetivo
Portar o lint STOP_RELATIVO para o código ATUAL do rd-segue-01: em
`scripts/contrato_lint.py`, toda condição `cmd` do bloco harness-stop
deve começar com `cd <caminho-ABSOLUTO> && `; caso contrário, achado
`STOP_RELATIVO` (severidade erro), mensagem apontando o padrão correto.
Apoie-se no padrão `CD_ABS` que JÁ existe (`contrato_lint.py:14`).

## MAPA (código ATUAL, rd-segue-01 @ 42634c08)
- `scripts/contrato_lint.py:24:lint` — lista de achados; adicionar checagem nova
  (nº 8) sobre `conds` (já coletadas em `lint`, linha 26-31, via `_condicoes`
  em `scripts/contrato_lint.py:21:_condicoes`).
- `scripts/contrato_lint.py:14` — `CD_ABS` (regex de `cd /abs`), reaproveitar
  ou criar regex de prefixo `^cd\s+/\S+\s*&&\s+\S`.
- `tests/test_contrato_lint.py` — testes novos aqui (pytest, funções).
- NÃO é alvo: `harness.py` (o _bash_redirect atual fica como está).

## Escopo ESTREITO
Só o lint STOP_RELATIVO + detector + testes. NÃO refatore nada mais,
não toque em `harness.py`, `fatiador.py`, `despachar_*`.

## Regras
- Escreva com Write/Edit; leitura de código só via code_slice (≤120 linhas)
  e code_find. Nunca root: python3/pytest como `sudo -u worker`.
- Stops SEMPRE prefixo `cmd`, caminho absoluto, stops COMPORTAMENTAIS
  (nada de `test -f`).
- Testes novos: pytest em funções (estilo tests/test_contrato_lint.py atual).

## Fora de escopo / anotação DESP-CWD-01
O port COMPLETO de DESP-CWD-01 (validar_contrato em despachar_rapido.py)
não cabe aqui: `scripts/despachar_rapido.py` NÃO existe no repo harness-s2
(o de produção está em /opt/mission-events/scripts, fora do escopo de
worktree). Fica para missão própria.

## Aceites (stop conditions — cada uma roda como worker no cwd abaixo)
```harness-stop
cmd cd /home/worker/wt-RD-H4-REPORT-01 && python3 -m pytest tests/test_contrato_lint.py -q 2>&1 | tail -1 | grep -q passed
cmd cd /home/worker/wt-RD-H4-REPORT-01 && python3 -c "open('fabricado-relativo.md','w').write('# M\n\n' + chr(96)*3 + 'harness-stop\ncmd grep -q padrao arq.py\n' + chr(96)*3 + '\n')" && python3 scripts/contrato_lint.py fabricado-relativo.md | grep -q STOP_RELATIVO
cmd cd /home/worker/wt-RD-H4-REPORT-01 && python3 scripts/contrato_lint.py MISSAO-RD-H4-REPORT-01.md
```
A 2ª é o stop E2E real: fabrica um contrato com stop relativo (sem cd) e
exige que o lint acuse STOP_RELATIVO. A 3ª exige o lint do PRÓPRIO
contrato verde (exit 0).

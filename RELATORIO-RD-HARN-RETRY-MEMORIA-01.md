# RELATORIO RD-HARN-RETRY-MEMORIA-01

## O que `scripts/diagnostico_memoria.py` entrega
Extrai do trail `harness-trail.jsonl` da tentativa anterior:
- **Arquivos lidos** — lista de leituras registradas na trilha.
- **Arquivos escritos** — artefatos produzidos na tentativa anterior.
- **Edits falhos** — tentativas de edição que não aplicaram.

Esse resumo é injetado no prompt da tentativa N+1, curando o problema dos **57% de leituras repetidas**: a nova tentativa começa sabendo o que já foi lido/escrito/falhado, sem reler do zero.

## Rollback
O wiring em `scripts/diagnostico.py` é desativável por ambiente: `DIAG_MEMORIA=0` desliga a injeção de memória (rollback seguro).

## Deploy
O deploy é responsabilidade do **supervisor**; o worker entrega apenas código, testes (4/4 verdes em `tests/test_diagnostico_memoria.py`) e este relatório.
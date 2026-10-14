# RELATORIO-RD-CONTRATADOR-01

CONTRATADOR-OK

## Desenho
`scripts/contratador.sh <ID> [--dry-run]`: extrai o item do ROADMAP (grep -n), faz diagnóstico $0 dos arquivos citados (existência + nº de linhas), escreve `contratos/contract-<ID>.md` no padrão da casa (CONTEXTO, ENTREGAS, Regras com MAPA-DE-TOOLS e proibição git reset/checkout/stash/sudo//root//opt, MAPA, Critérios, harness-stop com linhas `cmd`), roda `contrato_lint.py` e, sem `--dry-run`, despacha via `wt_spin.sh` + `despachar_missao.py --budget 0.20`, imprimindo JSON 1 linha `{"ok":true,"id":...,"unit":...,"pane":...,"run_dir":...}`.

## Guardas
- **Lint com 3 tentativas**: em erro, corrige deterministicamente (garante `## MAPA` e referência `arquivo:NNN`) e re-linta; após 3 falhas, `{"ok":false,"erro":"LINT_3_TENTATIVAS"}` e escala.
- **Infra sensível**: item citando orchestrator-consumer/routing/bridge//root → imprime `ESCALA-SUPERVISOR` e NÃO despacha.
- **ITEM_AUSENTE**: ID sem linha no ROADMAP → `{"ok":false,"erro":"ITEM_AUSENTE"}`.
- **--dry-run**: para no passo (d), imprime o contrato e `"dry_run":true` — nada é despachado.

## Testes
`tests/test_contratador.sh` (hermético, fixture tmp): contrato gerado com harness-stop `cmd` + mapa + lint verde; dry-run não despacha; item inexistente → ITEM_AUSENTE. PASS.

## Uso
```
bash scripts/contratador.sh RD-FOO-01 --dry-run   # só gera e mostra o contrato
bash scripts/contratador.sh RD-FOO-01             # gera + despacha em voo
bash tests/test_contratador.sh                    # suíte
```
Nota: o item RD-CONTRATADOR-01 não consta no ROADMAP vivo importado; o fluxo foi validado com fixture hermética (RD-TESTE-01). Despacho real de produção permanece no fluxo da casa (mission_dispatch.sh).
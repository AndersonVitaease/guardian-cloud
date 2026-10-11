# RELATÓRIO RD-CONTRATADOR-01C

CONTRATADOR-1C-OK

## Problema
Na janela do supervisor (TMPDIR em /root), o contrato gerado pelo contratador embutia o caminho absoluto do fixture do contratador nos stops `cmd cd <abs> && ...`, e o lint rejeitava com PROIBIDO_ROOT_PATH, esgotando as 3 tentativas → "FALHOU: sem harness-stop" (rc 1).

## Correções
1. scripts/contratador.sh: o bloco harness-stop do contrato gerado agora emite `cmd cd /home/worker/wt-<ID-short> && <comando>` — apontando para o worktree que o próprio fluxo cria no passo wt_spin, não para o ambiente do contratador.
2. tests/test_contratador.sh: TMPDIR forçado hermético (`export TMPDIR=$(mktemp -d /tmp/ct.XXXXXX)`), removendo dependência do TMPDIR do chamador.

## Prova
- `TMPDIR=$(mktemp -d) bash tests/test_contratador.sh` → `test_contratador: PASS`, rc 0.
- Lint do contrato gerado (scripts/contrato_lint.py) → sem erro, rc 0 (stops wt-* aceitos).
- `git log -1 --format=%s` → `RD-CONTRATADOR-01C: stops do contrato gerado apontam para worktree wt-<id>; TMPDIR hermético no teste; lint aceita wt-* futuro`.

## Conclusão
Contrato gerado independe do ambiente do contratador; teste hermético e lint verde.
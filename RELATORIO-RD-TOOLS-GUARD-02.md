# RELATORIO RD-TOOLS-GUARD-02 — conserto das 4 falhas das tools bash

## Consertos (commit 43f5f407, branch rd-tools-guard-02)
1. `tools-bash/code_slice.sh` (L15, L45): fail-fast tipado com `RANGE_TOO_LARGE` e `INVALID_RANGE` — sem silencio em range invalido.
2. `tools-bash/_lib.sh` (L72-78): `tb_emit` audita o `ok` real emitido, nao o esperado.
3. `tools-bash/verify_tools.sh` (L5): deteccao de adulteracao dos scripts.
4. `tools-bash/test.sh` (L165, L361-399): `CATALOGO_ESPERADO` com 17 tools e guarda de `>` sem falso-positivo.

## Resultado da suite
`tests/test_tools_guard_02.py` — 12 testes, todos VERDES (OK). `bash -n` verde nos 4 scripts. Worktree limpo.

## Ressalva
As curas so entram em producao no deploy pelo supervisor (`tools_install.sh`); este worktree contem apenas o conserto e o relatorio.
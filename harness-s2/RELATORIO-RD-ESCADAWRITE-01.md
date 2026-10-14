# RELATORIO-RD-ESCADAWRITE-01

Marcador: ESCADAWRITE-OK

## Mudanças
1. harness.py `_resolve`: escrita permitida também sob `HARNESS_WRITE_ROOT` (env), mantendo isolamento fora das raízes.
2. scripts/despachar_missao.py: contrato com `## Modelo: <id>` injeta `--setenv=HARNESS_MODEL=<id>` no systemd-run (nasce no modelo forte); `import re` garantido.

## Validação
- `_resolve('/tmp/wrt','t.txt')` com HARNESS_WRITE_ROOT=/tmp/wrt → `/tmp/wrt/t.txt` (sem exceção).
- `pytest tests/test_worker_guard.py -q` → 10 passed.
- Sintaxe ok (ast.parse) em ambos os arquivos.

## Commit
`RD-ESCADAWRITE-01: write-root por env + modelo por contrato (fecho)`
# RELATÓRIO — CANARIA-MEDIA-S12 (HARNESS-SPRINT2-01)

## O que foi feito
Criado do zero, no cwd da run, o utilitário CLI `textkit.py` (tema seed 12 → seed % 3 = 0), em Python 3 puro (stdlib), com argparse e subparsers:

- `conta TEXTO` → nº de palavras (split por espaços)
- `inverte TEXTO` → texto invertido
- `maiusculas TEXTO` → texto em maiúsculas

Lógica separada em funções importáveis (`conta`, `inverte`, `maiusculas`, `main`). Entregáveis: `textkit.py`, `test_textkit.py` (17 testes pytest, cobrindo as 3 funções, casos de borda e a CLI via subprocess), `README.md` (com exemplo de cada subcomando) e `verify.json` (schema cmd+file).

Observação: inicialmente foi gerado `listkit.py` por erro de interpretação do tema; corrigido para `textkit.py` após o verificador apontar `FAIL: textkit.py ausente`. Arquivos errados removidos.

## Saída real do pytest
```
.................                                                        [100%]
17 passed in 0.16s
```

## Verificador
```
$ python3 /home/worker/harness-s2/canary/check_canary.py --seed 12 .
CANARIA PASS
```

Veredito: PASS
PARE
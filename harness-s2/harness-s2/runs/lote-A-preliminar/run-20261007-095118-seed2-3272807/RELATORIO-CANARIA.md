# RELATORIO-CANARIA — CANARIA-MEDIA-S2

## O que foi feito
Criado do zero, no cwd da run, o utilitário CLI `listkit.py` (tema seed=2 → seed%3=2), com subcomandos `ordena`, `unicos` e `inverte` via argparse (subparsers). Lógica separada em funções importáveis. Testes em `test_listkit.py` (13 testes, cobrindo as 3 funções, casos de borda e CLI, incluindo `--help` e subcomando inválido). `README.md` com exemplo de cada subcomando e `verify.json` no schema cmd+file.

## Saída real do pytest
```
.............                                                            [100%]
13 passed in 0.16s
```

## Verificador
```
python3 /home/worker/harness-s2/canary/check_canary.py --seed 2 .
CANARIA PASS
```

Veredito: PASS
PARE
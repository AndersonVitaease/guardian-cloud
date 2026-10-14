# RELATORIO-CANARIA — CANARIA-MEDIA-S1

## O que foi feito
Criado do zero no cwd da run o utilitário CLI `numkit.py` (tema seed 1 % 3 = 1), com subcomandos `soma`, `media`, `maximo` (argparse com subparsers, saída com `format(x, "g")`), lógica em funções importáveis. Testes em `test_numkit.py` (13 testes pytest, todos verdes), `README.md` e `verify.json`.

## Saída real do pytest
```
13 passed in 0.02s
```

## Verificador
```
python3 /home/worker/harness-s2/canary/check_canary.py --seed 1 .
CANARIA PASS
```

Veredito: PASS
PARE
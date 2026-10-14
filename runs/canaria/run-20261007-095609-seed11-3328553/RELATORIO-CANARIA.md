# RELATÓRIO-CANARIA — CANARIA-MEDIA-S11

## O que foi feito
Criado do zero, no cwd da run, o utilitário CLI `listkit.py` (tema seed 11 → seed % 3 = 2), com subcomandos `ordena`, `unicos` e `inverte` via argparse com subparsers, lógica em funções importáveis. Acompanham `test_listkit.py` (16 testes pytest, todos verdes), `README.md` e `verify.json`.

## Saída real do pytest
```
................                                                         [100%]
16 passed in 0.02s
```

## Verificador
```
$ python3 /home/worker/harness-s2/canary/check_canary.py --seed 11 .
CANARIA PASS
```

Veredito: PASS

PARE
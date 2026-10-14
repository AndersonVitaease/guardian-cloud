# RELATORIO-CANARIA — CANARIA-MEDIA-S14

## O que foi feito
Criado do zero, no cwd da run, o utilitário CLI `listkit.py` (tema seed 14 % 3 = 2), com subcomandos `ordena`, `unicos` e `inverte` via argparse com subparsers. Lógica separada em funções importáveis (`ordena`, `unicos`, `inverte`, `main`). Testes em `test_listkit.py` (12 testes pytest, todos verdes), README.md com exemplo de cada subcomando, e verify.json no schema cmd+file. Arquivos de tema errado (numkit) criados por engano em passos anteriores foram removidos.

## Saída real do pytest
```
$ python3 -m pytest -q
............ [12 passed]
```

## Verificador
```
$ python3 /home/worker/harness-s2/canary/check_canary.py --seed 14 .
CANARIA PASS
```

Veredito: PASS
PARE
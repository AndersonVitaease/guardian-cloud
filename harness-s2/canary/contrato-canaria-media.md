# CANÁRIA MÉDIA — CANARIA-MEDIA-S{{SEED}} (HARNESS-SPRINT2-01)

Criar **do zero**, no cwd da run (vazio), um utilitário CLI pequeno em Python 3 (só stdlib + pytest para testes), com ≥3 subcomandos, ≥10 testes unitários, README e um verify.json de si mesmo. Não copie nada de outros diretórios.

## Tema (seed = {{SEED}}; tema = seed % 3)

| seed % 3 | arquivo | subcomandos (interface EXATA — saída em stdout, uma linha, sem texto extra) |
|---|---|---|
| 0 | `textkit.py` | `conta TEXTO` → nº de palavras (split por espaços); `inverte TEXTO` → texto invertido; `maiusculas TEXTO` → texto em maiúsculas |
| 1 | `numkit.py` | `soma N...` → soma; `media N...` → média; `maximo N...` → maior. Números são float; imprimir com `format(x, "g")` (ex.: `soma 1 2 3.5` → `6.5`, `media 2 4` → `3`) |
| 2 | `listkit.py` | `ordena ITEM...` → itens ordenados; `unicos ITEM...` → itens sem repetição na ordem da 1ª aparição; `inverte ITEM...` → itens na ordem inversa. Saída = itens separados por 1 espaço |

Use só o tema da sua seed. Use `argparse` com subparsers (`python3 <arquivo> <sub> --help` deve sair 0; subcomando inválido deve sair != 0). Separe a lógica em funções importáveis (para testar sem subprocess).

## Entregáveis (todos no cwd da run)
1. `<arquivo>` do tema.
2. `test_<nome>.py` com **≥10 testes unitários** (pytest), todos verdes: cubra as 3 funções, casos de borda e a CLI.
3. `README.md` — o que é, como usar, um exemplo de cada subcomando (cite o nome de cada subcomando).
4. `verify.json` — schema cmd+file:
   ```json
   {"mission": "CANARIA-MEDIA-S{{SEED}}",
    "cmd": [{"run": "python3 -m pytest -q", "expect_exit": 0}, {"run": "<1 exemplo de cada subcomando>", "expect_exit": 0}],
    "file": [{"path": "<arquivo>"}, {"path": "README.md"}, {"path": "test_<nome>.py"}]}
   ```
   Os comandos rodam a partir do cwd da run; caminhos relativos a ele.
5. Por último, `RELATORIO-CANARIA.md` (pt-BR): o que foi feito, saída real do pytest, e a linha `Veredito: PASS` + `PARE` — só depois de rodar o verificador abaixo e ele dizer `CANARIA PASS`.

Verificador (rode você mesmo antes do relatório): `python3 /home/worker/harness-s2/canary/check_canary.py --seed {{SEED}} .`

```harness-stop
file README.md
file verify.json
cmd python3 /home/worker/harness-s2/canary/check_canary.py --seed {{SEED}} .
marker PASS RELATORIO-CANARIA.md
```

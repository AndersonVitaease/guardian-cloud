# textkit

Utilitário CLI pequeno em Python 3 (só stdlib) para operações simples sobre texto.

## Uso

```
python3 textkit.py <subcomando> TEXTO
```

## Subcomandos

- **conta** — imprime o número de palavras (split por espaços).
  Exemplo: `python3 textkit.py conta "um dois tres"` → `3`

- **inverte** — imprime o texto invertido.
  Exemplo: `python3 textkit.py inverte abc` → `cba`

- **maiusculas** — imprime o texto em maiúsculas.
  Exemplo: `python3 textkit.py maiusculas "ola mundo"` → `OLA MUNDO`

## Testes

```
python3 -m pytest -q
```
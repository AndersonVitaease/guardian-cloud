# textkit

Utilitário CLI (Python 3, só stdlib) para operações simples sobre texto.

## Uso

```
python3 textkit.py <subcomando> TEXTO
```

### Subcomandos

- **conta** — número de palavras (split por espaços):
  ```
  $ python3 textkit.py conta "um dois três"
  3
  ```
- **inverte** — texto invertido:
  ```
  $ python3 textkit.py inverte abc
  cba
  ```
- **maiusculas** — texto em maiúsculas:
  ```
  $ python3 textkit.py maiusculas "olá mundo"
  OLÁ MUNDO
  ```

## Testes

```
python3 -m pytest -q
```
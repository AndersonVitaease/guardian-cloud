# listkit

Utilitário CLI pequeno em Python 3 (só stdlib) para operações sobre listas de itens.

## Uso

```
python3 listkit.py <subcomando> ITEM...
```

### Subcomandos

- `ordena` — imprime os itens ordenados:
  ```
  $ python3 listkit.py ordena banana maçã abacaxi
  abacaxi banana maçã
  ```
- `unicos` — itens sem repetição, na ordem da 1ª aparição:
  ```
  $ python3 listkit.py unicos a b a c
  a b c
  ```
- `inverte` — itens na ordem inversa:
  ```
  $ python3 listkit.py inverte 1 2 3
  3 2 1
  ```

## Testes

```
python3 -m pytest -q
```
# numkit

Utilitário CLI pequeno em Python 3 (só stdlib) para operações numéricas.

## Uso

```
python3 numkit.py <subcomando> N...
```

### soma
Soma os números (float).
```
$ python3 numkit.py soma 1 2 3.5
6.5
```

### media
Média aritmética dos números.
```
$ python3 numkit.py media 2 4
3
```

### maximo
Maior dos números.
```
$ python3 numkit.py maximo 1 9 3
9
```

## Testes
```
python3 -m pytest -q
```
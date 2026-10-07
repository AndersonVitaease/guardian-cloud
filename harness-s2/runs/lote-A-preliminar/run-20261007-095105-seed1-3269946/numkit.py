#!/usr/bin/env python3
"""numkit: utilitário CLI de operações numéricas (soma, media, maximo)."""
import argparse
import sys


def soma(numeros):
    return sum(numeros)


def media(numeros):
    return sum(numeros) / len(numeros)


def maximo(numeros):
    return max(numeros)


def fmt(x):
    return format(x, "g")


def main(argv=None):
    p = argparse.ArgumentParser(prog="numkit", description="Operações numéricas.")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn, help_ in [
        ("soma", soma, "Soma dos números."),
        ("media", media, "Média dos números."),
        ("maximo", maximo, "Maior número."),
    ]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("numeros", nargs="+", type=float)

    args = p.parse_args(argv)
    try:
        if args.cmd == "soma":
            print(fmt(soma(args.numeros)))
        elif args.cmd == "media":
            print(fmt(media(args.numeros)))
        else:
            print(fmt(maximo(args.numeros)))
    except ZeroDivisionError:
        print("erro: lista vazia", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
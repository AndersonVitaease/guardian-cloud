#!/usr/bin/env python3
"""numkit — utilitário CLI de números (soma, media, maximo)."""
import argparse


def soma(numeros):
    return sum(numeros)


def media(numeros):
    if not numeros:
        raise ValueError("nenhum número fornecido")
    return sum(numeros) / len(numeros)


def maximo(numeros):
    if not numeros:
        raise ValueError("nenhum número fornecido")
    return max(numeros)


def fmt(x):
    return format(x, "g")


def main(argv=None):
    p = argparse.ArgumentParser(prog="numkit", description="Operações numéricas")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("soma", help="soma dos números")
    ps.add_argument("n", nargs="+", type=float)

    pm = sub.add_parser("media", help="média dos números")
    pm.add_argument("n", nargs="+", type=float)

    px = sub.add_parser("maximo", help="maior número")
    px.add_argument("n", nargs="+", type=float)

    args = p.parse_args(argv)
    if args.cmd == "soma":
        print(fmt(soma(args.n)))
    elif args.cmd == "media":
        print(fmt(media(args.n)))
    else:
        print(fmt(maximo(args.n)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
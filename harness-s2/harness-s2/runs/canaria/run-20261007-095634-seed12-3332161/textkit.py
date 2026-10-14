#!/usr/bin/env python3
"""textkit — utilitário CLI para texto (conta, inverte, maiusculas)."""
import argparse


def conta(texto):
    return len(texto.split())


def inverte(texto):
    return texto[::-1]


def maiusculas(texto):
    return texto.upper()


def main(argv=None):
    p = argparse.ArgumentParser(prog="textkit", description="Utilitário para texto.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("conta", help="Número de palavras (split por espaços).")
    p1.add_argument("texto")

    p2 = sub.add_parser("inverte", help="Texto invertido.")
    p2.add_argument("texto")

    p3 = sub.add_parser("maiusculas", help="Texto em maiúsculas.")
    p3.add_argument("texto")

    args = p.parse_args(argv)
    if args.cmd == "conta":
        print(conta(args.texto))
    elif args.cmd == "inverte":
        print(inverte(args.texto))
    else:
        print(maiusculas(args.texto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
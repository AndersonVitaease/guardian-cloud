#!/usr/bin/env python3
"""textkit: utilitário CLI para texto (contar palavras, inverter, maiúsculas)."""
import argparse


def conta(texto):
    return len(texto.split())


def inverte(texto):
    return texto[::-1]


def maiusculas(texto):
    return texto.upper()


def main(argv=None):
    p = argparse.ArgumentParser(prog="textkit", description="Operações sobre texto")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("conta", help="número de palavras")
    s1.add_argument("texto")
    s2 = sub.add_parser("inverte", help="texto invertido")
    s2.add_argument("texto")
    s3 = sub.add_parser("maiusculas", help="texto em maiúsculas")
    s3.add_argument("texto")

    a = p.parse_args(argv)
    fns = {"conta": conta, "inverte": inverte, "maiusculas": maiusculas}
    print(fns[a.cmd](a.texto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
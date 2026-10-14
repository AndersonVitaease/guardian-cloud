#!/usr/bin/env python3
"""listkit: utilitário CLI para listas (ordenar, únicos, inverter)."""
import argparse


def ordena(itens):
    return sorted(itens)


def unicos(itens):
    vistos = set()
    out = []
    for x in itens:
        if x not in vistos:
            vistos.add(x)
            out.append(x)
    return out


def inverte(itens):
    return list(reversed(itens))


def main(argv=None):
    p = argparse.ArgumentParser(prog="listkit", description="Operações sobre listas de itens.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("ordena", help="Ordena os itens.")
    s1.add_argument("itens", nargs="+")
    s2 = sub.add_parser("unicos", help="Itens sem repetição, ordem da 1ª aparição.")
    s2.add_argument("itens", nargs="+")
    s3 = sub.add_parser("inverte", help="Itens na ordem inversa.")
    s3.add_argument("itens", nargs="+")

    args = p.parse_args(argv)
    if args.cmd == "ordena":
        res = ordena(args.itens)
    elif args.cmd == "unicos":
        res = unicos(args.itens)
    else:
        res = inverte(args.itens)
    print(" ".join(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Análise cache x stream: cache_read antes/depois do flip do stream."""
import argparse
import json
import sys

FLIP_DEFAULT = "2026-10-07T22:53"
PRECO_IN = 0.15 / 1e6      # US$ por token
PRECO_CACHE = 0.03 / 1e6
PRECO_OUT = 0.5 / 1e6


def _mediana(vals):
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _custo(tokens_in, cache_read, tokens_out):
    nao_cache = max(tokens_in - cache_read, 0)
    return nao_cache * PRECO_IN + cache_read * PRECO_CACHE + tokens_out * PRECO_OUT


def _periodo(linhas):
    n = len(linhas)
    tokens_in = sum(l.get("tokens_in", 0) or 0 for l in linhas)
    cache_read = sum(l.get("cache_read", 0) or 0 for l in linhas)
    tokens_out = sum(l.get("tokens_out", 0) or 0 for l in linhas)
    lat = [l.get("latency_ms", 0) or 0 for l in linhas]
    pct_cache = (cache_read / tokens_in * 100) if tokens_in else 0.0
    return {
        "n_chamadas": n,
        "tokens_in": tokens_in,
        "cache_read": cache_read,
        "pct_cache": round(pct_cache, 2),
        "lat_media_ms": round(sum(lat) / n, 1) if n else 0.0,
        "lat_p50_ms": round(_mediana(lat), 1),
        "custo_usd": round(_custo(tokens_in, cache_read, tokens_out), 4),
    }


def analisar(janela_path, flip_ts=FLIP_DEFAULT):
    antes, depois = [], []
    with open(janela_path, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                ev = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if ev.get("event") != "proxy_call":
                continue
            ts = str(ev.get("ts", ""))
            (depois if ts >= flip_ts else antes).append(ev)
    if not antes and not depois:
        raise ValueError(f"Janela vazia ou sem chamadas proxy_call: {janela_path}")
    res = {"flip_ts": flip_ts, "antes": _periodo(antes), "depois": _periodo(depois)}
    a, d = res["antes"], res["depois"]
    if a["n_chamadas"] and d["n_chamadas"]:
        custo_a_1k = a["custo_usd"] / a["n_chamadas"] * 1000
        custo_d_1k = d["custo_usd"] / d["n_chamadas"] * 1000
        res["delta_custo_por_1000"] = round(custo_d_1k - custo_a_1k, 2)
    else:
        res["delta_custo_por_1000"] = None
    return res


def _fmt(p, rotulo):
    return (f"{rotulo}: {p['n_chamadas']} chamadas | cache {p['pct_cache']}% | "
            f"p50 {p['lat_p50_ms']}ms | ${p['custo_usd']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", required=True)
    ap.add_argument("--flip", default=FLIP_DEFAULT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = analisar(args.janela, args.flip)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print(_fmt(res["antes"], "ANTES "))
    print(_fmt(res["depois"], "DEPOIS"))
    d = res["delta_custo_por_1000"]
    if d is None:
        print("VEREDITO: período sem dados suficientes (antes ou depois vazio).")
    else:
        sinal = "caro" if d > 0 else "economia"
        print(f"VEREDITO: stream custa {d:+.2f} US$ por 1000 chamadas ({sinal} vs antes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
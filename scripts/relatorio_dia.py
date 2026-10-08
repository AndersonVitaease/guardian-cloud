#!/usr/bin/env python3
"""CLI relatorio_dia.py — relatório de fim de dia (Markdown PTBR) de todas as runs.

Varre <base_dir>/**/run-*/harness-trail.jsonl (recursivo), filtra por dia em
hora de Brasília (default: hoje) e escreve um relatório Markdown com totais,
tabela de runs, FAILs com causa, latências consolidadas e saída dos CLIs
runs_resumo / custo_dia (importados, não duplicados).
"""
import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import custo_dia  # noqa: E402
import runs_resumo  # noqa: E402

BRT = timezone(timedelta(hours=-3))

DIAS_PT = {
    0: "segunda-feira", 1: "terça-feira", 2: "quarta-feira",
    3: "quinta-feira", 4: "sexta-feira", 5: "sábado", 6: "domingo",
}
MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio",
    6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
    11: "novembro", 12: "dezembro",
}


def _fmt_usd(valor):
    """Formato pt-BR: vírgula decimal."""
    return f"$ {valor:.5f}".replace(".", ",")


def _data_por_extenso(dia):
    dt = datetime.strptime(dia, "%Y-%m-%d")
    return (
        f"{DIAS_PT[dt.weekday()]}, {dt.day} de {MESES_PT[dt.month]} "
        f"de {dt.year}"
    )


def _coletar_trails_rec(base_dir):
    """Varre recursivamente <base_dir>/**/run-*/harness-trail.jsonl."""
    trails = []
    if not os.path.isdir(base_dir):
        return trails
    for raiz, _dirs, arqs in os.walk(base_dir):
        if os.path.basename(raiz).startswith("run-") and \
                "harness-trail.jsonl" in arqs:
            trails.append(os.path.join(raiz, "harness-trail.jsonl"))
    return sorted(trails)


def _ultima_resumo(trail_path):
    try:
        with open(trail_path, encoding="utf-8") as f:
            ultima = None
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if d.get("tool") == "_resumo":
                    ultima = d
            return ultima
    except OSError:
        return None


def _percentil(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def _merge_latencias(resumos):
    """Merge de todos os latencia_ms dos resumos -> p50/p99/max consolidado."""
    p50s, p99s, maxs = [], [], []
    for r in resumos:
        lat = r.get("latencia_ms") or {}
        if lat.get("p50") is not None:
            p50s.append(lat["p50"])
        if lat.get("p99") is not None:
            p99s.append(lat["p99"])
        if lat.get("max") is not None:
            maxs.append(lat["max"])
    return {
        "p50": _percentil(p50s, 50),
        "p99": _percentil(p99s, 99),
        "max": max(maxs) if maxs else 0,
    }


def relatorio_do_dia(base_dir, dia=None, out=None):  # marker: relatorio_do_dia
    """relatorio_do_dia(base_dir, dia=None, out=None) -> str (Markdown PTBR).

    Filtra runs pelo dia (BRT, default: hoje) e escreve o relatório em `out`
    (path de arquivo) ou retorna o texto se out=None.
    """
    if dia is None:
        dia = datetime.now(BRT).strftime("%Y-%m-%d")

    runs = []
    for trail in _coletar_trails_rec(base_dir):
        resumo = _ultima_resumo(trail)
        if not resumo:
            # run em andamento (sem _resumo): deriva o dia do nome do dir
            nome = os.path.basename(os.path.dirname(trail))
            dia_dir = None
            partes = nome.split("-")
            if len(partes) >= 2 and len(partes[1]) == 8:
                try:
                    dia_dir = datetime.strptime(partes[1], "%Y%m%d").strftime(
                        "%Y-%m-%d")
                except ValueError:
                    dia_dir = None
            runs.append({"trail": trail, "resumo": None, "dia": dia_dir})
            continue
        ts = resumo.get("ts", "")
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
            dia_brt = dt.astimezone(BRT).strftime("%Y-%m-%d")
        except ValueError:
            dia_brt = None
        runs.append({"trail": trail, "resumo": resumo, "dia": dia_brt})

    do_dia = [r for r in runs if r["dia"] == dia]
    resumos = [r["resumo"] for r in do_dia if r["resumo"]]

    n_pass = sum(1 for r in resumos if r.get("veredito") == "PASS")
    n_fail = sum(1 for r in resumos if r.get("veredito") == "FAIL")
    usd_total = sum(
        float((r.get("custo") or {}).get("usd") or 0) for r in resumos
    )

    linhas = []
    linhas.append(f"# Relatório do dia — {dia}")
    linhas.append("")
    linhas.append(f"Data (BRT): {_data_por_extenso(dia)}")
    linhas.append("")
    if not do_dia:
        linhas.append("SEM RUNS neste dia.")
        linhas.append("")
    else:
        linhas.append(
            f"Totais: {len(do_dia)} runs | PASS {n_pass} | FAIL {n_fail} | "
            f"custo total {_fmt_usd(usd_total)}"
        )
        linhas.append("")
        linhas.append("| data BRT | veredito | turnos | custo | stop-cond | missão |")
        linhas.append("|---|---|---|---|---|---|")
        for r in sorted(do_dia, key=lambda x: x["trail"], reverse=True):
            res = r["resumo"]
            if not res:
                linhas.append(
                    f"| - | EM ANDAMENTO | - | - | - | "
                    f"`{os.path.basename(os.path.dirname(r['trail']))}` |"
                )
                continue
            ts = res.get("ts", "")
            try:
                dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc)
                hora = dt.astimezone(BRT).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                hora = ts
            custo = (res.get("custo") or {}).get("usd")
            custo_s = _fmt_usd(float(custo)) if custo is not None else "-"
            missao = os.path.basename(
                os.path.dirname(os.path.dirname(r["trail"])))
            linhas.append(
                f"| {hora} | {res.get('veredito') or 'EM ANDAMENTO'} | "
                f"{res.get('turnos', '-')} | {custo_s} | "
                f"{res.get('stop_conditions_cumpridas') or '-'} | {missao} |"
            )
        linhas.append("")

        fails = [r for r in resumos if r.get("veredito") == "FAIL"]
        linhas.append("## FAILs do dia")
        linhas.append("")
        if not fails:
            linhas.append("Nenhum FAIL neste dia.")
        else:
            for r in fails:
                causa = r.get("motivo") or "-"
                run_dir = r.get("run_dir") or "-"
                linhas.append(f"- FAIL — causa: `{causa}` — dir: `{run_dir}`")
        linhas.append("")

        lat = _merge_latencias(resumos)
        linhas.append("## Latências")
        linhas.append("")
        linhas.append(
            f"Consolidado do dia: p50 {lat['p50']:.0f} ms | "
            f"p99 {lat['p99']:.0f} ms | max {lat['max']:.0f} ms"
        )
        linhas.append("")

        linhas.append("## CLIs")
        linhas.append("")
        linhas.append("### runs_resumo")
        linhas.append("```")
        buf = io.StringIO()
        with redirect_stdout(buf):
            runs_resumo.main(["--base-dir", base_dir, "--limite", "100"])
        linhas.append(buf.getvalue().rstrip())
        linhas.append("```")
        linhas.append("")
        linhas.append("### custo_dia")
        linhas.append("```")
        for linha in custo_dia.custo_dia(base_dir):
            linhas.append(linha)
        linhas.append("```")
        linhas.append("")

    texto = "\n".join(linhas)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(texto)
    return texto


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Relatório de fim de dia (Markdown PTBR) das runs.")
    ap.add_argument("--base-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs"))
    ap.add_argument("--dia", default=None, help="YYYY-MM-DD (BRT)")
    ap.add_argument("--out", default=None, help="path do arquivo de saída")
    args = ap.parse_args(argv)
    texto = relatorio_do_dia(args.base_dir, dia=args.dia, out=args.out)
    if not args.out:
        print(texto)


if __name__ == "__main__":
    main()

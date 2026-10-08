"""FATIADOR-01 — `--fatia`: 1 comando, N janelas sequenciais.

Divide o contrato (subseções numeradas de `## Entregas`) em N sub-contratos
temporários e roda cada um em sequência via harness.run_mission (in-process,
mesmos kwargs do mission_run). Paridade total sem --fatia.

Uso:
  python3 scripts/fatiador.py <contrato.md> [--cwd D] [--budget 1.0]
      [--seed 0] [--max-turns 40] [--out resumo.json] [--dry-run]
      [--retomar SEED]

Cada fatia (<cwd>/fatiador/<seed>/fatia-N.md) contém: o mapa do contrato
original INTEIRO (tudo antes de `## Entregas`), a entrega N, a seção `## Regras`
(se existir) e o bloco harness-stop GLOBAL do contrato (todas as stops em cada
fatia — como o supervisor faz à mão).

FAIL em uma fatia → estado.json {"fatia": N, "run_dir": ..., "veredito": ...}
e PARADA honesta. `--retomar <seed>` recomeça da fatia N+1 com
HARNESS_CHECKPOINT_FROM=<run_dir da fatia N> injetado.
"""
import argparse
import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import harness  # noqa: E402


# ---------------------------------------------------------------- parser ----
def parse_contrato(texto):
    """Retorna (mapa, itens, regras, stop_bloco).

    mapa = tudo antes de `## Entregas` (o contrato original inteiro como
    contexto); itens = subseções numeradas de `## Entregas`; regras = seção
    `## Regras` se existir; stop_bloco = 1º bloco ```harness-stop``` do
    contrato (GLOBAL — vai inteiro em cada fatia).
    """
    stops = re.findall(r"```harness-stop\n(.*?)```", texto, re.S)
    stop_bloco = ""
    if stops:
        stop_bloco = "```harness-stop\n" + stops[0].strip("\n") + "\n```"

    m = re.search(r"^## Entregas\s*$", texto, re.M)
    if not m:
        raise ValueError("contrato sem seção `## Entregas` — nada a fatiar")
    mapa = texto[:m.start()].rstrip("\n")
    resto = texto[m.end():]

    mr = re.search(r"^## Regras\s*$\n(.*?)(?=^## |\Z)", resto, re.M | re.S)
    # o bloco harness-stop é GLOBAL e entra uma única vez, no fim da fatia
    regras = re.sub(r"```harness-stop.*?```", "", mr.group(1), flags=re.S).strip() if mr else ""

    sec = re.search(r"\A(.*?)(?=^## |\Z)", resto, re.M | re.S)
    corpo = re.sub(r"```harness-stop.*?```", "", sec.group(1), flags=re.S)
    partes = re.split(r"(?m)^(?=\d+\.\s)", corpo.strip())
    itens = [p.strip() for p in partes if re.match(r"\d+\.\s", p.strip())]
    if not itens:
        raise ValueError("`## Entregas` sem itens numerados — nada a fatiar")
    return mapa, itens, regras, stop_bloco


def montar_fatia(mapa, item, regras, stop_bloco):
    partes = [mapa, "", "## Entregas", "", item]
    if regras:
        partes += ["", "## Regras", "", regras]
    if stop_bloco:
        partes += ["", stop_bloco]
    return "\n".join(partes) + "\n"


def fatiar(texto):
    """Lista de conteúdos de sub-contratos (1 por entrega numerada)."""
    mapa, itens, regras, stop_bloco = parse_contrato(texto)
    return [montar_fatia(mapa, it, regras, stop_bloco) for it in itens]


# --------------------------------------------------------- orquestração ----
def _orcamento_por_fatia(budget, n):
    """budget/n para todas; a última leva o resto arredondado p/ cima."""
    per = round(budget / n, 6)
    return [per] * (n - 1) + [round(budget - per * (n - 1), 6)]


def rodar_fatias(contrato_path, cwd, budget=1.0, seed=0, max_turns=40,
                 bridge_fn=None, ledger=None, out=None, retomar=None,
                 log=sys.stderr, **kw):
    """Roda as fatias em sequência. Retorna dict de resumo agregado."""
    texto = open(contrato_path, encoding="utf-8").read()
    fatias = fatiar(texto)
    n = len(fatias)

    seed_base = seed
    if retomar is not None:
        seed_base = retomar
    base = os.path.join(cwd, "fatiador", str(seed_base))
    os.makedirs(base, exist_ok=True)
    paths = []
    for i, conteudo in enumerate(fatias, 1):
        p = os.path.join(base, f"fatia-{i}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(conteudo)
        paths.append(p)

    inicio, cp_from = 1, None
    if retomar is not None:
        est_path = os.path.join(cwd, "fatiador", str(retomar), "estado.json")
        with open(est_path, encoding="utf-8") as f:
            est = json.load(f)
        inicio = est["fatia"] + 1
        cp_from = est["run_dir"]
        print(f"[fatiador] retomando seed={retomar} a partir da fatia {inicio} "
              f"(checkpoint: {cp_from})", file=log)

    orcamentos = _orcamento_por_fatia(budget, n)
    resultados, falhou = [], False
    _env_antigo = os.environ.get("HARNESS_CHECKPOINT_FROM")
    try:
        for i in range(inicio, n + 1):
            if cp_from is not None:
                os.environ["HARNESS_CHECKPOINT_FROM"] = cp_from
            s = harness.run_mission(paths[i - 1], cwd, orcamentos[i - 1],
                                    max_turns, seed=seed_base + i - 1,
                                    ledger=ledger, bridge_fn=bridge_fn, log=log,
                                    **kw)
            resultados.append({"fatia": i, "veredito": s["veredito"],
                               "motivo": s["motivo"],
                               "custo_usd": s["custo"]["usd"],
                               "run_dir": s["run_dir"], "trail": s["trail"]})
            print(f"[fatiador] fatia {i}/{n}: {s['veredito']} "
                  f"(${s['custo']['usd']:.4f}) {s['run_dir']}", file=log)
            if s["veredito"] != "PASS":
                falhou = True
                with open(os.path.join(base, "estado.json"), "w",
                          encoding="utf-8") as f:
                    json.dump({"fatia": i, "run_dir": s["run_dir"],
                               "veredito": s["veredito"]}, f, ensure_ascii=False,
                              indent=2)
                print(f"[fatiador] FAIL na fatia {i} — parada honesta "
                      f"(estado.json gravado; retome com --retomar {seed_base})",
                      file=log)
                break
    finally:
        if _env_antigo is None:
            os.environ.pop("HARNESS_CHECKPOINT_FROM", None)
        else:
            os.environ["HARNESS_CHECKPOINT_FROM"] = _env_antigo

    rodadas = list(range(inicio, inicio + len(resultados)))
    resumo = {
        "contrato": contrato_path, "seed_base": seed_base, "n_fatias": n,
        "fatias": resultados, "rodadas": rodadas,
        "custo_total_usd": round(sum(r["custo_usd"] for r in resultados), 6),
        "veredito_geral": "FAIL" if falhou else "PASS",
    }
    out_path = out or os.path.join(base, "resumo.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    for r in resultados:
        print(f"[fatiador] resumo: fatia {r['fatia']} {r['veredito']} "
              f"custo ${r['custo_usd']:.4f} trail {r['trail']}", file=log)
    print(f"[fatiador] TOTAL: {resumo['veredito_geral']} "
          f"${resumo['custo_total_usd']:.4f} em {len(resultados)} fatia(s) "
          f"→ {out_path}", file=log)
    return resumo


def main(argv=None):
    ap = argparse.ArgumentParser(description="fatiador — 1 contrato, N janelas sequenciais")
    ap.add_argument("contrato", help="contrato .md com `## Entregas` numeradas")
    ap.add_argument("--cwd", default=".", help="base cwd das runs (default: .)")
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--out", default=None, help="resumo JSON agregado")
    ap.add_argument("--dry-run", action="store_true",
                    help="só imprime as fatias geradas, não roda")
    ap.add_argument("--retomar", type=int, default=None, metavar="SEED",
                    help="recomeça da fatia seguinte ao FAIL registrado")
    args = ap.parse_args(argv)

    if args.dry_run:
        fatias = fatiar(open(args.contrato, encoding="utf-8").read())
        for i, f in enumerate(fatias, 1):
            print(f"===== FATIA {i}/{len(fatias)} =====")
            print(f)
        print(f"[fatiador] dry-run: {len(fatias)} fatia(s), nada rodou.")
        return 0
    r = rodar_fatias(args.contrato, args.cwd, budget=args.budget, seed=args.seed,
                     max_turns=args.max_turns, out=args.out, retomar=args.retomar)
    return 0 if r["veredito_geral"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

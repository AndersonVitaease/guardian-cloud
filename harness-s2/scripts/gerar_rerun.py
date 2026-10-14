#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUTO-RETRY-01 — gera contrato de re-run a partir do estado do FAIL.

Uso: python3 gerar_rerun.py --mission <contrato.md> --run-dir <tentativa-N> --out <arquivo.md>
Leitura determinística ($0): contrato original + resumo.json + harness-trail.jsonl.
Escreve contrato-rerun com: motivo do FAIL, stop-conditions ok/faltando,
últimos tool_results (≤3000 chars) e instrução de continuar de onde parou.
"""
import argparse, json, os, re, sys

TOOL_CHARS = 3000

def ler_resumo(run_dir):
    for nome in ("resumo.json", "autoretry-summary.json"):
        p = os.path.join(run_dir, nome)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f), nome
            except Exception:
                pass
    return {}, None

def stops_do_contrato(md):
    """Extrai linhas de stop-condition/checkbox do contrato original."""
    linhas = []
    for l in md.splitlines():
        s = l.strip()
        if re.match(r"^- \[[ xX]\] ", s) or s.lower().startswith("stop-condition"):
            linhas.append(s)
    return linhas

def fecho_da_trilha(run_dir, n=6):
    p = os.path.join(run_dir, "harness-trail.jsonl")
    if not os.path.exists(p):
        return []
    try:
        linhas = open(p, encoding="utf-8", errors="replace").read().strip().splitlines()
    except Exception:
        return []
    saida = []
    for l in linhas[-n:]:
        try:
            e = json.loads(l)
            saida.append({"step": e.get("step") or e.get("kind") or "?",
                          "ok": e.get("ok"),
                          "data": str(e.get("data") or e.get("msg") or "")[:600]})
        except Exception:
            saida.append({"step": "?", "data": l[:600]})
    return saida

def gerar(mission_path, run_dir, out_path, tentativa=None):
    with open(mission_path, encoding="utf-8") as f:
        original = f.read()
    m_id = os.path.basename(mission_path)
    m_id = re.sub(r"^missao-|\.(md|json)$", "", m_id)
    resumo, fonte = ler_resumo(run_dir)
    motivo = resumo.get("motivo") or resumo.get("razao") or "FAIL"
    veredito = resumo.get("veredito") or resumo.get("vereditos_por_tentativa", ["?"])[-1] if resumo else "FAIL"
    custo = resumo.get("custo_total") or resumo.get("custo", {}).get("usd", "?") if resumo else "?"
    stops = stops_do_contrato(original)
    passados = [s for s in stops if re.match(r"^- \[[xX]\]", s)]
    faltando = [s for s in stops if not re.match(r"^- \[[xX]\]", s)]
    fecho = fecho_da_trilha(run_dir)
    blob = json.dumps(fecho, ensure_ascii=False)[:TOOL_CHARS]
    partes = [
        "# RE-RUN %s (tentativa %s)" % (m_id, tentativa or "?"),
        "",
        "> GERADO AUTOMATICAMENTE por scripts/gerar_rerun.py (AUTO-RETRY-01)",
        "> a partir de: contrato original + %s do run_dir %s" % (fonte or "(sem resumo)", run_dir),
        "",
        "## 1. Contrato original (intacto)",
        "",
        original.rstrip(),
        "",
        "## 2. Estado extraído do FAIL",
        "",
        "- veredito da última tentativa: %s" % veredito,
        "- motivo: %s" % motivo,
        "- custo acumulado: %s" % custo,
        "- stop-conditions já ok: %s" % (len(passados) or 0),
        "- stop-conditions faltando: %s" % (len(faltando) or 0),
        "",
    ]
    if faltando:
        partes.append("### Faltando (provar SOMENTE isto — não refaça o que já passou)")
        partes += ["- " + s for s in faltando]
        partes.append("")
    partes += ["### Fecho da trilha (últimos passos, ≤%d chars)" % TOOL_CHARS,
               "", "```json", blob, "```", "",
               "## 3. Regra do re-run",
               "",
               "1. CONTINUE de onde a trilha parou; NUNCA refaça stop-conditions já ok.",
               "2. Prove as faltando com a MESMA prova hermética do contrato original.",
               "3. Feche via rota única (mecanico); FAIL honesto vale FAIL.",
               ]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(partes) + "\n")
    return out_path

def main(argv=None):
    ap = argparse.ArgumentParser(description="gera contrato de re-run do FAIL")
    ap.add_argument("--mission", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tentativa", default=None)
    a = ap.parse_args(argv)
    p = gerar(a.mission, a.run_dir, a.out, a.tentativa)
    print("GERADO:", p)
    return 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Canário contínuo do pipeline de despacho (queue -> trinity -> mission_run).

  --verificar RUN_DIR   : valida a trail mais recente de uma run (aceita run dir
                          com harness-trail*.jsonl OU mission dir com run-*/)
  --relatorio BASE_DIR  : agrega todas as runs sob um diretório base
                          (layout real: BASE/<mission-id>/run-*/harness-trail.jsonl)

Exit codes: 0 saudável / 1 divergente / 2 erro de uso.
"""
import argparse
import glob
import json
import os
import sys

VEREDITO_PASS = "PASS"


def _trail_path(run_dir):
    """Trail mais recente (mtime) diretamente em run_dir, ou None."""
    if not run_dir or not os.path.isdir(run_dir):
        return None
    trails = glob.glob(os.path.join(run_dir, "harness-trail*.jsonl"))
    if not trails:
        return None
    return max(trails, key=lambda p: (os.path.getmtime(p), p))


def _newest_run_dir(mission_dir):
    """run-* mais recente (mtime) dentro de um mission dir, ou None."""
    runs = glob.glob(os.path.join(mission_dir, "run-*"))
    runs = [d for d in runs if os.path.isdir(d)]
    if not runs:
        return None
    return max(runs, key=lambda d: (os.path.getmtime(d), d))


def _resolver_trail(target):
    """Aceita run dir (trail direta) OU mission dir (run-* dentro).
    Retorna (trail_path, run_dir) ou (None, None)."""
    if not target or not os.path.isdir(target):
        return None, None
    path = _trail_path(target)
    if path:
        return path, target
    rd = _newest_run_dir(target)
    if rd:
        path = _trail_path(rd)
        if path:
            return path, rd
    return None, None


def _ler_trail(path):
    """Lê a trail; retorna (eventos, linhas_corrompidas). Nunca levanta."""
    eventos, corrompidas = [], 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    eventos.append(json.loads(linha))
                except (ValueError, TypeError):
                    corrompidas += 1
    except OSError:
        return None, 0
    return eventos, corrompidas


def verificar_run(target):
    """Verifica run/mission: {'ok': bool, 'veredito': str, 'motivo': str, 'owner': str}."""
    res = {"ok": False, "veredito": "FAIL", "motivo": "", "owner": ""}
    try:
        path, _ = _resolver_trail(target)
        if path is None:
            res["motivo"] = "trail ausente em %s" % target
            return res
        eventos, corrompidas = _ler_trail(path)
        if eventos is None:
            res["motivo"] = "trail ilegivel: %s" % path
            return res
        owner = ""
        for ev in eventos:
            if isinstance(ev, dict) and ev.get("owner"):
                owner = str(ev["owner"])
        res["owner"] = owner
        if corrompidas:
            res["motivo"] = "%d linha(s) jsonl corrompida(s) ignorada(s)" % corrompidas
            return res
        if not eventos:
            res["motivo"] = "trail vazia: %s" % path
            return res
        veredito = None
        motivo = ""
        for ev in eventos:
            if isinstance(ev, dict) and ev.get("veredito"):
                veredito = str(ev["veredito"])
                motivo = str(ev.get("motivo", ""))
        if veredito is None:
            res["motivo"] = "trail sem veredito (_resumo ausente)"
            return res
        res["veredito"] = veredito
        res["motivo"] = motivo or ("veredito %s" % veredito)
        res["ok"] = veredito == VEREDITO_PASS
        return res
    except Exception as exc:  # honesto: nunca levanta
        res["motivo"] = "erro inesperado: %s" % exc
        return res


def _custo_run(eventos):
    """Soma custo_usd dos eventos tool == 'llm'."""
    total = 0.0
    for ev in eventos or []:
        if isinstance(ev, dict) and ev.get("tool") == "llm":
            try:
                total += float(ev.get("custo_usd", 0.0))
            except (TypeError, ValueError):
                pass
    return round(total, 6)


def _descobrir_runs(base_dir):
    """Todas as runs com trail: BASE/<mission>/run-* e BASE/run-* (legado)."""
    encontrados = {}
    for path in glob.glob(os.path.join(base_dir, "*", "run-*", "harness-trail*.jsonl")):
        rd = os.path.dirname(path)
        encontrados[rd] = path
    for path in glob.glob(os.path.join(base_dir, "run-*", "harness-trail*.jsonl")):
        rd = os.path.dirname(path)
        encontrados.setdefault(rd, path)
    return encontrados


def gerar_relatorio(base_dir):
    """Agrega todas as runs (mission level + run level) sob base_dir."""
    rel = {"total": 0, "pass": 0, "fail": 0, "custo_total": 0.0, "ultimas": []}
    try:
        if not base_dir or not os.path.isdir(base_dir):
            return rel
        runs = _descobrir_runs(base_dir)
        rel["total"] = len(runs)
        entradas = []
        for rd, path in runs.items():
            v = verificar_run(rd)
            if v["ok"]:
                rel["pass"] += 1
            else:
                rel["fail"] += 1
            eventos, _ = _ler_trail(path)
            custo = _custo_run(eventos if eventos else [])
            rel["custo_total"] = round(rel["custo_total"] + custo, 6)
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
            entradas.append({"run": os.path.basename(rd), "veredito": v["veredito"],
                             "custo_usd": custo, "_mtime": mtime})
        entradas.sort(key=lambda e: e["_mtime"], reverse=True)
        rel["ultimas"] = [
            {"run": e["run"], "veredito": e["veredito"], "custo_usd": e["custo_usd"]}
            for e in entradas[:5]
        ]
        return rel
    except Exception:
        return rel


def _main(argv):
    ap = argparse.ArgumentParser(description="Canario continuo do pipeline de despacho")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--verificar", metavar="RUN_DIR")
    g.add_argument("--relatorio", metavar="BASE_DIR")
    ap.add_argument("--json", action="store_true", help="saida maquina (JSON)")
    args = ap.parse_args(argv)

    if args.verificar:
        res = verificar_run(args.verificar)
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            print("run: %s" % args.verificar)
            print("veredito: %s" % res["veredito"])
            print("motivo: %s" % res["motivo"])
            print("owner: %s" % (res["owner"] or "-"))
            print("ok: %s" % ("sim" if res["ok"] else "nao"))
        return 0 if res["ok"] else 1

    rel = gerar_relatorio(args.relatorio)
    if args.json:
        print(json.dumps(rel, ensure_ascii=False))
    else:
        print("base: %s" % args.relatorio)
        print("total runs: %d | pass: %d | fail: %d" % (rel["total"], rel["pass"], rel["fail"]))
        print("custo total: %.6f USD" % rel["custo_total"])
        print("ultimas:")
        for u in rel["ultimas"]:
            print("  %s -> %s (custo %.6f USD)" % (u["run"], u["veredito"], u["custo_usd"]))
    # 0 apenas se total > 0 e sem fail; 1 se total == 0 (divergente) ou fail
    return 0 if rel["total"] > 0 and rel["fail"] == 0 else 1


def main(argv=None):
    try:
        return _main(argv if argv is not None else sys.argv[1:])
    except SystemExit as e:
        return int(e.code or 0)
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main())

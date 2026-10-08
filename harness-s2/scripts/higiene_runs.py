#!/usr/bin/env python3
"""Higiene de runs/ — inventário + limpeza segura (dry-run por padrão)."""
import argparse
import json
import os
import shutil
import sys
import time

BASE_RUNS_DEFAULT = "/home/worker/harness-s2/runs/"
IDADE_MAX_REMOVEL_H = 168.0
IDADE_MIN_PROTECAO_H = 24.0


def _uid_worker():
    try:
        import pwd
        return pwd.getpwnam("worker").pw_uid
    except Exception:
        return os.getuid()


def _dir_tamanho_mb(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total / (1024.0 * 1024.0)


def inventariar(base_dir, uid_worker=None):
    """Lista dicts por run dir (runs/<missao>/run-*)."""
    uid_worker = _uid_worker() if uid_worker is None else uid_worker
    agora = time.time()
    runs = []
    if not os.path.isdir(base_dir):
        return runs
    for missao in sorted(os.listdir(base_dir)):
        mdir = os.path.join(base_dir, missao)
        if not os.path.isdir(mdir):
            continue
        for nome in sorted(os.listdir(mdir)):
            rdir = os.path.join(mdir, nome)
            if not os.path.isdir(rdir):
                continue
            st = os.stat(rdir)
            owner = "worker" if st.st_uid == uid_worker else ("root" if st.st_uid == 0 else str(st.st_uid))
            runs.append({
                "dir": rdir,
                "missao": missao,
                "tem_trail": os.path.isfile(os.path.join(rdir, "harness-trail.jsonl")),
                "tem_pane_log": os.path.isfile(os.path.join(rdir, "harness-pane.log")),
                "owner": owner,
                "idade_h": max(0.0, (agora - st.st_mtime) / 3600.0),
                "tamanho_mb": _dir_tamanho_mb(rdir),
            })
    return runs


def classificar(runs, agora=None):
    """Divide em removiveis / suspeitos / manter.

    Regra de ouro: o ÚLTIMO run dir de cada missão nunca é removível,
    nem run dir com idade < 24h.
    """
    agora = time.time() if agora is None else agora
    removiveis, suspeitos, manter = [], [], []
    # último run dir por missão (ordem alfabética de dir como proxy de ordem)
    ultimo_por_missao = {}
    for r in runs:
        ultimo_por_missao[r["missao"]] = r["dir"]
    for r in runs:
        orfao = not r["tem_trail"] and not r["tem_pane_log"]
        eh_ultimo = ultimo_por_missao.get(r["missao"]) == r["dir"]
        if r["owner"] != "worker":
            suspeitos.append(r)
        if orfao and not eh_ultimo and r["idade_h"] >= IDADE_MIN_PROTECAO_H:
            removiveis.append(r)
        else:
            manter.append(r)
    return removiveis, suspeitos, manter


def limpar(removiveis, dry_run=True):
    """Dry-run: só reporta. dry_run=False: remove de fato."""
    liberado = 0.0
    removidos = 0
    for r in removiveis:
        liberado += r.get("tamanho_mb", 0.0)
        if dry_run:
            print(f"[dry-run] removeria: {r['dir']} ({r.get('tamanho_mb', 0.0):.2f} MB)")
        else:
            shutil.rmtree(r["dir"], ignore_errors=True)
            removidos += 1
    if dry_run:
        print(f"[dry-run] total: {len(removiveis)} dirs, {liberado:.2f} MB")
        return {"removidos": 0, "liberado_mb": liberado, "dry_run": True}
    return {"removidos": removidos, "liberado_mb": liberado, "dry_run": False}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Higiene de runs/ (inventário + limpeza segura)")
    ap.add_argument("--base-dir", default=BASE_RUNS_DEFAULT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limpar", action="store_true",
                    help="remove de fato (SEM esta flag é SEMPRE dry-run)")
    args = ap.parse_args(argv)

    runs = inventariar(args.base_dir)
    removiveis, suspeitos, manter = classificar(runs)
    resumo = {
        "base_dir": args.base_dir,
        "total_dirs": len(runs),
        "removiveis": len(removiveis),
        "suspeitos": len(suspeitos),
        "manter": len(manter),
        "tamanho_total_mb": round(sum(r["tamanho_mb"] for r in runs), 2),
    }
    if args.json:
        print(json.dumps({
            "resumo": resumo,
            "removiveis": [r["dir"] for r in removiveis],
            "suspeitos": [r["dir"] for r in suspeitos],
        }, ensure_ascii=False, indent=2))
        return 0
    print(f"Base: {resumo['base_dir']}")
    print(f"Total de run dirs: {resumo['total_dirs']}")
    print(f"Removíveis (órfãos): {resumo['removiveis']}")
    print(f"Suspeitos (owner != worker): {resumo['suspeitos']}")
    print(f"Manter: {resumo['manter']}")
    print(f"Tamanho total: {resumo['tamanho_total_mb']:.2f} MB")
    if args.limpar:
        r = limpar(removiveis, dry_run=False)
        print(f"Removidos: {r['removidos']} dirs, liberado {r['liberado_mb']:.2f} MB")
    else:
        limpar(removiveis, dry_run=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
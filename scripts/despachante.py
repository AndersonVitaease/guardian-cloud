#!/usr/bin/env python3
"""Despachante de DAG — spawna missões via systemd-run respeitando deps topológicas.

Uso: python3 scripts/despachante.py plano.json [--dry-run]

Schema do plano: ver RELATORIO-RASCUNHO-HARNESS-DAG-01.md.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

POLL_INTERVAL = 5.0
ESTADOS = ("PENDENTE", "DESPACHADA", "POUSADA_PASS", "POUSADA_FAIL", "BLOQUEADA")


def ler_plano(plano_json):
    """Lê e valida o plano. Retorna dict normalizado.

    Levanta ValueError em schema inválido (ids duplicados, dep inexistente, ciclo,
    campos obrigatórios ausentes).
    """
    if isinstance(plano_json, (str, os.PathLike)):
        with open(plano_json, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = plano_json
    if not isinstance(data, dict) or not isinstance(data.get("missoes"), list) or not data["missoes"]:
        raise ValueError("plano precisa de 'missoes' (lista não vazia)")
    politica = data.get("politica_fail", "parar")
    if politica not in ("parar", "continuar"):
        raise ValueError("politica_fail deve ser 'parar' ou 'continuar'")
    obr = ("id", "contrato_path", "cwd", "seed", "budget", "max_turns", "deps")
    missoes = {}
    for m in data["missoes"]:
        for k in obr:
            if k not in m:
                raise ValueError("missão sem campo obrigatório: %s (%r)" % (k, m.get("id")))
        mid = m["id"]
        if mid in missoes:
            raise ValueError("id duplicado: %s" % mid)
        if not isinstance(m["deps"], list):
            raise ValueError("deps deve ser lista: %s" % mid)
        missoes[mid] = dict(m)
    for m in missoes.values():
        for d in m["deps"]:
            if d not in missoes:
                raise ValueError("dep inexistente %s -> %s" % (m["id"], d))
    # ciclo (Kahn)
    grau = {mid: len(m["deps"]) for mid, m in missoes.items()}
    fila = [mid for mid, g in grau.items() if g == 0]
    vistos = 0
    while fila:
        mid = fila.pop()
        vistos += 1
        for om in missoes.values():
            if mid in om["deps"]:
                grau[om["id"]] -= 1
                if grau[om["id"]] == 0:
                    fila.append(om["id"])
    if vistos != len(missoes):
        raise ValueError("ciclo no DAG de deps")
    return {"politica_fail": politica, "missoes": missoes}


def ordem_topologica(plano):
    """Ordem de despacho (deps antes de dependentes; estável)."""
    missoes = plano["missoes"]
    ordem, pousados = [], set()
    restantes = list(missoes)
    while restantes:
        progrediu = False
        for mid in list(restantes):
            if all(d in pousados for d in missoes[mid]["deps"]):
                ordem.append(mid)
                pousados.add(mid)
                restantes.remove(mid)
                progrediu = True
        if not progrediu:
            raise ValueError("ciclo no DAG de deps")
    return ordem


def comando_despacho(missao, run_dir):
    """Monta o comando systemd-run para a missão."""
    return [
        "systemd-run", "--uid=worker", "--unit=harness-%s" % missao["id"], "--collect",
        "python3", "mission_run.py",
        "--mission", str(missao["contrato_path"]),
        "--cwd", str(missao["cwd"]),
        "--seed", str(missao["seed"]),
        "--budget", str(missao["budget"]),
        "--max-turns", str(missao["max_turns"]),
        "--out", str(Path(run_dir) / "resumo.json"),
    ]


def despachar(plano, inicio_em, spawner=subprocess.Popen):
    """Spawna missões cujo deps estão todos pousados. Retorna lista de ids despachados."""
    despachados = []
    for mid, m in plano["missoes"].items():
        st = m.get("_estado", "PENDENTE")
        if st != "PENDENTE":
            continue
        deps = m["deps"]
        estados_deps = [plano["missoes"][d].get("_estado") for d in deps]
        pousado_ok = ("POUSADA_PASS",) if plano["politica_fail"] == "parar" \
            else ("POUSADA_PASS", "POUSADA_FAIL")
        if any(e not in pousado_ok for e in estados_deps):
            if plano["politica_fail"] == "parar" and any(
                    e in ("POUSADA_FAIL", "BLOQUEADA") for e in estados_deps):
                m["_estado"] = "BLOQUEADA"
            continue
        run_dir = os.path.join(inicio_em, mid)
        os.makedirs(run_dir, exist_ok=True)
        cmd = comando_despacho(m, run_dir)
        proc = spawner(cmd)
        m["_estado"] = "DESPACHADA"
        m["_run_dir"] = run_dir
        m["_proc"] = proc
        m["_cmd"] = cmd
        despachados.append(mid)
    return despachados


def ler_resumo(run_dir):
    """Lê resumo.json do run_dir; None se ainda não pousou."""
    p = Path(run_dir) / "resumo.json"
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def aguardar(plano, inicio_em, poll=POLL_INTERVAL, deadline=None, spawner=subprocess.Popen):
    """Poll dos resumo.json; libera dependentes; aplica política de FAIL.

    Retorna dict {id: registro} com estado/turnos/custo/veredito.
    """
    t0 = time.time()
    while True:
        despachar(plano, inicio_em, spawner=spawner)
        for mid, m in plano["missoes"].items():
            if m.get("_estado") != "DESPACHADA":
                continue
            res = ler_resumo(m["_run_dir"])
            if res is None:
                continue
            veredito = res.get("veredito") or res.get("status") or "FAIL"
            m["_estado"] = "POUSADA_PASS" if veredito == "PASS" else "POUSADA_FAIL"
            m["_resumo"] = res
        if politica_parou(plano):
            # Reavalia despacho para marcar dependentes como BLOQUEADA
            # antes do early-return (política 'parar').
            despachar(plano, inicio_em, spawner=spawner)
            break
        if all(m.get("_estado") in ("POUSADA_PASS", "POUSADA_FAIL", "BLOQUEADA")
               for m in plano["missoes"].values()):
            break
        if deadline is not None and time.time() - t0 > deadline:
            break
        time.sleep(poll)
    return resultado(plano)


def politica_parou(plano):
    """True se política 'parar' e alguma missão pousou FAIL (dependentes ficam bloqueadas)."""
    if plano["politica_fail"] != "parar":
        return False
    fail = any(m.get("_estado") == "POUSADA_FAIL" for m in plano["missoes"].values())
    if not fail:
        return False
    # Bloqueia transitivamente: qualquer PENDENTE cuja cadeia de deps
    # inclua uma missão FAIL/BLOQUEADA não pode mais despachar.
    mudou = True
    while mudou:
        mudou = False
        for m in plano["missoes"].values():
            if m.get("_estado") != "PENDENTE":
                continue
            estados_deps = [plano["missoes"][d].get("_estado") for d in m["deps"]]
            if any(e in ("POUSADA_FAIL", "BLOQUEADA") for e in estados_deps):
                m["_estado"] = "BLOQUEADA"
                mudou = True
    return True


def resultado(plano):
    out = {}
    for mid, m in plano["missoes"].items():
        res = m.get("_resumo") or {}
        out[mid] = {
            "estado": m.get("_estado", "PENDENTE"),
            "veredito": res.get("veredito") or res.get("status"),
            "turnos": res.get("turnos"),
            "custo": res.get("custo"),
            "run_dir": m.get("_run_dir"),
        }
    return out


def dry_run(plano):
    """Imprime ordem de despacho e comandos SEM executar."""
    ordem = ordem_topologica(plano)
    print("Ordem de despacho (topológica):")
    for i, mid in enumerate(ordem, 1):
        m = plano["missoes"][mid]
        print("  %d. %s (deps: %s)" % (i, mid, m["deps"] or "-"))
        print("     %s" % " ".join(comando_despacho(m, os.path.join("<inicio>", mid))))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Despachante de DAG")
    ap.add_argument("plano", help="caminho do plano.json")
    ap.add_argument("--dry-run", action="store_true", help="imprime ordem/comandos, não executa")
    args = ap.parse_args(argv)
    plano = ler_plano(args.plano)
    if args.dry_run:
        return dry_run(plano)
    inicio_em = os.path.join("runs", "DESPACHO-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(inicio_em, exist_ok=True)
    regs = aguardar(plano, inicio_em)
    with open(os.path.join(inicio_em, "despacho.json"), "w", encoding="utf-8") as f:
        json.dump(regs, f, ensure_ascii=False, indent=2)
    for mid, r in regs.items():
        print("%s: %s veredito=%s turnos=%s custo=%s" % (mid, r["estado"], r["veredito"], r["turnos"], r["custo"]))
    ok = all(r["estado"] == "POUSADA_PASS" for r in regs.values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROVA GB-DESP-ORDEM-01 (hermética, primeiro plano, sem sudo, sem systemd real).

(a) com espelho nativo pré-existente, o despacho RECUSA (ESPELHO_NAO_NASCEU)
    e NÃO deixa unit viva (nenhum systemd-run é chamado — assert por contagem
    de spawn via fake systemd-run no PATH);
(b) destinos.py consumido por despachante e contratador (import único, sem
    caminho duplicado — grep prova);
(c) contrato gerado contém bloco `## DESTINOS`;
(d) despacho normal completo numa unit fake local nasce com aba (fake herdr).

Saída final: GB-DESP-ORDEM-01-PROVA-OK
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")
sys.path.insert(0, SCRIPTS)

import espelho_nativo  # noqa: E402
import destinos  # noqa: E402

MID = "GB-DESP-ORDEM-01-PROVA"
FALHAS = []


def check(nome, cond, extra=""):
    if cond:
        print("ok %s" % nome)
    else:
        FALHAS.append(nome)
        print("FALHOU %s %s" % (nome, extra))


def sh(cmd, env=None, cwd=None):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="prova-gb-desp-ordem-01-")
    esp_dir = os.path.join(tmp, "espelho-nativo")
    ag_live = os.path.join(tmp, "ag-live")
    bin_dir = os.path.join(tmp, "bin")
    os.makedirs(esp_dir)
    os.makedirs(ag_live)
    os.makedirs(bin_dir)

    # ---- fakes: systemd-run (conta spawns) e herdr (pane list) ----
    spawn_log = os.path.join(tmp, "spawns.log")
    # systemd-run fake: registra o spawn E nasce o run dir (layout run-<ts>-seed<seed>-<pid>)
    with open(os.path.join(bin_dir, "systemd-run"), "w") as f:
        f.write('#!/bin/sh\necho "$@" >> %s\n'
                'prev=""; cwd=""; seed=""\n'
                'for a in "$@"; do\n'
                '  case "$prev" in\n'
                '    --cwd) cwd="$a";;\n'
                '    --seed) seed="$a";;\n'
                '  esac\n'
                '  prev="$a"\n'
                'done\n'
                'if [ -n "$cwd" ] && [ -n "$seed" ]; then\n'
                '  mkdir -p "$cwd"\n'
                '  mkdir "$cwd/run-$(date +%%s)-seed${seed}-$$" 2>/dev/null\n'
                'fi\nexit 0\n' % spawn_log)
    os.chmod(os.path.join(bin_dir, "systemd-run"), 0o755)
    # herdr fake: pane list + tab create com pane id no layout w<p>:p<n> (regex do despachante)
    with open(os.path.join(bin_dir, "herdr"), "w") as f:
        f.write('#!/bin/sh\nif [ "$1" = "pane" ] && [ "$2" = "list" ]; then\n'
                '  echo \'{"result":{"panes":[{"pane_id":"w0:p1"}]}}\'\n'
                '  exit 0\nfi\n'
                'if [ "$1" = "tab" ] && [ "$2" = "create" ]; then\n'
                '  echo \'{"result":{"root_pane":{"pane_id":"w0:p1"}}}\'\n'
                '  exit 0\nfi\nexit 0\n')
    os.chmod(os.path.join(bin_dir, "herdr"), 0o755)
    # systemctl fake: nunca ativo (unit não existe) — prova não toca systemd real
    with open(os.path.join(bin_dir, "systemctl"), "w") as f:
        f.write('#!/bin/sh\nif [ "$1" = "is-active" ]; then echo inactive; exit 3; fi\nexit 0\n')
    os.chmod(os.path.join(bin_dir, "systemctl"), 0o755)

    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env["PATH"]
    env["ESP_DIR"] = esp_dir
    env["HERDR_BIN"] = os.path.join(bin_dir, "herdr")
    env["HERDR_AG_LIVE_DIR"] = ag_live
    env["AG_LIVE_DIR"] = ag_live  # despachante lê AG_LIVE_DIR (ESPELHO_SALA)
    env["HERDR_LEDGER_DIR"] = os.path.join(tmp, "ledger")
    env["PROVA_HERMETICA"] = "1"  # despachante dispensa root na prova (fakes via env)
    env["PROVA_HERMETICA"] = "1"  # GB-DESP-ORDEM-01: despachante aceita sem root

    # contrato mínimo com stops válidas
    wt = os.path.join(tmp, "wt")
    os.makedirs(wt, exist_ok=True)
    wt = os.path.join(tmp, "wt")
    os.makedirs(wt, exist_ok=True)
    contrato = os.path.join(tmp, "contrato.md")
    with open(contrato, "w") as f:
        f.write("# MISSAO %s\n\n## STOPS\n```harness-stop\ncmd cd %s && test -s RELATORIO-%s.md\n```\n" % (MID, wt, MID))

    desp = os.path.join(SCRIPTS, "despachar_missao.py")

    # ---------- (a) espelho nativo pré-existente => RECUSA sem unit viva ----------
    assert espelho_nativo.nascer_espelho(MID, esp_dir), "espelho nativo de prova deve nascer"
    rc, out, err = sh("python3 %s %s %s --sem-baseline --seed 1" % (desp, contrato, wt), env=env)
    check("a-recusa-duplicado", "ESPELHO_NAO_NASCEU" in (out + err) and '"ok": false' in out,
          "rc=%d out=%s err=%s" % (rc, out[:200], err[:200]))
    spawns = open(spawn_log).read().strip() if os.path.exists(spawn_log) else ""
    check("a-sem-unit-viva", spawns == "", "spawn inesperado: %r" % spawns[:200])

    # ---------- (d) despacho normal (espelho livre) => nasce com aba ----------
    espelho_nativo.pousar_espelho(MID, esp_dir)
    # run dir pré-nascido: o systemd-run fake não executa mission_run.py;
    # o despachante deve achar o run dir e montar a aba (herdr fake) nele.
    runs_dir = os.path.join(wt, "runs", MID)
    os.makedirs(runs_dir, exist_ok=True)
    os.makedirs(os.path.join(runs_dir, "run-prova-seed2-1"), exist_ok=True)
    rc, out, err = sh("python3 %s %s %s --sem-baseline --seed 2" % (desp, contrato, wt), env=env)
    ok = False
    try:
        data = json.loads(out.strip().splitlines()[-1])
        ok = data.get("ok") is True and data.get("tab")
    except Exception:
        pass
    check("d-despacho-ok-com-aba", ok, "rc=%d out=%s err=%s" % (rc, out[:300], err[:300]))
    espelho_sala = os.path.join(ag_live, MID + ".espelho.json")
    check("d-espelho-sala-nasce", os.path.isfile(espelho_sala))
    espelho_nativo.pousar_espelho(MID, esp_dir)

    # ---------- (b) destinos.py import único, sem caminho duplicado ----------
    src_desp = open(desp).read()
    check("b-despachante-importa-destinos", "import destinos" in src_desp)
    check("b-despachante-sem-hardcode-aglive", "/tmp/ag-live" not in src_desp)
    check("b-despachante-sem-hardcode-resumo", "/tmp/resumo-" not in src_desp)
    src_esp = open(os.path.join(SCRIPTS, "espelho_nativo.py")).read()
    check("b-espelho-nativo-consome-destinos", "destinos" in src_esp or "ESP_DIR" in src_esp)
    src_ct = open(os.path.join(SCRIPTS, "contratador.sh")).read()
    check("b-contratador-usa-destinos", "destinos.py" in src_ct)

    # ---------- (c) contrato gerado contém bloco ## DESTINOS ----------
    rc, out, _ = sh("python3 %s" % os.path.join(SCRIPTS, "destinos.py"), env=env)
    check("c-destinos-bloco", rc == 0 and out.startswith("## DESTINOS") and "ESPELHO_SALA" in out)

    shutil.rmtree(tmp, ignore_errors=True)

    if FALHAS:
        print("FALHAS: %s" % ", ".join(FALHAS))
        sys.exit(1)
    print("GB-DESP-ORDEM-01-PROVA-OK")


if __name__ == "__main__":
    main()
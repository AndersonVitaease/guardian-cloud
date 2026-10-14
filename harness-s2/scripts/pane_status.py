# marker: def status_do_pane /home/worker/harness-s2/scripts/pane_status.py
#!/usr/bin/env python3
"""CLI pane_status.py — resume o status de uma run a partir do harness-pane.log.

Uso: python3 scripts/pane_status.py <run_dir>
"""
import argparse
import glob
import os
import sys


def _pane_log_mais_recente(run_dir):
    """Localiza o run-*/harness-pane.log mais recente sob run_dir."""
    padroes = [
        os.path.join(run_dir, "harness-pane.log"),
        os.path.join(run_dir, "run-*", "harness-pane.log"),
        os.path.join(run_dir, "*", "run-*", "harness-pane.log"),
    ]
    candidatos = []
    for padrao in padroes:
        candidatos.extend(glob.glob(padrao))
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)


def status_do_pane(run_dir):
    """Retorna (mensagem, exit_code) do status da run a partir do pane log.

    - VEREDITO <PASS|FAIL> | <resto> se houver linha de veredito;
    - EM ANDAMENTO | <última linha> caso contrário;
    - SEM PANE LOG (exit 1) se não houver pane log.
    """
    log = _pane_log_mais_recente(run_dir)
    if log is None:
        return "SEM PANE LOG | nenhum harness-pane.log encontrado em %s" % run_dir, 1
    with open(log, encoding="utf-8") as f:
        linhas = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not linhas:
        return "SEM PANE LOG | %s vazio" % log, 1
    veredito = None
    for ln in linhas:
        if "VEREDITO" in ln:
            veredito = ln
    if veredito is not None:
        resto = veredito.split("VEREDITO", 1)[1].strip()
        return "VEREDITO %s" % resto, 0
    return "EM ANDAMENTO | %s" % linhas[-1], 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resume o status de uma run a partir do harness-pane.log mais recente."
    )
    parser.add_argument("run_dir", help="Diretório da run (contendo run-*/harness-pane.log)")
    args = parser.parse_args(argv)
    msg, code = status_do_pane(args.run_dir)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())

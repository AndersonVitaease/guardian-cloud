# FECHO-AUTONOMO-01: a run deixa PRONTO o pacote do fecho (verificação objetiva
# + dados) para o supervisor (ou hook futuro) só aplicar.
#
# verificar(run_dir, mission_path) → dict:
#   - re-executa check_stop_conditions (parse do contrato + estado ATUAL do run dir);
#   - lê run-summary.json (veredito, motivo, turnos, custo);
#   - pytest tests do repo com timeout 120s (subprocess) → verde/vermelho + contagem;
#   - roda aprende.extrair (o que a missão deixou de aprendizado);
#   - grava fecho.json NO RUN DIR (atômico):
#     {pronto, veredito, conditions, suite, aprendizado, ts}
#     pronto = stop-conditions TODAS ok E suíte verde.
#
# CLI: python3 scripts/fecho.py <run_dir> <mission_path>
#   → imprime fecho.json; exit 0 se pronto=True, exit 1 se não (objetivo).
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def _resumo(run_dir):
    p = os.path.join(run_dir, "run-summary.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _suite(repo=REPO, timeout=120):
    """pytest tests do repo -> {verde, passed, failed, erro}."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
            cwd=repo, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return {"verde": False, "passed": None, "failed": None, "erro": str(e)}
    passed = failed = None
    m = re.search(r"(\d+) passed", r.stdout or "")
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", r.stdout or "")
    if m:
        failed = int(m.group(1))
    return {"verde": r.returncode == 0, "passed": passed, "failed": failed,
            "rc": r.returncode}


def verificar(run_dir, mission_path, repo=REPO):
    """Pacote do fecho: verificação objetiva + dados, gravado em fecho.json."""
    from harness import check_stop_conditions, parse_stop_conditions
    contrato = open(mission_path, encoding="utf-8").read()
    conds = parse_stop_conditions(contrato)
    todas, state = check_stop_conditions(conds, run_dir)
    conditions = {"todas_ok": bool(todas) if conds else False,
                  "sem_condicoes": not conds,
                  "estado": state}
    resumo = _resumo(run_dir)
    suite = _suite(repo)
    try:
        import importlib
        aprendizado = importlib.import_module("scripts.aprende").extrair(run_dir)
    except Exception as e:  # noqa: BLE001 — aprendizado nunca derruba o fecho
        aprendizado = {"erro": str(e)}
    pronto = bool(conditions["todas_ok"] and suite["verde"])
    fecho = {
        "pronto": pronto,
        "veredito": (resumo or {}).get("veredito"),
        "motivo": (resumo or {}).get("motivo"),
        "turnos": (resumo or {}).get("turnos", (resumo or {}).get("turns")),
        "custo_usd": (resumo or {}).get("custo_usd", (resumo or {}).get("cum_usd")),
        "resumo_ausente": resumo is None,
        "conditions": conditions,
        "suite": suite,
        "aprendizado": aprendizado,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # gravação atômica (tmp + rename)
    fd, tmp = tempfile.mkstemp(dir=run_dir, prefix=".fecho-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(fecho, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(run_dir, "fecho.json"))
    return fecho


def main(argv):
    if len(argv) != 3:
        print("uso: python3 scripts/fecho.py <run_dir> <mission_path>", file=sys.stderr)
        return 2
    fecho = verificar(argv[1], argv[2])
    print(json.dumps(fecho, ensure_ascii=False, indent=2))
    return 0 if fecho["pronto"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
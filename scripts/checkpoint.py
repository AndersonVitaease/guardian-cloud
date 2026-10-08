#!/usr/bin/env python3
"""Checkpoint de janela: salvar estado e gerar prompt de retomada (stdlib)."""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone


def salvar(run_dir, resumo, diag):
    """Grava CHECKPOINT.json atomicamente (tmp+rename) em run_dir."""
    os.makedirs(run_dir, exist_ok=True)
    dados = {
        "mission_id": resumo.get("mission_id", ""),
        "veredito_anterior": resumo.get("veredito", ""),
        "motivo": resumo.get("motivo", ""),
        "turnos": resumo.get("turnos", 0),
        "custo": resumo.get("custo", 0.0),
        "pendentes": resumo.get("pendentes", []),
        "bloco_diagnostico": diag if isinstance(diag, str) else str(diag),
        "proxima_janela": resumo.get("proxima_janela", {"max_turns_sugerido": 60, "nota": ""}),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    fd, tmp = tempfile.mkstemp(dir=run_dir, prefix=".checkpoint-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(run_dir, "CHECKPOINT.json"))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return os.path.join(run_dir, "CHECKPOINT.json")


def carregar(checkpoint_path):
    with open(checkpoint_path, encoding="utf-8") as f:
        return json.load(f)


def retomar_prompt(checkpoint_path):
    """Texto pt-BR pronto para injetar no início da próxima run da mesma missão."""
    c = carregar(checkpoint_path)
    pend = c.get("pendentes", [])
    pend_txt = "\n".join("- %s" % p for p in pend) if pend else "- (nenhuma)"
    janela = c.get("proxima_janela", {})
    return (
        "## CHECKPOINT DA JANELA ANTERIOR\n"
        "Missão: %s\n"
        "Veredito anterior: %s (motivo: %s) — turnos: %s, custo: %s\n\n"
        "### JÁ ENTREGUE (verde — NÃO REFAÇA o que está verde)\n"
        "%s\n\n"
        "### STOP-CONDITIONS AINDA PENDENTES (valores atuais)\n"
        "%s\n\n"
        "### JANELA NOVA\n"
        "max_turns sugerido: %s%s\n"
        "Retome exatamente de onde parou; valide o que já está verde antes de reexecutar.\n"
        % (
            c.get("mission_id", ""),
            c.get("veredito_anterior", ""),
            c.get("motivo", ""),
            c.get("turnos", 0),
            c.get("custo", 0.0),
            c.get("bloco_diagnostico", "").strip() or "(sem diagnóstico registrado)",
            pend_txt,
            janela.get("max_turns_sugerido", "?"),
            (" — " + janela["nota"]) if janela.get("nota") else "",
        )
    )


def _cli():
    if len(sys.argv) < 3:
        print("uso: checkpoint.py salvar <run_dir> <resumo.json> | retomar <run_dir>", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "salvar":
        run_dir, resumo_path = sys.argv[2], sys.argv[3]
        with open(resumo_path, encoding="utf-8") as f:
            resumo = json.load(f)
        diag = resumo.pop("bloco_diagnostico", "")
        salvar(run_dir, resumo, diag)
        return 0
    if cmd == "retomar":
        path = os.path.join(sys.argv[2], "CHECKPOINT.json")
        sys.stdout.write(retomar_prompt(path))
        return 0
    print("comando desconhecido: %s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
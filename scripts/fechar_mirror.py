#!/usr/bin/env python3
"""FECHO-CONSISTENTE-01 (FIND-8ebbff56): atualiza o mission-state-mirror no fecho.

Uso: fechar_mirror.py <ID> --resumo /tmp/resumo-<ID>.json [--state-dir D]

Comportamento idempotente:
- mirror ausente -> cria {status: closed, verdict: <veredito do resumo>};
- mirror fechado com o MESMO verdict -> ok, nada muda (updatedAt preservado);
- mirror fechado com verdict DIVERGENTE -> NAO sobrescreve, registra aviso;
- mirror em estado nao-terminal (failed/cancelled/running/...) -> regredir
  NUNCA: sempre promove para closed + verdict.
Fail-open: nunca levanta; saida JSON {"ok": ..., "acao": ...}.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR_DEFAULT = os.environ.get("MISSION_STATE_DIR") or \
    "/opt/mission-events/mission-state-mirror"
LOG_DEFAULT = "/tmp/fechar_missao-{id}.log"


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds") \
        .replace("+00:00", "Z")


def _log(id_, msg):
    try:
        with open(LOG_DEFAULT.format(id=id_), "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (_agora(), msg))
    except Exception:
        pass


def _ler_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _gravar_atomico(path, dados):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mirror-",
                               suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, str(path))


def fechar_mirror(missao_id, resumo_path, state_dir=None):
    state_dir = state_dir or STATE_DIR_DEFAULT
    path = Path(state_dir) / ("%s.json" % missao_id)
    resumo = _ler_json(resumo_path) or {}
    veredito = (resumo.get("veredito") or resumo.get("status") or "").upper()
    mirror = _ler_json(path)
    if not isinstance(mirror, dict):
        mirror = {"missionId": missao_id}
        criado = True
    else:
        criado = False
    status_atual = mirror.get("status")
    verdict_atual = (mirror.get("verdict") or mirror.get("veredito") or "")
    verdict_atual = (verdict_atual or "").upper()

    if status_atual == "closed":
        if verdict_atual == veredito or not veredito:
            return {"ok": True, "acao": "idempotente", "status": "closed",
                    "verdict": verdict_atual or None, "path": str(path),
                    "criado": criado}
        _log(missao_id, "AVISO mirror_verdict_divergente "
             "(mirror=%s resumo=%s) — mirror NAO sobrescrito"
             % (verdict_atual or "-", veredito or "-"))
        return {"ok": False, "acao": "divergente", "status": "closed",
                "verdict": verdict_atual or None, "path": str(path),
                "criado": criado}

    agora = _agora()
    mirror["status"] = "closed"
    if veredito:
        mirror["verdict"] = veredito
        mirror["veredito"] = veredito
    mirror["updatedAt"] = agora
    mirror["closedAt"] = mirror.get("closedAt") or agora
    if resumo_path:
        mirror["resumo"] = resumo_path
    _gravar_atomico(path, mirror)
    _log(missao_id, "OK mirror_fechar status=closed verdict=%s (antes=%s)"
         % (veredito or "-", status_atual))
    return {"ok": True, "acao": "atualizado", "status": "closed",
            "verdict": veredito or None, "path": str(path),
            "criado": criado, "status_anterior": status_atual}


def main(argv):
    p = argparse.ArgumentParser(description="Atualiza mirror no fecho")
    p.add_argument("missao_id")
    p.add_argument("--resumo", required=True)
    p.add_argument("--state-dir", default=None)
    args = p.parse_args(argv[1:])
    out = fechar_mirror(args.missao_id, args.resumo, state_dir=args.state_dir)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

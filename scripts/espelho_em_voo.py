"""GB-MIGRA-B-01 — sessões de AGENTE NOSSO em voo via espelho.sh.

Cada sessão despachada pelo espelho.sh grava <dir>/<ID>.espelho.json com
campos id/tab_id/pane_id/veredito/ms/ts. Sessão EM VOO = arquivo sem campo
"veredito" preenchido (ausente, null ou string vazia). Pousada = veredito
preenchido (PASS/FAIL/etc).

Fail-open: qualquer erro (json corrompido, permissão, dir inexistente) é
ignorado — nunca derruba o chamador (handle_mission_list / fast-router).

Diretórios: env ESPELHO_DIRS (separador ':' por diretório). Padrão: /tmp/ag-*/
"""
import glob
import json
import os
from typing import Any, Dict, List, Optional

_PADRAO = "/tmp/ag-*"


def _dirs() -> List[str]:
    env = os.environ.get("ESPELHO_DIRS", "").strip()
    if env:
        return [d.strip() for d in env.split(":") if d.strip()]
    return sorted(glob.glob(_PADRAO))


def coletar_em_voo(dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Devolve {"sessoes": [{id, tab_id, ts}], "total": N} das sessões em voo."""
    sessoes: List[Dict[str, Any]] = []
    for d in (dirs if dirs is not None else _dirs()):
        try:
            paths = sorted(glob.glob(os.path.join(d, "*.espelho.json")))
        except Exception:
            continue
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue  # fail-open: json corrompido/ilegível não conta
            if not isinstance(data, dict):
                continue
            if data.get("veredito"):
                continue  # veredito preenchido = pousada
            sessoes.append({
                "id": data.get("id")
                or os.path.basename(path)[: -len(".espelho.json")],
                "tab_id": data.get("tab_id"),
                "ts": data.get("ts"),
            })
    return {"sessoes": sessoes, "total": len(sessoes)}


if __name__ == "__main__":
    import sys

    json.dump(coletar_em_voo(), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

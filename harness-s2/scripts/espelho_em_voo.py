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


def _estado_de(data: Dict[str, Any]) -> str:
    """GB-MIGRA-B-02: estado legível da sessão.

    veredito preenchido → "pousou:<VEREDITO>"; senão (status "running",
    ausente ou vazio) → "em voo"."""
    veredito = data.get("veredito")
    if veredito:
        return "pousou:%s" % veredito
    return "em voo"


def coletar_sessoes(dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """GB-MIGRA-B-02: TODAS as sessões espelhadas, cada uma com `estado`.

    Devolve {"sessoes": [{id, tab_id, ts, estado}], "total": N} — em voo e
    pousadas. Fail-open igual a coletar_em_voo."""
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
            sessoes.append({
                "id": data.get("id")
                or os.path.basename(path)[: -len(".espelho.json")],
                "tab_id": data.get("tab_id"),
                "ts": data.get("ts"),
                "estado": _estado_de(data),
            })
    return {"sessoes": sessoes, "total": len(sessoes)}


def coletar_em_voo(dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Devolve {"sessoes": [{id, tab_id, ts, estado}], "total": N} das sessões em voo.

    (pré-02: só as SEM veredito preenchido; pousadas ficam de fora —
    use coletar_sessoes() para ver também as pousadas.)"""
    todas = coletar_sessoes(dirs)["sessoes"]
    sessoes = [s for s in todas if s["estado"] == "em voo"]
    return {"sessoes": sessoes, "total": len(sessoes)}


if __name__ == "__main__":
    import sys

    json.dump(coletar_em_voo(), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

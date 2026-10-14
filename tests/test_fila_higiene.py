import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import fila_higiene as fh


def _escrever(tmp_path, entradas):
    p = tmp_path / "fila.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for e in entradas:
            f.write(json.dumps(e) + "\n")
    return str(p)


def _ent(eid, mid="M1", status="queued"):
    return {"id": eid, "payload": {"missionId": mid, "status": status,
            "promptFile": "/tmp/x.md"}, "type": "mission_dispatch"}


def test_duplicados_contados(tmp_path):
    p = _escrever(tmp_path, [_ent("a"), _ent("a"), _ent("a"), _ent("b")])
    inv = fh.inventariar(p)
    assert inv["total"] == 4
    assert inv["ids_duplicados"] == {"a": 3}
    assert inv["linhas_duplicadas"] == 2


def test_plano_mantem_primeira_ocorrencia(tmp_path):
    p = _escrever(tmp_path, [_ent("a", "M1"), _ent("a", "M2"), _ent("b")])
    fila = fh._ler(p)
    rem = fh.plano_limpeza(fila)
    assert rem == [1]
    restantes = [e for i, e in enumerate(fila) if i not in set(rem)]
    assert [e["id"] for e in restantes] == ["a", "b"]
    assert restantes[0]["payload"]["missionId"] == "M1"


def test_dry_run_nao_escreve(tmp_path):
    p = _escrever(tmp_path, [_ent("a"), _ent("a")])
    res = fh.limpar(p, dry_run=True)
    assert res["escrito"] is False
    assert not os.path.exists(p + ".limpa.jsonl")


def test_limpar_escreve_limpa(tmp_path):
    p = _escrever(tmp_path, [_ent("a"), _ent("a"), _ent("b")])
    res = fh.limpar(p, dry_run=False)
    assert res["escrito"] is True
    assert res["restantes"] == 2
    with open(p + ".limpa.jsonl", encoding="utf-8") as f:
        linhas = [json.loads(l) for l in f if l.strip()]
    assert len(linhas) == 2
    assert [e["id"] for e in linhas] == ["a", "b"]
    # original intacta
    assert len(fh._ler(p)) == 3


def test_fila_vazia(tmp_path):
    p = _escrever(tmp_path, [])
    inv = fh.inventariar(p)
    assert inv["total"] == 0
    assert inv["ids_duplicados"] == {}
    res = fh.limpar(p, dry_run=False)
    assert res["restantes"] == 0
    assert os.path.exists(p + ".limpa.jsonl")
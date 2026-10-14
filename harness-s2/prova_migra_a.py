#!/usr/bin/env python3
"""GB-MIGRA-100-01A — prova offline das fases (a) e (b).
(a) fixture de contrato fake -> extrai o TITULO-FINDER de vigia_chat.sh,
    gera o texto do aviso de pouso e asserta que o título aparece.
(b) parser do briefing com agentes de agente fake (espelho.json) ->
    asserta contagem como "agentes de agente".
Tudo offline, sem rede. Sai com MIGRA-A-OK no stdout.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VIGIA = os.path.join(HERE, "scripts", "vigia_chat.sh")


def titulo_finder_src():
    """Extrai o python interno do TITULO-FINDER (heredoc <<'PY' ... PY)."""
    with open(VIGIA, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"# TITULO-FINDER-BEGIN\n(.*?)# TITULO-FINDER-END", src, re.S)
    assert m, "TITULO-FINDER nao encontrado em vigia_chat.sh"
    m2 = re.search(r"<<'PY'\n(.*?)\nPY\n", m.group(1), re.S)
    assert m2, "python do TITULO-FINDER nao encontrado"
    return m2.group(1)


def msg_formatter_src():
    with open(VIGIA, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"MSG=\"\$\(printf '%s' \"\$DATA\" \| VIGIA_TITULO=\"\$TITULO\" python3 -c '\n(.*?)'\)\"", src, re.S)
    assert m, "formatador de MSG nao encontrado em vigia_chat.sh"
    return m.group(1)


def prova_a():
    with tempfile.TemporaryDirectory() as run_dir:
        mid = "GB-TESTE-01"
        with open(os.path.join(run_dir, "contrato.md"), "w", encoding="utf-8") as f:
            f.write("# MISSÃO %s — Corrige Filtro de Spam\n\nconteudo\n" % mid)
        # executa o TITULO-FINDER extraido com resumo fake (sem campo titulo)
        out = subprocess.run(
            [sys.executable, "-c", titulo_finder_src(), run_dir, HERE, mid],
            capture_output=True, text=True, check=True).stdout.strip()
        assert out == "Corrige Filtro de Spam", "titulo errado: %r" % out
        titulo = out
        data = json.dumps({"missao": mid, "veredito": "PASS", "custo_usd": "1.25",
                           "turnos": "7", "aba": "x", "titulo": titulo},
                          ensure_ascii=False)
        msg = subprocess.run([sys.executable, "-c", msg_formatter_src()],
                             input=data, capture_output=True, text=True,
                             check=True).stdout
        assert "Corrige Filtro de Spam" in msg and mid in msg and "PASS" in msg, msg
        assert "US$1.25" in msg and "7 turnos" in msg, msg
        # fallback honesto: sem titulo no DATA, formatador usa o ID
        data2 = json.dumps({"missao": mid, "veredito": "FAIL", "custo_usd": "0",
                            "turnos": "2", "aba": None}, ensure_ascii=False)
        msg2 = subprocess.run([sys.executable, "-c", msg_formatter_src()],
                              input=data2, capture_output=True, text=True,
                              check=True).stdout
        assert mid in msg2 and "FAIL" in msg2, msg2


def briefing_parse(agents):
    """Parser do briefing (fase b): missoes + sessoes de agente, uma linha cada."""
    linhas = []
    ignorados = []
    for a in agents:
        if a.get("tipo") == "mission-record":
            linhas.append("%s %s %s" % (a["id"], a.get("estado", "?"), a.get("titulo", "")))
        elif a.get("tipo") == "agente":
            estado = "em voo" if a.get("ativo") else "pousado"
            linhas.append("agente de agente %s %s" % (a["id"], estado))
        else:
            ignorados.append(a.get("id", "?"))
    return linhas, ignorados


def prova_b():
    agents = [
        {"tipo": "mission-record", "id": "GB-X-1", "estado": "pousado", "titulo": "Foo"},
        {"tipo": "agente", "id": "ag-live-abc", "ativo": True},
        {"tipo": "agente", "id": "ag-live-def", "ativo": False},
    ]
    linhas, ignorados = briefing_parse(agents)
    assert len(linhas) == 3, linhas
    assert any("agente de agente ag-live-abc em voo" in l for l in linhas), linhas
    assert any("agente de agente ag-live-def pousado" in l for l in linhas), linhas
    assert not ignorados, ignorados
    # espelho.json fake de agente de agente
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "espelho.json"), "w", encoding="utf-8") as f:
            json.dump({"sessoes": [{"id": "ag-live-xyz", "ativo": True}]}, f)
        with open(os.path.join(d, "espelho.json"), encoding="utf-8") as f:
            esp = json.load(f)
        fake = [{"tipo": "agente", "id": s["id"], "ativo": s["ativo"]}
                for s in esp["sessoes"]]
        linhas2, _ = briefing_parse(fake)
        assert len(linhas2) == 1 and "em voo" in linhas2[0], linhas2


if __name__ == "__main__":
    prova_a()
    prova_b()
    print("MIGRA-A-OK")
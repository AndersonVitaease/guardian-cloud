#!/usr/bin/env python3
"""Helpers de parsing JSON para espelho.sh (evita python3 -c inline).

GB-STREAM-PTBR-01: também serve de filtro PT-BR do streamer:
  python3 _espelho_parse.py ptbr        # stdin -> stdout traduzido (labels EN -> PT-BR)
  python3 _espelho_parse.py filtro-ptbr # stdin -> filtro do streamer + tradução
"""
import json
import os
import re
import sys

# GB-STREAM-PTBR-01: dicionário compartilhado das labels inglesas geradas pelo
# display da CLI -> PT-BR. Termos técnicos (nomes de arquivo, comandos git)
# ficam intactos — só o TEXTO exibido é traduzido. Replicado em
# ponte_office.py (agent-office) e app.js (guardian-app).
PTBR_LABELS = [
    (re.compile(r"preparing terminal…?"), "abrindo terminal…"),
    (re.compile(r"preparing patch…?"), "escrevendo patch…"),
    (re.compile(r"preparing read_file…?"), "lendo arquivo…"),
    (re.compile(r"preparing write_file…?"), "escrevendo arquivo…"),
    (re.compile(r"preparing search_files…?"), "buscando arquivos…"),
    (re.compile(r"preparing execute_code…?"), "executando código…"),
    (re.compile(r"preparing skill_view…?"), "abrindo skill…"),
    (re.compile(r"preparing a patch is read-only"), "escrevendo patch…"),
    (re.compile(r"preparing (\S+)…?"), r"preparando \1…"),
    # prompt "$ cmd" -> "executando comando: cmd" (o comando fica intacto)
    (re.compile(r"(?<![|\w])\$ (?=\S)"), "executando comando: "),
]

RE_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def traduz_linha(line: str) -> str:
    """Traduz as labels inglesas do stream para PT-BR (códigos ANSI preservados)."""
    out = line
    for pat, repl in PTBR_LABELS:
        out = pat.sub(repl, out)
    return out

MODE = sys.argv[1] if len(sys.argv) > 1 else ""

try:
    if MODE == "create":
        d = json.loads(os.environ["PROMPT_JSON"])
        res = d.get("result", {})
        tab = res.get("tab", {})
        tab_id = tab.get("tab_id") or res.get("root_pane", {}).get("tab_id")
        ws_id = tab.get("workspace_id") or res.get("root_pane", {}).get("workspace_id")
        if not tab_id or not ws_id:
            sys.exit(1)
        print(f"{tab_id}|{ws_id}")
    elif MODE == "wscreate":
        d = json.loads(os.environ["WS_JSON"])
        res = d.get("result", {})
        ws = res.get("workspace", {})
        ws_id = ws.get("workspace_id") or res.get("root_pane", {}).get("workspace_id")
        if not ws_id:
            sys.exit(1)
        print(ws_id)
    elif MODE == "pane":
        d = json.loads(os.environ["PANE_JSON"])
        tab_id = os.environ["TAB_ID"]
        res = d.get("result", {})
        panes = res.get("panes") or res.get("pane_list") or []
        if not isinstance(panes, list):
            panes = [panes]
        found = None
        for p in panes:
            if isinstance(p, dict) and p.get("tab_id") == tab_id:
                found = p.get("pane_id") or p.get("id")
                break
        if not found:
            sys.exit(1)
        print(found)
    elif MODE in ("ptbr", "filtro-ptbr"):
        # GB-STREAM-PTBR-01: traduz as labels EN -> PT-BR, linha a linha,
        # preservando o resto (códigos ANSI de cor incluídos).
        try:
            for ln in sys.stdin:
                sys.stdout.write(traduz_linha(ln))
                sys.stdout.flush()
        except (BrokenPipeError, OSError):
            pass
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)

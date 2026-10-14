#!/usr/bin/env python3
# SPIKE-DESK-CONN-01 — falso app desktop: disca PARA FORA (long-poll 1s), registra tools.
import json, os, signal, subprocess, sys, time, urllib.request

GW = os.environ.get('SPIKE_GW', 'http://127.0.0.1:21001')
TOKEN = os.environ.get('SPIKE_TOKEN', 'tok-tenant-a')

TOOLS = [
    {"name": "proc_list", "description": "Lista processos locais (ps)",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "echo_local", "description": "Ecoa texto com prefixo LOCAL:",
     "inputSchema": {"type": "object", "properties": {"texto": {"type": "string"}}}},
]

def post(path, payload, timeout=10):
    req = urllib.request.Request(GW + path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def run_tool(name, args):
    if name == 'proc_list':
        out = subprocess.run(['ps', '-eo', 'pid,comm', '--no-headers'], capture_output=True, text=True).stdout
        return '\n'.join(out.splitlines()[:20])
    if name == 'echo_local':
        return 'LOCAL: ' + str(args.get('texto', ''))
    raise ValueError('tool desconhecida: ' + name)

def main():
    post('/conector/registrar', {"token": TOKEN, "tools": TOOLS})
    print('conector registrado', flush=True)
    while True:
        try:
            r = post('/conector/poll', {"token": TOKEN}, timeout=5)
        except Exception:
            time.sleep(0.3); continue
        call = r.get('call')
        if not call:
            continue
        try:
            resp = {"token": TOKEN, "id": call["id"], "ok": True, "texto": run_tool(call["name"], call.get("arguments") or {})}
        except Exception as e:
            resp = {"token": TOKEN, "id": call["id"], "ok": False, "erro": str(e)}
        try: post('/conector/responder', resp)
        except Exception: pass

def _term(*a):
    try: post('/conector/bye', {"token": TOKEN})
    except Exception: pass
    sys.exit(0)

signal.signal(signal.SIGTERM, _term)
if __name__ == '__main__':
    main()
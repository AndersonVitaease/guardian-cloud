#!/usr/bin/env python3
# SPIKE-DESK-CONN-01 — prova E2E hermética (sobe gateway + conector, valida fluxo reverso).
import json, os, signal, socket, subprocess, sys, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))

def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p

def call(port, token, method, params=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/mcp',
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def err_tipo(resp):
    return (resp.get('error') or {}).get('data', {}).get('tipo')

def main():
    port = free_port()
    gw = subprocess.Popen(['node', os.path.join(ROOT, 'gateway.js')], env={**os.environ, 'SPIKE_PORT': str(port)},
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.6)
    ok = False
    try:
        for _ in range(50):
            try:
                call(port, 'tok-tenant-a', 'initialize'); break
            except Exception: time.sleep(0.1)
        con = subprocess.Popen([sys.executable, os.path.join(ROOT, 'conector.py')],
                               env={**os.environ, 'SPIKE_GW': f'http://127.0.0.1:{port}', 'SPIKE_TOKEN': 'tok-tenant-a'},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)

        # 1) tools/list contém proc_list e echo_local
        r = call(port, 'tok-tenant-a', 'tools/list')
        names = [t['name'] for t in r['result']['tools']]
        assert 'proc_list' in names and 'echo_local' in names, names
        print('OK tools/list:', names)

        # 2) tools/call proc_list -> saída de ps
        r = call(port, 'tok-tenant-a', 'tools/call', {"name": "proc_list", "arguments": {}})
        txt = r['result']['content'][0]['text']
        assert txt.strip(), txt
        print('OK proc_list (amostra):', txt.splitlines()[0])

        # 3) tools/call echo_local("x") -> LOCAL: x
        r = call(port, 'tok-tenant-a', 'tools/call', {"name": "echo_local", "arguments": {"texto": "x"}})
        assert r['result']['content'][0]['text'] == 'LOCAL: x', r
        print('OK echo_local')

        # 4) token B inválido
        r = call(port, 'tok-BAD', 'tools/list')
        assert err_tipo(r) == 'MCP_TOKEN_INVALIDO', r
        print('OK MCP_TOKEN_INVALIDO')

        # 5) conector morto -> CONECTOR_OFFLINE e tool sai do tools/list
        con.send_signal(signal.SIGTERM); con.wait(timeout=5)
        time.sleep(0.5)
        r = call(port, 'tok-tenant-a', 'tools/call', {"name": "proc_list", "arguments": {}})
        assert err_tipo(r) == 'CONECTOR_OFFLINE', r
        r = call(port, 'tok-tenant-a', 'tools/list')
        assert 'proc_list' not in [t['name'] for t in r['result']['tools']], r
        print('OK CONECTOR_OFFLINE + tools/list limpa')

        ok = True
    finally:
        gw.terminate()
        try: gw.wait(timeout=5)
        except Exception: gw.kill()
    assert ok
    print('SPIKE-DESK-CONN-01-PROVA-OK')

if __name__ == '__main__':
    main()
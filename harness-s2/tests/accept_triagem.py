#!/usr/bin/env python3
"""Aceite RD-TOOL-TRIAGEM-01 (supervisor; worker NAO edita). Usa trails REAIS de 09-10/10."""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASOS = [
    # (runs_dir da missao, causa que DEVE aparecer em alguma tentativa, tentativas esperadas>=)
    ('/home/worker/wt-RD-GB-ABUSE-01C/runs/RD-GB-ABUSE-01C', 'LEITURA_RECUSADA', 2),
    ('/home/worker/wt-RD-HARN-FATIA-AUTO-03/runs/RD-HARN-FATIA-AUTO-03', 'SO_EXPLORACAO', 4),
    ('/home/worker/wt-RD-HARN-FATIA-AUTO-03/runs/RD-HARN-FATIA-AUTO-03', 'LOOP_COMANDO_RECUSADO', 4),
    ('/home/worker/wt-RD-HARN-FATIA-AUTO-03/runs/RD-HARN-FATIA-AUTO-03', 'EDIT_FALHOU', 4),
]


def triar(d):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'triagem.py'), d],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, ('rc', r.returncode, r.stderr[-300:])
    return json.loads(r.stdout)


def main():
    for d, causa, minimo in CASOS:
        j = triar(d)
        assert len(j['tentativas']) >= minimo, (d, len(j['tentativas']))
        causas = {c for t in j['tentativas'] for c in t['causas']}
        assert causa in causas, ('causa esperada ausente', d, causa, causas)
        assert j['causa_dominante'] and j['acao'], ('sem causa_dominante/acao', j)
        for t in j['tentativas']:
            assert t['evidencia'], ('tentativa sem evidencia', t)
    ok = triar('/home/worker/wt-RD-HARN-FATIA-AUTO-02/runs/RD-HARN-FATIA-AUTO-02')
    assert ok['causa_dominante'] in ('PASS', None), ('PASS nao pode virar falha', ok['causa_dominante'])
    assert triar('/home/worker/wt-RD-GB-ABUSE-01C/runs/RD-GB-ABUSE-01C') == triar('/home/worker/wt-RD-GB-ABUSE-01C/runs/RD-GB-ABUSE-01C'), 'nao deterministico'
    print('ACEITE-TRIAGEM OK')


if __name__ == '__main__':
    main()

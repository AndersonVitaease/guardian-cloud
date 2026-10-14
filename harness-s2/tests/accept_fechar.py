#!/usr/bin/env python3
"""Aceite RD-TOOL-FECHAR-01 (supervisor; worker NAO edita)."""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fechar(*a):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fechar_missao.py'), *a],
                       capture_output=True, text=True, timeout=170)
    assert r.returncode in (0, 1), ('rc', r.returncode, r.stderr[-300:])
    return json.loads(r.stdout)


def main():
    # PASS real ja mergeado: tudo verde, pronto
    j = fechar('RD-HARN-FATIA-AUTO-02', '--contrato', '/opt/mission-events/missao-rd-harn-fatia-auto-02.md',
               '--worktree', '/home/worker/wt-RD-HARN-FATIA-AUTO-02')
    assert j['veredito'] == 'PASS' and j['stops_verdes'] == j['stops_total'] == 6, j
    assert j['pronto_para_fechar'] is True and j['aplicado'] is False, 'dry-run e o padrao: nada aplicado'
    pk = j['registro']
    assert pk['ucme']['summary'] and pk['ucme']['projectId'] and pk['roadmap_linha'].startswith('- '), pk
    assert 'RD-HARN-FATIA-AUTO-02' in pk['ucme']['summary'] and 'RD-HARN-FATIA-AUTO-02' in pk['roadmap_linha']
    # FAIL com WIP bom (ledger FAIL vagueio 6/7, so faltava o nome do relatorio): NAO pronto, diz qual stop
    k = fechar('RD-GB-ABUSE-01G', '--contrato', '/opt/mission-events/missao-rd-gb-abuse-01g.md',
               '--worktree', '/home/worker/wt-RD-GB-ABUSE-01D')
    assert k['veredito'] == 'FAIL', k['veredito']
    assert k['stops_total'] == 7 and k['stops_verdes'] >= 6, k
    assert 'avisos' in k and isinstance(k['avisos'], list)
    # qualidade: contrato cujo conjunto de stops e so trivial deve gerar aviso RASO
    t = fechar('RD-HARN-FATIA-AUTO-01', '--contrato', '/opt/mission-events/missao-rd-harn-fatia-auto-01.md',
               '--worktree', '/home/worker/wt-RD-HARN-FATIA-AUTO-01')
    assert t['veredito'] == 'PASS' and 'avisos' in t
    print('ACEITE-FECHAR OK')


if __name__ == '__main__':
    main()

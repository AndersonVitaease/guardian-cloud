#!/usr/bin/env python3
"""Aceite v3 RD-HARN-FATIA-AUTO-03 (supervisor; worker NAO edita). Relevancia do mapa."""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRATO = '/opt/mission-events/missao-rd-gb-abuse-01c.md'
REPO = '/home/worker/wt-RD-GB-ABUSE-01D'
COMENT = re.compile(r'^\s*(#|//|\*|/\*|"""|\'\'\')')


def main():
    out = tempfile.mkdtemp(prefix='fa3-', dir='/tmp')
    os.chmod(out, 0o777)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fatiar_auto.py'), CONTRATO, REPO, out],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, ('rc', r.returncode, r.stderr[-300:])
    plano = json.load(open(os.path.join(out, 'plano.json')))
    achou_ratelimit = False
    achou_tos = False
    for f in plano['fatias']:
        txt = open(os.path.join(out, f['arquivo']), encoding='utf-8').read()
        mapa = re.findall(r'`([\w./-]+\.(?:js|mjs|py)):(\d+)`[^`\n]*`([^`\n]+)`', txt)
        assert mapa, ('fatia sem mapa', f['id'])
        corpo = txt[txt.find('## ENTREGAS'):txt.find('## REGRAS')] if '## ENTREGAS' in txt else txt
        citados = set(re.findall(r'`([^`\n]+)`', corpo))
        for fn, n, sim in mapa:
            linha = open(os.path.join(REPO, fn), encoding='utf-8', errors='replace').read().split('\n')[int(n) - 1]
            assert not COMENT.match(linha), ('mapa aponta linha de comentario/docstring', f['id'], fn, n, sim)
            if re.fullmatch(r'[A-Z][A-Z0-9_]+', sim):
                assert any(sim in c for c in citados), ('constante ALL_CAPS que a entrega nao cita', f['id'], sim)
            assert sim != '/api/', ('simbolo /api/ e generico demais', f['id'])
            assert any(sim in c or c in sim for c in citados), ('simbolo nao vem de um termo citado entre crases na entrega', f['id'], sim)
            if sim == 'rateLimit' and fn == 'server.js':
                achou_ratelimit = True
            if sim in ('tosAccepted', 'tos_accepted_at'):
                achou_tos = True
    assert achou_ratelimit, 'nenhuma fatia mapeou a definicao rateLimit em server.js (ancora da entrega 1)'
    assert achou_tos, 'nenhuma fatia mapeou tosAccepted/tos_accepted_at (ancora da entrega 2)'
    print('ACEITE-FATIA-AUTO3 OK: mapa relevante (ancoras reais, sem comentario, sem constante solta)')


if __name__ == '__main__':
    main()

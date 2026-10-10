#!/usr/bin/env python3
"""Aceite RD-HARN-FATIA-AUTO-01 (escrito pelo supervisor; o worker NAO edita este arquivo).

Roda scripts/fatiar_auto.py sobre um contrato GRANDE REAL (RD-GB-ABUSE-01C, 5 entregas,
server/app/db/provas) e confere o plano e as micro-missoes geradas com dados reais."""
import hashlib, json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTRATO = '/opt/mission-events/missao-rd-gb-abuse-01c.md'
REPO = '/home/worker/wt-RD-GB-ABUSE-01D'
LINT = os.path.join(ROOT, 'scripts', 'contrato_lint.py')


def rodar(out):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fatiar_auto.py'),
                        CONTRATO, REPO, out], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, ('fatiar_auto rc', r.returncode, r.stderr[-400:])
    return json.load(open(os.path.join(out, 'plano.json')))


def digest(out):
    h = hashlib.sha256()
    for f in sorted(os.listdir(out)):
        h.update(f.encode()); h.update(open(os.path.join(out, f), 'rb').read())
    return h.hexdigest()


def main():
    a, b = tempfile.mkdtemp(prefix='fa-a-'), tempfile.mkdtemp(prefix='fa-b-')
    plano = rodar(a)
    fatias = plano['fatias']
    assert len(fatias) >= 3, ('poucas fatias', len(fatias))
    ids = [f['id'] for f in fatias]
    assert len(set(ids)) == len(ids), 'ids duplicados'
    for i, f in enumerate(fatias):
        esperado = [] if i == 0 else [fatias[i - 1]['id']]
        assert f['deps'] == esperado, ('DAG nao serial', f['id'], f['deps'])
        micro = os.path.join(a, f['arquivo'])
        assert os.path.isfile(micro), ('micro-missao ausente', micro)
        r = subprocess.run([sys.executable, LINT, micro], capture_output=True, text=True)
        assert r.returncode == 0, ('contrato_lint reprovou', f['id'], r.stdout[-300:])
        txt = open(micro, encoding='utf-8').read()
        refs = re.findall(r'\b([\w./-]+\.(?:js|mjs|py)):(\d+)\b', txt)
        assert refs, ('micro-missao sem mapa de linhas arquivo:N', f['id'])
        for fn, n in refs:
            p = os.path.join(REPO, fn)
            assert os.path.isfile(p), ('mapa cita arquivo inexistente', fn)
            total = sum(1 for _ in open(p, encoding='utf-8', errors='replace'))
            assert 1 <= int(n) <= total, ('linha fora do arquivo', fn, n, total)
        arqs = set(fn for fn, _ in refs)
        assert len(arqs) <= 3, ('fatia toca arquivos demais', f['id'], arqs)
    rodar(b)
    assert digest(a) == digest(b), 'saida nao deterministica (sem LLM, deve ser identica)'
    print(f'ACEITE-FATIA-AUTO OK: {len(fatias)} fatias, DAG serial, lint ok, mapa real, deterministico')


if __name__ == '__main__':
    main()

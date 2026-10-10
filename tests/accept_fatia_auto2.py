#!/usr/bin/env python3
"""Aceite v2 RD-HARN-FATIA-AUTO-02 (supervisor; o worker NAO edita). Qualidade, nao so forma."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTRATO = '/opt/mission-events/missao-rd-gb-abuse-01c.md'
REPO = '/home/worker/wt-RD-GB-ABUSE-01D'
TRIVIAL = re.compile(r'^\s*(test\s+-[fde]\s+\S+|true|:|ls\b.*|echo\b.*)\s*$')


def stops_de(txt):
    bloco = re.search(r'```harness-stop\n(.*?)```', txt, re.S)
    out = []
    for l in (bloco.group(1) if bloco else '').split('\n'):
        if l.startswith('cmd '):
            c = l[4:]
            c = re.sub(r'^cd\s+\S+\s*&&\s*', '', c)
            out.append(c)
    return out


def main():
    out = tempfile.mkdtemp(prefix='fa2-')
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fatiar_auto.py'), CONTRATO, REPO, out],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, ('rc', r.returncode, r.stderr[-300:])
    plano = json.load(open(os.path.join(out, 'plano.json')))
    contrato_stops = stops_de(open(CONTRATO, encoding='utf-8').read())
    herdados = set()
    for f in plano['fatias']:
        txt = open(os.path.join(out, f['arquivo']), encoding='utf-8').read()
        # 1. mapa: cada simbolo citado precisa aparecer LITERALMENTE na linha apontada
        for fn, n, sim in re.findall(r'`([\w./-]+\.(?:js|mjs|py)):(\d+)`[^`\n]*`([^`\n]+)`', txt):
            linhas = open(os.path.join(REPO, fn), encoding='utf-8', errors='replace').read().split('\n')
            assert sim in linhas[int(n) - 1], ('mapa mente: simbolo nao esta na linha', f['id'], fn, n, sim)
            assert sim not in ('ausente', 'body', 'req', 'res', 'const', 'function'), ('simbolo generico', sim)
        assert re.search(r'`[\w./-]+\.(?:js|mjs|py):\d+`[^`\n]*`[^`\n]+`', txt), ('fatia sem mapa simbolo+linha', f['id'])
        # 2. stops da fatia: nenhum so-trivial, e ao menos 1 deve ser especifico da entrega
        ss = stops_de(txt)
        assert ss, ('fatia sem stops', f['id'])
        nao_triviais = [s for s in ss if not TRIVIAL.match(s)]
        assert nao_triviais, ('stops so triviais (VACUO)', f['id'], ss)
        herdados.update(s for s in ss if s in contrato_stops)
    # 3. todo stop do contrato aparece em pelo menos uma fatia (nada se perde)
    perdidos = [s for s in contrato_stops if s not in herdados]
    assert not perdidos, ('stops do contrato perdidos', perdidos)
    # 4. a ultima fatia carrega o stop do relatorio e do commit
    ult = open(os.path.join(out, plano['fatias'][-1]['arquivo']), encoding='utf-8').read()
    assert 'RELATORIO' in ult and 'git log -1' in ult, 'ultima fatia sem relatorio/commit'
    print(f'ACEITE-FATIA-AUTO2 OK: {len(plano["fatias"])} fatias, mapa literal, stops reais herdados')


if __name__ == '__main__':
    main()

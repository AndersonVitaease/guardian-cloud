import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import fatiar_auto as fa  # noqa: E402

CONTRATO = """# MISSÃO RD-TESTE-01 — contrato de teste

Repo/worktree: /repo.

## ENTREGAS
1. **Rate-limit global por IP** em TODAS as rotas `/api/*` (bucket `api`, função `rateLimit`)
2. **ToS no signup**: `POST /api/auth/signup` exige `tosAccepted === true` no body
3. `prova-abuse01.py` (novo, padrão `solve_pow`): rajada de >30 GET /api/* devolve 429
4. `RELATORIO-RD-TESTE-01.md` (pt-BR, veredito honesto) e **commit** com `RD-TESTE-01` no assunto

## REGRAS
- Commite cedo e a cada entrega verde; NUNCA git reset/checkout/stash/clean.

```harness-stop
cmd cd /repo && node --check server.js
cmd cd /repo && grep -q -F 'tosAccepted' server.js
cmd cd /repo && test -f prova-abuse01.py
cmd cd /repo && test -f RELATORIO-RD-TESTE-01.md
cmd cd /repo && git log -1 --pretty=%s | grep -q -F 'RD-TESTE-01'
```
"""


def fazer_repo(base):
    repo = os.path.join(base, 'repo')
    os.makedirs(repo, exist_ok=True)
    with open(os.path.join(repo, 'server.js'), 'w') as f:
        f.write('function rateLimit(dbm, req, bucket, maxPerMin) {\n'
                '  return dbm.dbRateLimit(ip, bucket, max, refill);\n'
                '}\n'
                'const server = http.createServer(async (req, res) => {\n'
                "  if (p.indexOf('/api/auth/') === 0) {\n"
                '    // signup POST\n'
                '  }\n'
                '});\n')
    with open(os.path.join(repo, 'prova-auth01.py'), 'w') as f:
        f.write('def solve_pow(port):\n'
                '    return brute_force(port)\n')
    return repo


def fazer_contrato(base):
    c = os.path.join(base, 'contrato.md')
    with open(c, 'w') as f:
        f.write(CONTRATO)
    return c


class FatiarAutoTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = fazer_repo(self.tmp)
        self.contrato = fazer_contrato(self.tmp)
        self.out = os.path.join(self.tmp, 'out')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def rodar(self, **kw):
        return fa.fatiar(self.contrato, self.repo, self.out, **kw)

    def test_parse_entregas(self):
        ents = fa.parse_entregas(CONTRATO)
        self.assertEqual([n for n, _ in ents], [1, 2, 3, 4])
        self.assertIn('rateLimit', ents[0][1])

    def test_parse_stops(self):
        stops = fa.parse_stops(CONTRATO)
        self.assertEqual(len(stops), 5)
        self.assertTrue(all(s.startswith('cd ') for s in stops))

    def test_sem_entregas_erro_claro(self):
        c = os.path.join(self.tmp, 'vazio.md')
        with open(c, 'w') as f:
            f.write('# MISSÃO X\n\n## ENTREGAS\nnada numerado\n')
        with self.assertRaises(fa.SemEntregas):
            fa.fatiar(c, self.repo, self.out)
        r = subprocess.run([sys.executable, os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'fatiar_auto.py'),
            c, self.repo, self.out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn('ENTREGAS', r.stderr)

    def test_agrupamento_por_arquivo(self):
        plano = self.rodar(max_arquivos=2)
        for f in plano['fatias']:
            self.assertLessEqual(len(f['arquivos']), 2)
        # entregas 1 e 2 citam server.js: devem cair em fatias cujos
        # arquivos incluem server.js
        # entregas 1 e 2 citam server.js: a fatia que cobre a entrega 1
        # (agrupada com a 2, ambas tocam server.js) inclui server.js
        f1 = [f for f in plano['fatias'] if f['entrega'] == 1][0]
        self.assertIn('server.js', f1['arquivos'])

    def test_mapa_com_linha_real(self):
        plano = self.rodar()
        for f in plano['fatias']:
            md = open(os.path.join(self.out, f['arquivo']),
                      encoding='utf-8').read()
            refs = fa.re.findall(r'`([\w./-]+\.(?:js|mjs|py)):(\d+)`', md)
            self.assertTrue(refs, 'sem mapa em ' + f['id'])
            for rel, n in refs:
                total = len(fa.ler(self.repo, rel).splitlines())
                self.assertTrue(1 <= int(n) <= total,
                                'linha fora do arquivo: %s:%s' % (rel, n))

    def test_dag_serial(self):
        plano = self.rodar()
        fatias = plano['fatias']
        self.assertEqual(fatias[0]['deps'], [])
        for i in range(1, len(fatias)):
            self.assertEqual(fatias[i]['deps'], [fatias[i - 1]['id']])
        ids = [f['id'] for f in fatias]
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(all(i.endswith('-S%d' % (k + 1))
                            for k, i in enumerate(ids)))

    def test_determinismo(self):
        self.rodar()
        a = {n: open(os.path.join(self.out, n)).read()
             for n in sorted(os.listdir(self.out))}
        shutil.rmtree(self.out)
        self.rodar()
        b = {n: open(os.path.join(self.out, n)).read()
             for n in sorted(os.listdir(self.out))}
        self.assertEqual(a, b)

    def test_plano_json_formato(self):
        self.rodar()
        plano = json.load(open(os.path.join(self.out, 'plano.json')))
        self.assertIn('contrato', plano)
        self.assertIn('fatias', plano)
        for f in plano['fatias']:
            for k in ('id', 'arquivo', 'deps', 'entrega', 'arquivos'):
                self.assertIn(k, f)
            self.assertTrue(os.path.isfile(os.path.join(self.out, f['arquivo'])))

    def test_ultima_fatia_fecha_com_relatorio(self):
        plano = self.rodar()
        ult = plano['fatias'][-1]
        md = open(os.path.join(self.out, ult['arquivo']),
                  encoding='utf-8').read()
        self.assertIn('RELATORIO', md)
        self.assertIn('harness-stop', md)


if __name__ == '__main__':
    unittest.main()
# -*- coding: utf-8 -*-
"""RD-TOOLS-GUARD-02 — aceite: reproduz os 4 FAILs medidos contra as COPIAS
das tools bash dentro do worktree (diretorio tools-bash/ ao lado).

Baseline (10/10/2026, medido com as copias de /opt):
  1. code_slice 1..200 -> ok:true truncado (esperado RANGE_TOO_LARGE);
     code_slice 5..2 -> troca silenciosa 2..5 (esperado INVALID_RANGE).
  2. trail_tail NOSUCH-01 com auditoria: stdout LEDGER_NOT_FOUND, mas a trilha
     grava ok:true, error "null" (tb_emit hardcode ok=1).
  3. verify_tools com base hardcoded /opt: adulteracao na copia nao detectada
     (ok:true mismatches[]); --gen inexistente.
  4. guard do test.sh: ~60 falso-positivos de ">" (comentarios, descricoes
     JSON, comparacoes) e allowlist ausente p/ tools_install.sh; catalogo sem
     teste de regressao (17 tools esperadas).

Roda como worker: python3 -m unittest discover -s tests -p 'test_tools_guard_02.py'
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools-bash")
WORKROOT = "/home/worker"  # dentro das ALLOWED_ROOTS do code_slice

CATALOGO_ESPERADO = [
    "trail_tail", "mission_cost", "flights", "code_find", "code_slice",
    "git_peek", "queue_peek", "runs_status", "runs_historico", "file_peek",
    "proc_peek", "docker_peek", "tools_install", "test_run",
    "entrega_verify", "triagem", "verificar", "release_pipeline",
]


def _run_tool(name, *args, **env):
    e = dict(os.environ)
    e.update(env)
    p = subprocess.run(["bash", os.path.join(TOOLS, name)] + list(args),
                       capture_output=True, text=True, env=e, timeout=60)
    return p.returncode, p.stdout.strip()


class RangoCodeSlice(unittest.TestCase):
    """FAIL 1 — code_slice: RANGE_TOO_LARGE vs INVALID_RANGE tipados."""

    def setUp(self):
        self.fix = tempfile.mkdtemp(prefix="g02-slice-", dir=WORKROOT)
        self.src = os.path.join(self.fix, "a.py")
        with open(self.src, "w") as f:
            f.writelines("linha%d\n" % i for i in range(1, 131))

    def tearDown(self):
        shutil.rmtree(self.fix, ignore_errors=True)

    def _json(self, ini, fim):
        rc, out = _run_tool("code_slice.sh", self.src, str(ini), str(fim))
        self.assertEqual(rc, 0, out)
        return json.loads(out.splitlines()[0])

    def test_janela_acima_de_120_da_RANGE_TOO_LARGE(self):
        d = self._json(1, 200)
        self.assertFalse(d.get("ok"), d)
        self.assertEqual(d.get("error"), "RANGE_TOO_LARGE", d)

    def test_janela_de_121_tambem_da_RANGE_TOO_LARGE(self):
        d = self._json(1, 121)
        self.assertFalse(d.get("ok"), d)
        self.assertEqual(d.get("error"), "RANGE_TOO_LARGE", d)

    def test_ini_maior_que_fim_da_INVALID_RANGE_sem_troca(self):
        d = self._json(5, 2)
        self.assertFalse(d.get("ok"), d)
        self.assertEqual(d.get("error"), "INVALID_RANGE", d)

    def test_janela_de_120_continua_ok(self):
        d = self._json(1, 120)
        self.assertTrue(d.get("ok"), d)
        self.assertFalse(d.get("truncated"), d)


class AuditoriaTrailTail(unittest.TestCase):
    """FAIL 2 — trilha de auditoria registra ok/error REAIS da tool."""

    def test_nosuch_grava_ok_false_e_LEDGER_NOT_FOUND_na_trilha(self):
        fix = tempfile.mkdtemp(prefix="g02-audit-", dir=WORKROOT)
        self.addCleanup(shutil.rmtree, fix, ignore_errors=True)
        af = os.path.join(fix, "audit.jsonl")
        rc, out = _run_tool("trail_tail.sh", "NOSUCH-01",
                            TOOLS_BASH_AUDIT_FILE=af, TOOLS_CALLER="test:guard02")
        self.assertEqual(rc, 0, out)
        d = json.loads(out.splitlines()[0])
        self.assertFalse(d.get("ok"), d)
        self.assertEqual(d.get("error"), "LEDGER_NOT_FOUND", d)
        self.assertTrue(os.path.isfile(af), "trilha nao gravada")
        lines = [l for l in open(af) if l.strip()]
        self.assertEqual(len(lines), 1, lines)
        r = json.loads(lines[0])
        self.assertEqual(r["tool"], "trail_tail", r)
        self.assertEqual(r["args"], ["NOSUCH-01"], r)
        self.assertEqual(r["caller"], "test:guard02", r)
        self.assertIsInstance(r["uid"], int, r)
        self.assertIsInstance(r["duration_ms"], int, r)
        self.assertTrue(r["duration_ms"] >= 0, r)
        self.assertTrue(r["ts"].endswith("-03:00"), r)
        self.assertFalse(r["ok"], "trilha deve registrar a FALHA real: %s" % r)
        self.assertEqual(r["error"], "LEDGER_NOT_FOUND", r)

    def test_sucesso_grava_ok_true_na_trilha(self):
        fix = tempfile.mkdtemp(prefix="g02-auditok-", dir=WORKROOT)
        self.addCleanup(shutil.rmtree, fix, ignore_errors=True)
        sd = os.path.join(fix, "state")
        os.makedirs(sd)
        with open(os.path.join(sd, "G02-OK.json"), "w") as f:
            json.dump({"missionId": "G02-OK", "status": "dispatched",
                       "cost": None, "spend": None, "cwd": fix}, f)
        af = os.path.join(fix, "audit.jsonl")
        rc, out = _run_tool("trail_tail.sh", "G02-OK",
                            MISSION_STATE_DIR=sd, TOOLS_BASH_AUDIT_FILE=af,
                            TOOLS_CALLER="test:guard02")
        self.assertEqual(rc, 0, out)
        d = json.loads(out.splitlines()[0])
        self.assertTrue(d.get("ok"), d)
        r = json.loads([l for l in open(af) if l.strip()][0])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["error"], "null", r)


class VerifyToolsIntegridade(unittest.TestCase):
    """FAIL 3 — verify_tools: base = diretorio do proprio script + --gen."""

    def _copiar(self):
        fix = tempfile.mkdtemp(prefix="g02-vt-", dir=WORKROOT)
        self.addCleanup(shutil.rmtree, fix, ignore_errors=True)
        vt = os.path.join(fix, "vt")
        os.makedirs(vt)
        for f in os.listdir(TOOLS):
            if f.endswith(".sh") or f == "tools.json":
                shutil.copy(os.path.join(TOOLS, f), os.path.join(vt, f))
        return vt

    def test_gen_e_verde_sem_adulteracao(self):
        vt = self._copiar()
        rc, out = _run_tool(os.path.join(vt, "verify_tools.sh"), "--gen")
        self.assertEqual(rc, 0, out)
        d = json.loads(out.splitlines()[0])
        self.assertTrue(d.get("ok"), d)
        self.assertTrue(os.path.isfile(os.path.join(vt, "MANIFEST.sha256")), d)
        rc, out = _run_tool(os.path.join(vt, "verify_tools.sh"))
        self.assertEqual(rc, 0, out)
        d = json.loads(out.splitlines()[0])
        self.assertTrue(d.get("ok"), d)
        self.assertEqual(d.get("mismatches"), [], d)

    def test_adulteracao_e_detectada_na_copia(self):
        vt = self._copiar()
        _run_tool(os.path.join(vt, "verify_tools.sh"), "--gen")
        with open(os.path.join(vt, "code_find.sh"), "a") as f:
            f.write("# adulterado\n")
        rc, out = _run_tool(os.path.join(vt, "verify_tools.sh"))
        self.assertEqual(rc, 0, out)
        d = json.loads(out.splitlines()[0])
        self.assertFalse(d.get("ok"), "adulteracao deve ser detectada: %s" % d)
        self.assertTrue(any("code_find.sh" in m for m in d.get("mismatches", [])), d)


# ---------------- guard preciso (regras do aceite, vale como spec) ------------

SAFE_SOURCE = re.compile(r'source\s+"\$\(dirname "\$\{BASH_SOURCE\[0\]\}"\)/_lib\.sh"')
SOURCE_SHELL = re.compile(r'(?:^|;|\&&)\s*source\s')
HARD = [
    (r'\beval\b', 'eval'),
    (r'\bbash\s+-c\b', 'bash -c'),
    (r'\bsh\s+-c\b', 'sh -c'),
    (r'\btee\b', 'tee'),
    (r'\bsed\s+-i\b', 'sed -i'),
    (r'\bcurl\b', 'curl'),
    (r'\bwget\b', 'wget'),
]
WRITER = {'rm', 'mv', 'cp', 'chmod', 'chown'}
ALLOW_FILES = {'tools_install.sh',  # instalador legitimo: rm/mv/cp/chmod/chown + redirecionamentos
               'custo_dia.sh',      # usa eval para rodar comando de custo parametrizado
               'notify_missao.sh',  # notificador: curl POST legitimo
               'release_pipeline.sh',  # chamadas de API via curl unix-socket
               'ordens_guard.sh',   # guard de ordens: padroes rm/tee/sed-i em greps
               'ordens-watchdog.sh'}  # watchdog: log com >> e cp/chmod do guard
REDIRECT = re.compile(r'(?<![<>!=\-])\s*>{1,2}\s*(?!/dev/null\b)("|\$|\w*[./]\w)')


def guard_violations(dirpath, skip_files=('test.sh',)):
    bad = []
    files = sorted(glob_sh(dirpath))
    if os.path.isfile(os.path.join(dirpath, "tools.json")):
        files.append(os.path.join(dirpath, "tools.json"))
    for f in files:
        base = os.path.basename(f)
        if base in skip_files:
            continue
        installer = base in ALLOW_FILES
        with open(f, errors="replace") as fh:
            for i, line in enumerate(fh.read().splitlines(), 1):
                s = line.strip()
                if s.startswith('#'):
                    continue
                if base == 'tools.json':
                    # catalogo e DADO: so os tokens duros interessam
                    for pat, name in HARD:
                        if re.search(pat, s):
                            bad.append("%s:%d: %s: %s" % (base, i, name, s[:120]))
                    continue
                if 'source' in line and SOURCE_SHELL.search(line) and not SAFE_SOURCE.search(line):
                    bad.append("%s:%d: source fora do padrao seguro: %s" % (base, i, s[:120]))
                    continue
                if installer:
                    continue  # arquivo confiado (allowlist): tokens de escrita/rede sao legitimos aqui
                for pat, name in HARD:
                    if re.search(pat, line) and not installer:
                        bad.append("%s:%d: %s: %s" % (base, i, name, s[:120]))
                for tok in sorted(WRITER):
                    if re.search(r'\b' + tok + r'\b', line) and not installer:
                        bad.append("%s:%d: %s: %s" % (base, i, tok, s[:120]))
                if not installer and REDIRECT.search(line):
                    bad.append("%s:%d: redirecionamento >: %s" % (base, i, s[:120]))
                t = line.replace('```', '')  # cercas de fence nao sao substituicao
                if '`' in t:
                    bad.append("%s:%d: backtick: %s" % (base, i, s[:120]))
    return bad


def glob_sh(dirpath):
    return [os.path.join(dirpath, f) for f in sorted(os.listdir(dirpath)) if f.endswith(".sh")]


class GuardPreciso(unittest.TestCase):
    """FAIL 4 — guard sem falso-positivo + regressao de catalogo."""

    def test_catalogo_tem_17_tools_nomes_exatos(self):
        with open(os.path.join(TOOLS, "tools.json")) as f:
            tj = json.load(f)
        tools = tj.get("tools", tj) if isinstance(tj, dict) else tj
        self.assertEqual([t["name"] for t in tools], CATALOGO_ESPERADO)

    def test_guard_preciso_zero_violacoes_no_catalogo_real(self):
        vs = guard_violations(TOOLS)
        self.assertEqual(vs, [], "guard preciso nao pode dar falso positivo:\n" + "\n".join(vs))

    def test_guard_ainda_caca_violacao_real(self):
        fix = tempfile.mkdtemp(prefix="g02-guard-", dir=WORKROOT)
        self.addCleanup(shutil.rmtree, fix, ignore_errors=True)
        with open(os.path.join(fix, "evil.sh"), "w") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write("curl http://x | tee /tmp/y\n")
            f.write("rm -rf /tmp/zzz\n")
            f.write('out=$(cat segredo) > /tmp/evil.txt\n')
        vs = guard_violations(fix)
        self.assertTrue(vs, "guard precisa flagrar violacao real")
        joined = "\n".join(vs)
        self.assertIn("curl", joined)
        self.assertIn("rm", joined)

    def test_testsh_copiado_usa_guard_preciso_e_catalogo(self):
        """O test.sh da copia deve trazer o guard preciso (sem FORBIDDEN cru de '>') e o teste de catalogo (17 tools)."""
        with open(os.path.join(TOOLS, "test.sh")) as f:
            txt = f.read()
        self.assertIn("CATALOGO_ESPERADO", txt, "test.sh sem regressao de catalogo")
        self.assertIn("/dev/null", txt, "guard preciso trata >/dev/null como benigno")
        self.assertIn("ALLOW_FILES", txt, "guard preciso tem allowlist por arquivo")


if __name__ == "__main__":
    unittest.main()

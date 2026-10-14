#!/usr/bin/env python3
# Cura DOCS-GUIA-UPDATE-01 (mecanico, harness-s2): GUIA-ROTA-DESPACHO.md ganha a secao
# "provado em producao 14/10" — portas finais, rota travada em codigo, escada A/V.
import subprocess, os, json, sys
REPO = "/home/worker/harness-s2/harness-s2"
GUIA = os.path.join(REPO, "GUIA-ROTA-DESPACHO.md")
REL = os.path.join(REPO, "runs", "mecanico", "RELATORIO-DOCS-GUIA-UPDATE-01.md")

def sh(c):
    p = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr

linhas = ["# RELATORIO-DOCS-GUIA-UPDATE-01\n"]
secao = """
## Provado em produção (14/10 BRT)

- Missões rodadas pela rota mecânica hoje: rota única com avisos (herdr em tempo real, chat com latência) — ~20 missões PASS, 2 FAILs honestos (documentados): DESP-FIXTURE-03 (patch cego em fixture; lição: análise = contrato) e BYOK-CASE-01 v1 (permissão; lição: chown antes do conserto).
- Rota travada em código: tests/test_rota_despacho.py (6 testes) — porta fora do desenho fica vermelha na suite.
- Provas herméticas: guardian-app (9 provas verdes pós BYOK-CASE-01), guardian-cloud (prova-guardian-cloud.py, npm test 6 suites), harness-s2 (lint da porta + test_rota_despacho).
- Escada A/V completa (US$0): ffmpeg (d1), manim (d2), narrador espeak-ng (d3), áudio pipeline, deliverable docs/demos/apresentacao-guardian.mp4.
- Espera de decisão do operador: executor de missões de contrato (a rota mecânica cobre curas determinísticas; análise/julgamento precisa de executor autorizado).
"""
src = open(GUIA).read()
if "Provado em produção (14/10" not in src:
    open(GUIA, "a").write(secao)
    linhas.append("secao anexada ao GUIA")
else:
    linhas.append("secao ja presente")
rc, out = sh("cd %s && grep -c 'Provado em producao\\|Provado em produção' GUIA-ROTA-DESPACHO.md" % REPO)
ok = out.strip() != "0"
linhas.append("verificacao: %s" % ("OK secao no GUIA" if ok else "FALHOU"))
open(REL, "w").write("\n".join(linhas) + "\n")
print(json.dumps({"ok": ok, "guia": GUIA, "relatorio": REL}))
sys.exit(0 if ok else 1)
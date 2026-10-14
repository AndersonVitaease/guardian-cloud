# -*- coding: utf-8 -*-
"""Testes do gate de lint bloqueante em scripts/despachar_missao.py (RD-HARN-LINT-ENFORCE-01).

Importa a CÓPIA do worktree por importlib (caminho), nunca o arquivo vivo de /opt.
Exercita comportamento REAL: contrato ruim -> LINT_RECUSADO; baseline toda verde ->
VACUO_STOPS_VERDES; contrato válido passa pelo gate do lint.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(os.path.join(HERE, "..", "scripts", "despachar_missao.py"))
LINT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "contrato_lint.py")  # SUITE-DEBT-01(d) — tests/ -> raiz -> scripts


def _load():
    global _SH_REAL
    spec = importlib.util.spec_from_file_location("despachar_missao_wt", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _SH_REAL = mod.sh  # sh original, antes de qualquer fake
    return mod


CONTRATO_OK = """# MISSÃO TESTE-OK-01 — contrato válido

## Objetivo
Entrega de teste com stop relativo ao worktree e não trivial.

```harness-stop
cmd cd {worktree} && test -f RELATORIO-TESTE-OK-01.md && grep -q -F CONCLUIDO RELATORIO-TESTE-OK-01.md
```

PROIBIDO usar git reset/checkout/stash/clean.
"""

CONTRATO_STOP_RELATIVO = """# MISSÃO TESTE-REL-01 — stop relativo sem cd /abs

## Objetivo
Stop relativo (sem `cd /abs &&`) deve ser recusado pelo lint.

```harness-stop
cmd test -f RELATORIO.md
```

PROIBIDO usar git reset/checkout/stash/clean.
"""

CONTRATO_FENCE_ABERTO = """# MISSÃO TESTE-FENCE-01 — fence aberto

## Objetivo
Fence sem fechamento deve ser recusado.

```harness-stop
cmd test -f RELATORIO.md
"""

CONTRATO_ZERO_STOPS = """# MISSÃO TESTE-ZERO-01 — sem stops

## Objetivo
Nenhum fence harness-stop: recusa.

PROIBIDO usar git reset/checkout/stash/clean.
"""

CONTRATO_TRIVIAL = """# MISSÃO TESTE-TRIV-01 — stop trivial

## Objetivo
Stop só com `test -f` é trivial: recusa.

```harness-stop
cmd cd {worktree} && test -f README.md
```

PROIBIDO usar git reset/checkout/stash/clean.
"""


def _write(tmp_path, texto, worktree):
    p = tmp_path / "contrato.md"
    p.write_text(texto.format(worktree=str(worktree)), encoding="utf-8")
    return str(p)


def _lint_cli(contrato_path):
    r = subprocess.run([sys.executable, LINT, contrato_path],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _lint_ok(contrato_path):
    """exit 0 do lint = contrato verde."""
    rc, out = _lint_cli(contrato_path)
    return rc == 0, out


def _tem_codigo(out, codigo):
    """O lint emite JSON de erros; verifica presença do código sem depender de formatação."""
    return codigo in out


def _tem_codigo(out, codigo):
    """O lint emite JSON de erros; verifica presença do código sem depender de formatação."""
    return codigo in out


def _run_main(mod, contrato, worktree, sh_fake=None):
    """Roda main() da cópia com --dry-run; geteuid falso (root) e sh opcionalmente falso.

    Isolamento: mod.os É o módulo os global — salvar/restaurar geteuid e sys.argv
    para não vazar estado entre testes (dependência de ordem).
    """
    real_geteuid = os.geteuid
    mod.os.geteuid = lambda: 0
    real_sh = mod.sh
    if sh_fake is not None:
        mod.sh = sh_fake
    real_argv = sys.argv
    sys.argv = ["despachar_missao.py", contrato, str(worktree), "--dry-run"]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.main()
    except SystemExit:
        pass
    finally:
        mod.sh = real_sh
        os.geteuid = real_geteuid
        sys.argv = real_argv
    return buf.getvalue() or None


_SH_REAL = None  # sh original do módulo, capturado antes de qualquer monkeypatch


def _sh_lint_real_resto(mod, cmd, timeout=60, resultado_resto=(0, "")):
    """Delega ao lint REAL (via _SH_REAL); demais comandos (baseline) retornam resultado_resto."""
    if LINT in cmd:
        return _SH_REAL(cmd, timeout)
    return resultado_resto


def test_lint_recusado_stop_relativo(tmp_path):
    """Stop relativo (sem cd /abs &&) -> despacho falha com LINT_RECUSADO (lint REAL)."""
    mod = _load()
    wt = tmp_path / "wt"
    wt.mkdir()
    c = _write(tmp_path, CONTRATO_STOP_RELATIVO, wt)
    rc, out = _lint_cli(c)
    assert rc != 0 and _tem_codigo(out, "STOP_RELATIVO")
    saida = _run_main(mod, c, wt,
                      sh_fake=lambda cmd, timeout=60: _sh_lint_real_resto(mod, cmd, timeout))
    assert saida is not None
    j = json.loads(saida)
    assert j["erro"] == "LINT_RECUSADO" and j["id"] == "TESTE-REL-01"
    assert "STOP_RELATIVO" in j["detalhe"]


def test_lint_recusado_fence_aberto_e_zero_stops(tmp_path):
    """Fence aberto e contrato sem stops -> recusa pelo lint (FENCE_ERRADA/SEM_STOP)."""
    wt = tmp_path / "wt"
    wt.mkdir()
    c1 = _write(tmp_path, CONTRATO_FENCE_ABERTO, wt)
    rc1, out1 = _lint_cli(c1)
    assert rc1 != 0 and (_tem_codigo(out1, "FENCE_ERRADA") or _tem_codigo(out1, "SEM_STOP"))
    c2 = _write(tmp_path, CONTRATO_ZERO_STOPS, wt)
    rc2, out2 = _lint_cli(c2)
    assert rc2 != 0 and _tem_codigo(out2, "SEM_STOP")


def test_lint_recusado_stop_trivial(tmp_path):
    """Stop só `test -f` -> STOP_SO_TRIVIAL -> recusa."""
    wt = tmp_path / "wt"
    wt.mkdir()
    c = _write(tmp_path, CONTRATO_TRIVIAL, wt)
    rc, out = _lint_cli(c)
    assert rc != 0 and _tem_codigo(out, "STOP_SO_TRIVIAL")


def test_contrato_valido_passa_pelo_gate_do_lint(tmp_path):
    """Contrato válido passa no lint; despacho NÃO falha com LINT_RECUSADO (baseline vermelha)."""
    mod = _load()
    wt = tmp_path / "wt"
    wt.mkdir()
    c = _write(tmp_path, CONTRATO_OK, wt)
    rc, out = _lint_cli(c)
    assert rc == 0, out
    saida = _run_main(mod, c, wt,
                      sh_fake=lambda cmd, timeout=60: _sh_lint_real_resto(mod, cmd, timeout, (1, "")))
    assert saida is not None
    j = json.loads(saida)
    assert j.get("ok") is True and j.get("dry_run") is True
    assert j.get("erro") != "LINT_RECUSADO"


def test_vacuo_stops_verdes_baseline_toda_verde(tmp_path):
    """Baseline com todos os stops verdes -> fail VACUO_STOPS_VERDES (sem flag que contorne)."""
    mod = _load()
    wt = tmp_path / "wt"
    wt.mkdir()
    c = _write(tmp_path, CONTRATO_OK, wt)
    rc, out = _lint_cli(c)
    assert rc == 0, out
    saida = _run_main(mod, c, wt,
                      sh_fake=lambda cmd, timeout=60: _sh_lint_real_resto(mod, cmd, timeout, (0, "")))
    assert saida is not None
    j = json.loads(saida)
    assert j["erro"] == "VACUO_STOPS_VERDES" and j["id"] == "TESTE-OK-01"
    src = io.open(SCRIPT, encoding="utf-8").read()
    assert "VACUO: todos os stops ja estao verdes" not in src  # aviso antigo removido


def test_lint_e_vacuo_sao_obrigatorios_sem_flag():
    """Nenhuma flag contorna o lint ou o vácio."""
    src = io.open(SCRIPT, encoding="utf-8").read()
    assert "--sem-lint" not in src
    assert "--forcar" not in src
    assert "fail(\"LINT_RECUSADO\"" in src
    assert "fail(\"VACUO_STOPS_VERDES\"" in src

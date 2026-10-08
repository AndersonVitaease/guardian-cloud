"""AUTORETRY-CLI-01 — fiação da flag --auto-retry no mission_run.py.

Testes diretos de parse/main (sem rodar o CLI como processo).
"""
import json

import mission_run


def _parse(argv):
    """Parse puro do argparse de main() (sem executar despacho)."""
    import argparse
    captured = {}
    orig = argparse.ArgumentParser.parse_args

    def fake(self, argv=None):
        captured["actions"] = list(self._actions)
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = fake
    try:
        mission_run.main(["--mission", "m", "--cwd", "c"])
    except SystemExit:
        pass
    finally:
        argparse.ArgumentParser.parse_args = orig
    ap = argparse.ArgumentParser()
    for act in captured["actions"]:
        if act.dest != "help":
            ap._add_action(act)
    return ap.parse_args(argv)


def test_default_zero():
    args = _parse(["--mission", "m.md", "--cwd", "/tmp/x"])
    assert args.auto_retry == 0


def test_parse_valor():
    args = _parse(["--mission", "m.md", "--cwd", "/tmp/x", "--auto-retry", "2"])
    assert args.auto_retry == 2


def test_conflito_memoria_exit2(capsys):
    rc = mission_run.main(["--mission", "m.md", "--cwd", "/tmp/x",
                           "--auto-retry", "1", "--memoria", "x"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "auto-retry" in err and ("memoria" in err or "memória" in err)


def test_despacho(monkeypatch, tmp_path):
    chamadas = []

    def fake_rodar(**kw):
        chamadas.append(kw)
        return {"veredito": "PASS"}

    import scripts.autoretry as _ar
    monkeypatch.setattr(_ar, "rodar_com_retry", fake_rodar)
    out = str(tmp_path / "agg.json")
    rc = mission_run.main(["--mission", "m.md", "--cwd", str(tmp_path),
                           "--auto-retry", "2", "--seed", "7",
                           "--budget", "1.5", "--max-turns", "30",
                           "--out", out])
    assert rc == 0
    assert len(chamadas) == 1
    kw = chamadas[0]
    assert kw["mission_path"] == "m.md"  # kwarg real da assinatura (scripts/autoretry.py)
    assert kw["base_cwd"] == str(tmp_path)
    assert kw["budget_total"] == 1.5
    assert kw["max_turns"] == 30
    assert kw["n_retries"] == 2
    assert kw["seed0"] == 7
    assert json.load(open(out)) == {"veredito": "PASS"}


def test_sem_flag_nao_despacha(monkeypatch, tmp_path):
    def fake_rodar(**kw):
        raise AssertionError("não deveria ser chamado sem --auto-retry")

    import scripts.autoretry as _ar
    monkeypatch.setattr(_ar, "rodar_com_retry", fake_rodar)
    contrato = tmp_path / "missao-x.md"
    contrato.write_text("# missao-x\n\nsem prova determinística\n", encoding="utf-8")
    rc = mission_run.main(["--mission", str(contrato), "--cwd", str(tmp_path)])
    assert rc in (0, 1)

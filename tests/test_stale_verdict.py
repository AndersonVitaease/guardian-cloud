# STOP-STALE-01B — veredito nunca stale (re-checar stops do disco no
# veredito e no retry). Fixture H1H2-REPORT-01: tick sem stops -> stops
# completam no disco -> veredito PASS fresco; auto-retry com resumo
# atualizado no disco -> nao re-despacha; stops:[] com contrato com stops
# -> erro tipado RESUMO_INVALIDO.
import json
import os

import pytest

import harness
from harness import (ResumoInvalido, parse_stop_conditions, retry_ou_veredito,
                     validar_resumo_stops, veredito_fresco)

CONTRATO = "# MISSÃO H1H2-REPORT-01\nblablabla\n```harness-stop\ncmd test -f entrega.md\ncmd grep -q pronto entrega.md\n```\n"


def _conds():
    return parse_stop_conditions(CONTRATO)


def test_veredito_rele_disco_pass_fresco(tmp_path):
    # tick sem stops: estado stale todo False, veredito seria FAIL...
    conds = _conds()
    done, state = harness.check_stop_conditions(conds, str(tmp_path))
    assert not done and not any(state.values())
    # ...stops completam no disco DEPOIS do último tick...
    (tmp_path / "entrega.md").write_text("pronto\n", encoding="utf-8")
    # ...veredito re-lê o disco: PASS fresco, não retry/FAIL.
    verdict, reason, state_f, evitado = veredito_fresco(
        "FAIL", "max_turns", conds, str(tmp_path), state)
    assert verdict == "PASS"
    assert reason == "stop_condition"
    assert evitado
    assert all(state_f.values())


def test_veredito_fail_continua_se_stops_pendentes(tmp_path):
    conds = _conds()
    verdict, reason, state_f, evitado = veredito_fresco(
        "FAIL", "max_turns", conds, str(tmp_path), {})
    assert verdict == "FAIL"
    assert not evitado
    assert not any(state_f.values())


def test_veredito_fail_com_stops_completas_e_bug_tipado(tmp_path):
    conds = _conds()
    (tmp_path / "entrega.md").write_text("pronto\n", encoding="utf-8")
    # invariante (a): FAIL com stops completas ao vivo é PROIBIDO —
    # veredito_fresco converte para PASS; o guard interno é bug tipado.
    verdict, _, _, _ = veredito_fresco("FAIL", "vagueio", conds, str(tmp_path), {})
    assert verdict == "PASS"


def test_resumo_stops_vazio_erro_tipado():
    conds = _conds()
    with pytest.raises(ResumoInvalido):
        validar_resumo_stops(conds, [])
    validar_resumo_stops(conds, [{"kind": "cmd", "ok": False}])
    validar_resumo_stops([], [])


def test_retry_resumo_stale_stops_vazio_erro_tipado(tmp_path):
    # resumo stale com stops:[] mas contrato com stops -> RESUMO_INVALIDO
    resumo = {"veredito": "FAIL", "motivo": "max_turns", "stop_conditions": []}
    with pytest.raises(ResumoInvalido):
        retry_ou_veredito(resumo, _conds(), str(tmp_path))


def test_retry_nao_re_despacha_quando_stops_completaram(tmp_path):
    conds = _conds()
    # tentativa anterior: FAIL com stops pendentes registradas no resumo...
    resumo = {"veredito": "FAIL", "motivo": "max_turns",
              "stop_conditions": [{"kind": "cmd", "ok": False},
                                  {"kind": "cmd", "ok": False}]}
    # ...stops completam no disco no intervalo antes do retry...
    (tmp_path / "entrega.md").write_text("pronto\n", encoding="utf-8")
    # ...retry re-lê o disco: vira veredito (PASS), não nova tentativa.
    acao, motivo = retry_ou_veredito(resumo, conds, str(tmp_path))
    assert acao == "veredito"
    assert motivo == "stop_condition_stale"


def test_retry_despacha_quando_stops_realmente_pendentes(tmp_path):
    conds = _conds()
    resumo = {"veredito": "FAIL", "motivo": "max_turns",
              "stop_conditions": [{"kind": "cmd", "ok": False},
                                  {"kind": "cmd", "ok": False}]}
    acao, motivo = retry_ou_veredito(resumo, conds, str(tmp_path))
    assert acao == "retry"


def test_retry_resumo_pass_nao_re_despacha(tmp_path):
    resumo = {"veredito": "PASS", "motivo": "stop_condition",
              "stop_conditions": [{"kind": "cmd", "ok": True}]}
    acao, motivo = retry_ou_veredito(resumo, _conds(), str(tmp_path))
    assert acao == "veredito"
"""HARNESS-LATENCIA-MARKER-01 — dt do stream real + marker multi-token recusado."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import bridge_sse
import harness
from test_bridge_sse import FakeLedger, sse, base_events


def test_stream_2_eventos_dt_cobre_span():
    """dt ≥ tempo entre 1º e último evento (reader injetável com sleep)."""
    span = 0.30
    def reader(body):
        evs = sse(base_events(("a",)))
        time.sleep(span)
        return evs + sse(base_events(("b",))[2:])
    d, usd, dt, retries = bridge_sse.call_bridge_stream(
        [], "sys", "m", FakeLedger(), reader=reader)
    assert dt >= span * 0.9, f"dt={dt:.4f} < span={span}"


def test_stream_1_evento_dt_cobre_tempo_do_evento():
    t_ev = 0.15
    def reader(body):
        time.sleep(t_ev)
        return sse(base_events(("só",)))
    d, usd, dt, retries = bridge_sse.call_bridge_stream(
        [], "sys", "m", FakeLedger(), reader=reader)
    assert dt >= t_ev * 0.9, f"dt={dt:.4f} < t_ev={t_ev}"


def test_marker_multi_token_vira_value_error(tmp_path):
    # path com espaço e inexistente → recusa explícita (não marker=1ª-palavra)
    with pytest.raises(ValueError, match="multi-token"):
        harness.parse_stop_conditions(
            "```harness-stop\nmarker latencia_marker "
            f"{tmp_path / 'nao existe.py'}\n```")


def test_marker_1_token_valido_parseia_igual():
    conds = harness.parse_stop_conditions(
        "```harness-stop\nmarker PASS rel.md\n```")
    assert conds == [{"kind": "marker", "marker": "PASS", "path": "rel.md"}]


def test_cmd_file_cmdout_inalterados():
    conds = harness.parse_stop_conditions(
        "```harness-stop\nfile a.txt\ncmd echo oi\n"
        "cmdout fail 0 :: cat r.txt\n```")
    assert [c["kind"] for c in conds] == ["file", "cmd", "cmdout"]
    assert conds[0] == {"kind": "file", "path": "a.txt"}
    assert conds[1] == {"kind": "cmd", "cmd": "echo oi"}
    assert conds[2] == {"kind": "cmdout", "marker": "fail 0", "cmd": "cat r.txt"}

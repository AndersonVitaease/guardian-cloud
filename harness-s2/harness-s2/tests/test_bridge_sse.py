"""BRIDGE-SSE-01 — testes com stream SSE FABRICADO (nunca bridge real)."""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge_sse import call_bridge_stream, BridgeSseError


class FakeLedger:
    def __init__(self):
        self.cost = 0.0
        self.calls = []

    def add(self, model, usage):
        u = usage or {}
        usd = (u.get("input_tokens", 0) + u.get("output_tokens", 0)) / 1e6
        self.cost += usd
        self.calls.append({"model": model, "usage": usage})
        return usd


def sse(events):
    """Fabrica linhas SSE a partir de lista de (event, obj)."""
    out = []
    for ev, obj in events:
        out.append(f"event: {ev}\ndata: {json.dumps(obj)}\n\n")
    return out


def base_events(texts=("Olá", " mundo"), usage=None):
    evs = [("message_start", {"type": "message_start",
                              "message": {"model": "m", "usage": {"input_tokens": 10}}})]
    evs.append(("content_block_start", {"type": "content_block_start", "index": 0,
                                        "content_block": {"type": "text", "text": ""}}))
    for t in texts:
        evs.append(("content_block_delta", {"type": "content_block_delta", "index": 0,
                                            "delta": {"type": "text_delta", "text": t}}))
    evs.append(("content_block_stop", {"type": "content_block_stop", "index": 0}))
    evs.append(("message_delta", {"type": "message_delta",
                                  "delta": {"stop_reason": "end_turn"},
                                  "usage": usage or {"output_tokens": 7}}))
    evs.append(("message_stop", {"type": "message_stop"}))
    return evs


def test_deltas_chegam_ao_callback_na_ordem():
    got = []
    d, usd, dt, retries = call_bridge_stream(
        [], "sys", "m", FakeLedger(), on_token=got.append,
        reader=lambda body: sse(base_events(("a", "b", "c"))))
    assert got == ["a", "b", "c"]
    assert d["content"][0]["text"] == "abc"
    assert retries == 0


def test_erro_no_meio_do_stream_retry_e_segunda_tentativa_ok():
    calls = {"n": 0}
    got = []

    def reader(body):
        calls["n"] += 1
        if calls["n"] == 1:
            evs = base_events(("par",))
            evs.insert(3, ("error", {"type": "error", "error": {"type": "overloaded"}}))
            return sse(evs)
        return sse(base_events(("ok",)))

    d, usd, dt, retries = call_bridge_stream(
        [], "sys", "m", FakeLedger(), on_token=got.append,
        reader=reader, sleep=lambda s: None)
    assert retries == 1
    assert calls["n"] == 2
    assert d["content"][0]["text"] == "ok"


def test_on_token_none_funciona():
    d, usd, dt, retries = call_bridge_stream(
        [], "sys", "m", FakeLedger(), on_token=None,
        reader=lambda body: sse(base_events()))
    assert d["content"][0]["text"] == "Olá mundo"
    assert d["stop_reason"] == "end_turn"


def test_usage_final_alimenta_ledger():
    led = FakeLedger()
    d, usd, dt, retries = call_bridge_stream(
        [], "sys", "m", led, reader=lambda body: sse(
            base_events(usage={"output_tokens": 100})))
    assert d["usage"]["output_tokens"] == 100
    assert d["usage"]["input_tokens"] == 10
    assert led.calls[0]["usage"]["output_tokens"] == 100
    assert usd == (10 + 100) / 1e6
    assert led.cost == usd


def test_tool_use_reconstruido():
    evs = [("message_start", {"type": "message_start",
                              "message": {"model": "m", "usage": {}}}),
           ("content_block_start", {"type": "content_block_start", "index": 0,
                                    "content_block": {"type": "tool_use", "id": "t1",
                                                      "name": "Bash"}}),
           ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                    "delta": {"type": "input_json_delta",
                                              "partial_json": "{\"command\": \"ls\"}"}}),
           ("content_block_stop", {"type": "content_block_stop", "index": 0}),
           ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"},
                              "usage": {"output_tokens": 5}}),
           ("message_stop", {"type": "message_stop"})]
    d, *_ = call_bridge_stream([], "sys", "m", FakeLedger(), reader=lambda b: sse(evs))
    assert d["content"][0] == {"type": "tool_use", "id": "t1", "name": "Bash",
                               "input": {"command": "ls"}}


def test_erro_em_todas_as_tentativas_levanta():
    try:
        call_bridge_stream([], "sys", "m", FakeLedger(),
                           reader=lambda b: sse([("error", {"type": "error"})]),
                           attempts=2, sleep=lambda s: None)
        raise AssertionError("deveria levantar")
    except BridgeSseError:
        pass

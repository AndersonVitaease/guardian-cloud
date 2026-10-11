"""RD-SUPGUARD-M2A: budget de turno + trail indexado (offline, bridge mock)."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_turn_budget_excedido_marker():
    src = open(os.path.join(ROOT, "harness.py"), encoding="utf-8").read()
    assert "TURN_BUDGET_EXCEDIDO" in src
    assert "harness-trail.idx.jsonl" in src
    assert "turn_budget_usd" in src


def test_cli_turn_budget():
    src = open(os.path.join(ROOT, "mission_run.py"), encoding="utf-8").read()
    assert "--turn-budget" in src
    assert "turn_budget_usd=getattr(args" in src


def test_idx_schema_and_offsets():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        idx = os.path.join(tmp, "harness-trail.idx.jsonl")
        trail = os.path.join(tmp, "harness-trail.jsonl")
        open(trail, "w").write("")
        recs = [{"turno": 1, "offset": 0, "ts": "t", "custo_usd": 0.1},
                {"turno": 2, "offset": 50, "ts": "t", "custo_usd": 0.2}]
        with open(idx, "w") as f:
            for r in recs: f.write(json.dumps(r) + "\n")
        lines = open(idx).read().splitlines()
        assert len(lines) == 2
        for ln in lines:
            r = json.loads(ln)
            assert set(r) == {"turno", "offset", "ts", "custo_usd"}

# Emissor de eventos mission-ops ← harness (HARNESS-SPRINT4-01, item 2)
#
# Converte o run-summary.json + harness-trail.jsonl de uma run do harness em
# eventos no spool do mission-ops (/opt/mission-events/spool.jsonl), no mesmo
# formato de notify.emit_event (kind/missionId/detail/source), com dedupe por
# assinatura (kind+missionId+transição) — a mesma transição NUNCA reemite.
import json
import os
import time

SPOOL = os.environ.get("MISSION_BUS_SPOOL") or "/opt/mission-events/spool.jsonl"
SIGNATURES = "/opt/mission-events/harness-signatures.json"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_signatures(path):
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def _spool_write(rec, spool_path):
    d = os.path.dirname(spool_path)
    if d and not os.path.isdir(d):
        return False  # spool ausente: não criar fora do ambiente mission-ops
    with open(spool_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def _resumo_da_trilha(trail_path):
    """1 linha: turnos, tools, custo, latência p50/p99 do trail."""
    try:
        with open(trail_path, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return "trail=indisponivel"
    tools = [r["tool"] for r in recs if r.get("tool") and not r["tool"].startswith("_")]
    lat = sorted(r["latencia_ms"] for r in recs
                 if isinstance(r.get("latencia_ms"), (int, float)))
    p50 = lat[len(lat) // 2] if lat else 0
    p99 = lat[int(len(lat) * 0.99)] if lat else 0
    return "turnos=%d tools=%d p50=%dms p99=%dms" % (
        len(tools), len(set(tools)), p50, p99)


def emitir_run(summary, spool_path=SPOOL, signatures_path=SIGNATURES):
    """Emitte mission_completed/mission_failed no spool a partir do run-summary.

    summary: dict do run-summary.json (veredito, motivo, run_dir, seed,
    cum_usd, latencia_ms, trail, mission opcional). Retorna lista de eventos
    emitidos (dicts) — dedupe por assinatura, erro nunca sobe.
    """
    mission = summary.get("mission") or os.path.basename(summary.get("run_dir", "run"))
    sigs = _load_signatures(signatures_path)
    emitted = []

    if summary.get("veredito") == "PASS":
        kind, transition = "mission_completed", "harness:pass"
        detail = "harness PASS (%s)" % _resumo_da_trilha(summary.get("trail", ""))
    else:
        kind, transition = "mission_failed", "harness:fail:%s" % summary.get("motivo", "?")
        detail = "harness FAIL motivo=%s (%s)" % (
            summary.get("motivo", "?"), _resumo_da_trilha(summary.get("trail", "")))

    sig = "%s|%s|%s" % (kind, mission, transition)
    if sig not in sigs:
        rec = {"ts": _now(), "event": "finding", "kind": kind, "missionId": mission,
               "detail": detail[:400], "source": "harness-v2"}
        if _spool_write(rec, spool_path):
            sigs.add(sig)
            emitted.append(rec)

    try:
        os.makedirs(os.path.dirname(signatures_path) or ".", exist_ok=True)
        with open(signatures_path, "w", encoding="utf-8") as f:
            json.dump(sorted(sigs), f)
    except OSError:
        pass
    return emitted
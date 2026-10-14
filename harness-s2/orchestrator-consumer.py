#!/usr/bin/env python3
# ORCH-QUEUE-CONSUMER-01: deterministic zero-LLM orchestrator queue consumer.
# Reads /opt/mission-events/orchestrator-queue.jsonl, applies promotion rules,
# dispatches missions via mission-ops handler, handles failures with backoff.
# Pattern: same as or-banner-guard.py (systemd daemon, Restart=always, heartbeat).
#
# RD-LOOP-01 (05/10): guarda-contra de loop e de realidade.
# Incidente: loop de redispatch (172 promoções / 3 missões ativas) — a fila era
# relida a cada sweep e cada entrada re-despachada (no_op contava como promoção),
# sem preflight de cwd/verify e sem cap. Agora, ANTES de despachar:
#   (a) conflito de verify/cwd resolvido (verify.json solto com dono de missão ATIVA
#       diferente → gate); (b) missão não promovida nas últimas 12h (dedupe);
#   (c) cwd existe e é gravável (W_OK + fs não-RO — classe EROFS de bind).
#   Cap de redispatch: máx 2 tentativas por missão em 24h → gate-operator.
#   Detector de loop: promoções/15min >> ledgers ativos (razão > 3) → auto-corte
#   (para de promover, finding dispatch_loop_detected, intervenção obrigatória).
#   Modo shadow (--shadow): decide e LOGA o que FARIA, sem despachar (soak 2h).
# Falha em qualquer gate → NÃO despacha; marca gate-operator com motivo tipado.
# Liberação: só ordem do operator — `python3 orchestrator-consumer.py reset-loop-breaker`
# (detector) ou intent com operatorOrder (cap/dedupe, repassado ao handle_mission_dispatch).
# ORCH-LIVENESS-02: paths por env — provas E2E com subprocesso real redirecionam
# os paths sem tocar produção (default = produção, igual ao comportamento anterior).
def _env_path(env_name, default):
    v = os.environ.get(env_name)
    return v if v else default


import hashlib, json, os, re, subprocess, sys, time, urllib.request, urllib.error

import yaml

QUEUE_PATH = _env_path("ORCH_LIVENESS_QUEUE", "/opt/mission-events/orchestrator-queue.jsonl")
STATE_PATH = _env_path("ORCH_LIVENESS_STATE", "/opt/mission-events/orchestrator-consumer.state.json")
LOCK_PATH = _env_path("ORCH_LIVENESS_LOCK", "/opt/mission-events/orchestrator-consumer.lock")
SPOOL_PATH = _env_path("ORCH_LIVENESS_SPOOL", "/opt/mission-events/spool.jsonl")
LOG_PATH = _env_path("ORCH_LIVENESS_LOG", "/opt/mission-events/orchestrator-consumer.log")
HEARTBEAT_PATH = _env_path("ORCH_LIVENESS_HEARTBEAT", "/opt/mission-events/orchestrator-consumer.heartbeat.json")
PID_PATH = _env_path("ORCH_LIVENESS_PID", "/opt/mission-events/orchestrator-consumer.pid")
SHADOW_LOG_PATH = "/opt/mission-events/orchestrator-consumer.shadow.jsonl"
SHADOW_HEARTBEAT_PATH = _env_path("ORCH_LIVENESS_SHADOW_HB", "/opt/mission-events/orchestrator-consumer.shadow-heartbeat.json")
INTERVAL = 15  # seconds between queue sweeps (operator 08/10: latência de agentes/missões)
LOCK_TTL_MS = 30_000
MAX_PROMOTIONS = 5
MAX_ATTEMPTS = 3

# ── ORCH-LIVENESS-02: liveness honesta — parado = parado ─────────────────
# state.status só vale 'alive' se o writer é o próprio consumer com heartbeat
# vivo (PID confere com kill -0). Shadow/diagnose/qualquer outro writer nunca
# escreve 'alive' (write_state_as). O mission-watcher roda reconcile_state() a
# cada ciclo: fantasma (state 'alive' com consumer morto) → 'stopped' + evento
# tipado orch_consumer_dead no bus (dedupe por incidente: pid + TTL 1h).
HEARTBEAT_MAX_AGE_S = 2 * INTERVAL   # 120s — mesmo teto do WatchdogSec=120
GHOST_STALE_S = 15 * 60              # lastPromotion parado > X com fila pendente
GHOST_EVENT_TTL_S = 3600             # dedupe do evento: 1 por incidente (pid) por hora
_LAST_SD_PING = None                 # epoch do último WATCHDOG=1 aceito

# ── RD-DISO-01: isolamento estrutural (worktree + lease + scheduler) ──
LEASES_PATH = "/root/.hermes/mission-state/component-leases.json"
LEASE_TTL_S = 6 * 3600                    # mesmo TTL do plugin (crash-safe)
LEASE_STAGGER_MAX_S = 24 * 3600           # lease não abre em 24h → dead-letter
DISPATCH_TIMEOUT_S = 240                  # cobre ready-deadline 180s do plugin (fix 5)
LATENCY_PATH = "/root/.hermes/mission-state/latency.jsonl"

# ── RD-ORCH-DEPS-01: dependências entre intents (opt-in por intent) ──────
# Flag OFF (default) = comportamento atual byte a byte. Flag ON + campo
# `depends_on` no payload da intent = só promove se TODOS os pré-requisitos
# tiverem ledger em estado terminal com verdict PASS; senão blocked
# DEPS_NOT_MET (sem requeue, sem loop — operator resolve).
DEPS_ON = os.environ.get("ORCH_DEPS_ON") == "1"
DEPS_STATE_DIR = _env_path("ORCH_STATE_DIR", "/root/.hermes/mission-state")
DEPS_ACTIVE_STATUSES = {"", "running", "pending", "queued", "in_progress", "active", "started"}


def deps_unmet(payload):
    """RD-ORCH-DEPS-01: pré-requisitos não satisfeitos ([] = ok).

    Satisfeito = ledger <DEPS_STATE_DIR>/<id>.json existe, estado terminal
    (status fora de DEPS_ACTIVE_STATUSES) e verdict PASS.
    """
    deps = payload.get("depends_on")
    if not deps or not isinstance(deps, list):
        return []
    unmet = []
    for dep_id in deps:
        if not isinstance(dep_id, str) or not dep_id.strip():
            continue
        try:
            with open(os.path.join(DEPS_STATE_DIR, dep_id.strip() + ".json")) as f:
                led = json.load(f)
        except (OSError, json.JSONDecodeError):
            unmet.append(dep_id)
            continue
        status = str(led.get("status") or "").strip().lower()
        # RD-CAN-DEPS-A2: ledgers reais gravam "veredito" (ledger_missao.py);
        # aceitar os dois nomes (fake/tests usam "verdict").
        verdict = str(led.get("verdict") or led.get("veredito") or "").strip().upper()
        if status in DEPS_ACTIVE_STATUSES or verdict != "PASS":
            unmet.append(dep_id)
    return unmet


# ── RD-LOOP-01: parâmetros dos guarda-contras ───────────────────────────
MISSION_STATE_DIR = "/root/.hermes/mission-state"
DEDUPE_WINDOW_S = 12 * 3600      # item 2b: missão não promovida nas últimas 12h
CAP_WINDOW_S = 24 * 3600         # item 3: janela do cap
CAP_MAX = 2                      # item 3: máx 2 tentativas por missão em 24h
LOOP_WINDOW_S = 15 * 60          # item 4: janela do detector
LOOP_RATIO_MAX = 3.0             # item 4: promoções/ledgers ativos > 3 → auto-corte

sys.path.insert(0, "/opt/mission-events")
try:
    from ledger_emit import criar_ledger
except Exception as _le_err:  # ledger NUNCA quebra o consumer
    criar_ledger = None
    log(f"ledger_emit indisponível: {_le_err}")
# RD-DISO-01 fix 6: breaker só arma com 3 janelas CONSECUTIVAS acima do limiar E
# promoções sem consumo correspondente da fila (progresso real) — burst isolado
# de catch-up (5 promoções em 15min após fila parada) NÃO re-arma.
LOOP_STREAK_MIN = 3
# Espelho de mc.ACTIVE_STATUSES (mission_core) — consumer não importa o plugin.
ACTIVE_LEDGER_STATUSES = {"dispatched", "interrupted", "needs_recovery", "start_timeout",
                          "autocompact", "prompt_failed", "waiting_operator"}
# Gate codes tipados do plugin (handle_mission_dispatch via _err) — não são falha de
# transporte: viram gate-operator no consumer, sem requeue/dead-letter.
_PLUGIN_GATE_CODES = {"INVALID_CWD", "VERIFY_CWD_CONFLICT", "CWD_NOT_WRITABLE",
                      "DISPATCH_DEDUPE_12H", "DISPATCH_CAP_EXCEEDED", "OPERATOR_ORDER_REQUIRED"}
# RD-DISO-01: recusas tipadas que REENFILEIRAM sozinhas (a fila reage, o operator não
# precisa intervir): lease de componente ocupado (staggering) e pane não confirmado
# (fix 5b — nunca ledger-ghost; tentativa seguinte com backoff).
_REQUEUE_CODES = {"COMPONENT_LEASED", "PANE_CREATE_TIMEOUT", "WORKTREE_CREATE_FAILED",
                  "HERDR_TAB_CREATE_FAILED", "HERDR_PANE_CREATE_FAILED",
                  "PLUGIN_MISSING", "DISPATCH_PAYLOAD_INVALID",
                  "PANE_AUSENTE", "PARSE_ZERO_STOPS", "SUDO_NO_STOP"}  # F2-QUEUE-PANE

# F2-QUEUE-PANE: despacho da fila usa o MESMO caminho do despachar_rapido.py
DESPACHAR_MISSAO_PATH = "/opt/mission-events/scripts/despachar_missao.py"
ROUTING_TABLE_PATH = "/opt/mission-events/orchestrator-model-routing.json"
SETTINGS_JSON_BASE = "/opt/memoryos/eng-mcp/.claude-config/projects"

# Cgroups dos workers (RD-SHIP-CGROUPS-01) — valores da docstring de calculate_memory_limits().
# Fails open: se o slice não existir, o dispatch volta ao caminho normal (spool cgroups_unavailable).
CGROUP_SLICE = "mission-workers.slice"
# ORCH-CGROUP-01: slice unit aninha sob mission.slice (regra systemd: pai de
# slice = nome antes do último traço; Slice= é ignorado para slice units).
CGROUP_SLICE_PATH = "/sys/fs/cgroup/mission.slice/mission-workers.slice"
# ORCH-CGROUP-01: PLUGIN_DIR era referenciado por dispatch_via_systemd sem
# definição (NameError latente — nunca disparou porque o check do slice falhava
# antes). Mesmo caminho do plugin usado pelo dispatch_mission.
PLUGIN_DIR = "/root/.hermes/plugins/mission-ops"
CGROUP_MEMORY_RESERVE = 4 * 1024 ** 3          # reserve do sistema: 4GB
CGROUP_PER_WORKER_HIGH_RATIO = 0.3             # MemoryHigh = min(allocatable*0.3, 2.5GB)
CGROUP_PER_WORKER_MAX_RATIO = 0.4              # MemoryMax  = min(allocatable*0.4, 3.5GB)
CGROUP_MIN_MEMORY_HIGH = 256 * 1024 ** 2
CGROUP_MIN_MEMORY_MAX = 512 * 1024 ** 2

_routing_table_cache = None


def log(msg):
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "orchestrator-consumer", "msg": str(msg)[:200]})
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        pass


def spool(kind, mission_id, msg):
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": kind, "missionId": mission_id, "msg": str(msg)[:200], "source": "orchestrator-consumer"})
    try:
        with open(SPOOL_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── ORCH-LIVENESS-02: mecanismos de liveness honesta ─────────────────────

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _pid_alive(pid):
    """kill -0 tipado: True só com PID existente e sinalizável."""
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError):
        return False
    except OSError:
        return False


def _write_heartbeat(path, status):
    """Batimento do writer: PID + frescor + estado do watchdog systemd.
    HEARTBEAT_PATH é EXCLUSIVO do consumer de produção; shadow escreve em
    SHADOW_HEARTBEAT_PATH (nunca conta como liveness do consumer)."""
    try:
        data = {"pid": os.getpid(), "ts": _now_iso(), "tsEpoch": time.time(),
                "status": status,
                "watchdog": {"active": bool(os.environ.get("NOTIFY_SOCKET")),
                             "lastPing": _LAST_SD_PING}}
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        pass


def write_state_as(state, writer_kind):
    """ORCH-LIVENESS-02 item 1: writer que NÃO é o consumer de produção nunca
    escreve 'alive' — shadow/diagnose/qualquer outro writer tem o status
    forçado para o próprio kind antes de persistir."""
    if str(state.get("status") or "") == "alive":
        state["status"] = str(writer_kind or "diagnose")
    write_state(state)
    return state


def consumer_health(now=None):
    """ORCH-LIVENESS-02 item 2: liveness provável e honesta do consumer.
    Fonte de verdade = PID do heartbeat (kill -0) + heartbeat < 2×INTERVAL +
    sd_notify recente quando o consumer roda sob systemd (WatchdogSec=120).
    Resultado tipado {alive, reason}. Sem heartbeat = alive:false com
    reason 'no-heartbeat' (evidência insuficiente p/ correção — regime antigo
    não escrevia heartbeat; o reconcile NÃO corrige nesse caso)."""
    now = now if now is not None else time.time()
    out = {"alive": False, "reason": "no-heartbeat", "pid": None, "pidAlive": False,
           "heartbeatAgeS": None, "sdNotifyAgeS": None, "watchdogActive": False,
           "stateStatus": "stopped", "lastPromotion": None, "shadow": None}
    st = read_state()
    out["stateStatus"] = str(st.get("status") or "stopped")
    out["lastPromotion"] = st.get("lastPromotion")
    hb = read_json(HEARTBEAT_PATH, None)
    if not isinstance(hb, dict) or not hb:
        return out
    pid = hb.get("pid")
    out["pid"] = pid
    out["pidAlive"] = _pid_alive(pid)
    ts = hb.get("tsEpoch")
    ts = float(ts) if isinstance(ts, (int, float)) else _parse_iso_flex(hb.get("ts"))
    if ts is not None:
        out["heartbeatAgeS"] = round(max(0.0, now - ts), 1)
    wd = hb.get("watchdog") or {}
    out["watchdogActive"] = bool(wd.get("active"))
    if out["watchdogActive"] and wd.get("lastPing") is not None:
        out["sdNotifyAgeS"] = round(max(0.0, now - float(wd["lastPing"])), 1)
    if not out["pidAlive"]:
        out["reason"] = "pid-dead"
        return out
    if out["heartbeatAgeS"] is None or out["heartbeatAgeS"] > HEARTBEAT_MAX_AGE_S:
        out["reason"] = "heartbeat-stale"
        return out
    if out["watchdogActive"] and (wd.get("lastPing") is None
                                  or now - float(wd["lastPing"]) > HEARTBEAT_MAX_AGE_S):
        out["reason"] = "sdnotify-stale"
        return out
    out["alive"] = True
    out["reason"] = "ok"
    shb = read_json(SHADOW_HEARTBEAT_PATH, None)
    if (isinstance(shb, dict) and isinstance(shb.get("tsEpoch"), (int, float))
            and now - float(shb["tsEpoch"]) <= HEARTBEAT_MAX_AGE_S):
        out["shadow"] = {"running": True, "pid": shb.get("pid")}  # informativo, nunca liveness
    return out


def _queue_pending_count():
    """Entradas pendentes na fila (para a condição do evento de fantasma)."""
    n = 0
    try:
        with open(QUEUE_PATH) as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    e = json.loads(s)
                except json.JSONDecodeError:
                    continue
                if isinstance(e, dict) and "id" in e:
                    n += 1
    except Exception:
        pass
    return n


def _last_promotion_age(state, now):
    ts = _parse_iso_flex(state.get("lastPromotion"))
    if ts is None:
        return None
    return max(0.0, now - ts)


def reconcile_state(now=None, emit=True):
    """ORCH-LIVENESS-02 item 4: auto-detecção de fantasma (0-LLM).
    state 'alive' com consumer morto (health não-alive COM evidência: heartbeat
    existente) → corrige para 'stopped' (+stoppedSince, deadReason) e emite
    evento tipado orch_consumer_dead no bus (condição do contrato:
    lastPromotion > GHOST_STALE_S com fila pendente; dedupe por incidente:
    pid + TTL 1h — guardado no próprio state). Sem heartbeat (regime antigo),
    corrige NADA: evidência insuficiente, alive:false apenas no health."""
    now = now if now is not None else time.time()
    health = consumer_health(now=now)
    if health.get("alive"):
        # consumer vivo de novo: limpa o marcador do incidente anterior
        state = read_state()
        if state.get("deadEvent"):
            state.pop("deadEvent", None)
            write_state(state)
        return {"changed": False, "alive": True, "health": health}
    if not isinstance(read_json(HEARTBEAT_PATH, None), dict):
        # regime antigo (sem heartbeat): sem evidência de morte — não corrige
        return {"changed": False, "alive": False, "health": health,
                "note": "sem heartbeat (regime antigo?) — correção exige evidência"}
    state = read_state()
    if str(state.get("status") or "") != "alive":
        return {"changed": False, "alive": False, "health": health,
                "note": "estado já honesto (%s)" % state.get("status")}
    # fantasma confirmado: state mente 'alive', consumer morto → stopped
    state["status"] = "stopped"
    state["stoppedSince"] = _now_iso()
    state["deadReason"] = health.get("reason")
    out = {"changed": True, "alive": False, "reason": health.get("reason"),
           "previousStatus": "alive", "stoppedSince": state["stoppedSince"],
           "event": None}
    promo_age = _last_promotion_age(state, now)
    pending = _queue_pending_count()
    stale_ok = promo_age is None or promo_age > GHOST_STALE_S
    marker = state.get("deadEvent") or {}
    marker_ts = marker.get("ts") if isinstance(marker.get("ts"), (int, float)) else 0
    dedupe_ok = (now - float(marker_ts) > GHOST_EVENT_TTL_S
                 or (health.get("pid") is not None and marker.get("pid") != health.get("pid")))
    if emit and stale_ok and pending > 0 and dedupe_ok:
        state["deadEvent"] = {"ts": now, "pid": health.get("pid"),
                              "reason": health.get("reason")}
        detail = ("consumer morto (%s): pid=%s lastPromotionAge=%s filaPendente=%d"
                  % (health.get("reason"), health.get("pid"),
                     ("%.0fs" % promo_age) if promo_age is not None else "null", pending))
        spool_finding("orch_consumer_dead", "*", detail)
        log("GHOST DETECTED: " + detail)
        out["event"] = {"kind": "orch_consumer_dead", "missionId": "*", "detail": detail}
    else:
        out["eventSuppressed"] = {"staleOk": bool(stale_ok), "pending": pending,
                                  "dedupeOk": bool(dedupe_ok)}
    write_state(state)
    return out


# ── RD-DISO-01: helpers de lease / latência / watchdog ──────────────────

def _parse_iso_flex(raw):
    """Timestamp ISO (com/sem millis, Z ou offset) → epoch. None se inválido."""
    raw = str(raw or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        from datetime import datetime
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _lease_holder(component, now=None, leases_path=None):
    """missionId dono do lease ativo do componente (registry do plugin).
    Crash-safe: lease sem heartbeat vencido pelo TTL não vale (mesma regra do
    plugin — component_leases._lease_expired)."""
    path = leases_path or LEASES_PATH
    now = now if now is not None else time.time()
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return None
    entry = (data or {}).get(component)
    if not isinstance(entry, dict):
        return None
    ttl = entry.get("ttlS") or LEASE_TTL_S
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        ttl = LEASE_TTL_S
    for field in ("heartbeatAt", "acquiredAt"):
        ts = _parse_iso_flex(entry.get(field))
        if ts is not None and now - ts > ttl:
            return None  # vencido: crash-safe, o componente volta à fila
    return str(entry.get("missionId") or "")


def _record_latency(kind, mission_id, ms, fallback=None, detail=""):
    """RD-DISO-01 item 8: medição tipada no MESMO latency.jsonl do plugin
    (schema idêntico; source distingue no detail). Fail-open."""
    try:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "kind": str(kind)[:40], "missionId": str(mission_id or "*")[:80],
               "ms": round(float(ms), 1)}
        if fallback is not None:
            rec["fallback"] = bool(fallback)
        if detail:
            rec["detail"] = str(detail)[:160]
        with open(LATENCY_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _sd_notify():
    """Ping do watchdog systemd (WatchdogSec=120). Sem NOTIFY_SOCKET = no-op
    (rodando fora do systemd / na suíte). Fail-open. ORCH-LIVENESS-02: ping
    bem-sucedido registra o epoch no heartbeat (sd_notify recente = check do
    health CLI)."""
    global _LAST_SD_PING
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    try:
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s.connect(addr)
        s.sendall(b"WATCHDOG=1")
        s.close()
        _LAST_SD_PING = time.time()
    except Exception:
        pass


# ── CGroups v2 helpers ──────────────────────────────────────────────

def _cgroup_read_u64(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def check_cgroups_v2():
    """Return True if cgroups v2 unified hierarchy with memory controller is available."""
    try:
        with open("/sys/fs/cgroup/cgroup.controllers") as f:
            return "memory" in f.read()
    except Exception:
        return False


def slice_memory_current():
    """Read memory.current from mission-workers.slice (bytes), or None if unavailable."""
    if not os.path.isdir(CGROUP_SLICE_PATH):
        return None
    return _cgroup_read_u64(os.path.join(CGROUP_SLICE_PATH, "memory.current"))


def calculate_memory_limits():
    """
    Calculate MemoryHigh and MemoryMax from MemTotal/mem_free.

    MemoryHigh = min(allocatable * 0.3, 2.5GB) — soft limit
    MemoryMax = min(allocatable * 0.4, 3.5GB) — hard limit
    Allocatable = MemAvailable - system reserve (4GB).
    """
    try:
        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0].endswith(":"):
                    meminfo[parts[0][:-1]] = int(parts[1]) * 1024
    except Exception:
        meminfo = {}

    mem_available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    allocatable = max(0, mem_available - CGROUP_MEMORY_RESERVE)

    memory_high = max(int(allocatable * CGROUP_PER_WORKER_HIGH_RATIO), CGROUP_MIN_MEMORY_HIGH)
    memory_high = min(memory_high, int(2.5 * 1024 ** 3))

    memory_max = max(int(allocatable * CGROUP_PER_WORKER_MAX_RATIO), CGROUP_MIN_MEMORY_MAX)
    memory_max = min(memory_max, int(3.5 * 1024 ** 3))

    return memory_high, memory_max


def dispatch_agent(entry):
    """STRIPE/ORCH-AGENT (operator 08/10): despacha comando a um agente-profile
    (hermes chat -q --profile X) em background. Retorna dict SEMPRE."""
    try:
        payload = entry.get("payload") or {}
        agent = str(payload.get("agent") or "").strip()
        cmd = str(payload.get("cmd") or "").strip()
        if not agent or not cmd:
            return {"ok": False, "error": "AGENT_PAYLOAD_INVALIDO", "detail": "payload.agent e payload.cmd obrigatorios"}
        allowed = {"despachante", "auditor", "vigia"}
        if agent not in allowed:
            return {"ok": False, "error": "AGENT_DESCONHECIDO", "detail": f"permitidos: {sorted(allowed)}"}
        outdir = os.path.join(os.path.dirname(QUEUE_PATH), "agent-runs")
        os.makedirs(outdir, exist_ok=True)
        entry_id = str(entry.get("id"))
        outfile = os.path.join(outdir, f"{entry_id}.out")
        logf = os.path.join(outdir, f"{entry_id}.log")
        import subprocess as _sp
        with open(logf, "w") as lf:
            _sp.Popen(["timeout", "600", "hermes", "chat", "--profile", agent, "-q", cmd],
                      stdout=lf, stderr=lf, start_new_session=True,
                      cwd=os.path.expanduser("~root"))
        with open(outfile, "w") as of:
            of.write(json.dumps({"id": entry_id, "agent": agent, "cmd": cmd[:200],
                                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "status": "dispatched"}) + "\n")
        spool("orch_agent_dispatched", entry_id, f"agent={agent} out={outfile}")
        return {"ok": True, "agent": agent, "outfile": outfile}
    except Exception as e:
        return {"ok": False, "error": "AGENT_DISPATCH_ERRO", "detail": str(e)[:200]}

def dispatch_via_systemd(mission_id, prompt_file, worktree, priority, payload=None):
    """Dispatch a mission via systemd-run --slice=mission-workers.slice with dynamic cgroup limits.

    Fails open: if cgroups v2 unavailable, systemd-run missing, or systemd-run fails,
    returns None and the caller must fall back to dispatch_mission() normal path.
    """
    if not check_cgroups_v2():
        spool("cgroups_unavailable", mission_id, "cgroups v2 unavailable — falling back to normal dispatch")
        return None

    if not os.path.isdir(CGROUP_SLICE_PATH):
        spool("cgroups_unavailable", mission_id, f"slice {CGROUP_SLICE} cgroup dir not found — falling back")
        return None

    memory_high, memory_max = calculate_memory_limits()
    unit_name = f"mission-{mission_id}"
    _p = payload or {}

    code = (
        "import sys, json, importlib.util; "
        f'spec = importlib.util.spec_from_file_location("mission_ops", "{PLUGIN_DIR}/__init__.py", '
        f'submodule_search_locations=["{PLUGIN_DIR}"]); '
        'PKG = importlib.util.module_from_spec(spec); sys.modules["mission_ops"] = PKG; '
        "spec.loader.exec_module(PKG); "
        f"result = PKG.handle_mission_dispatch({{'missionId': {json.dumps(mission_id)}, "
        f"'promptFile': {json.dumps(prompt_file)}, "
        f"'worktree': {worktree!r}, 'priority': {priority}, "
        f"'operatorOrder': {json.dumps(str(_p.get('operatorOrder') or ''))}, "
        f"'spawnedBy': {json.dumps(str(_p.get('spawnedBy') or ''))}}}); "
        "print(json.dumps(result))"
    )

    cmd = [
        "/usr/bin/systemd-run",
        "--slice", CGROUP_SLICE,
        f"--property=MemoryHigh={memory_high}",
        f"--property=MemoryMax={memory_max}",
        "--scope",
        f"--unit={unit_name}",
        "--description=Mission worker " + mission_id,
        "python3", "-c", code,
    ]

    try:
        # RD-DISO-01 fix 5: timeout cobre o despacho completo (ready-deadline 180s do
        # plugin) — 30s matava despachos LEGÍTIMOS no meio (outra fonte de ledger-ghost)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=DISPATCH_TIMEOUT_S)
        if r.returncode == 0:
            try:
                parsed = json.loads(r.stdout.strip())
                if isinstance(parsed, dict):
                    _p = payload or {}
                    _emit_dispatch_ledger(mission_id, prompt_file,
                                          str(_p.get("cwd") or ""),
                                          spawned_by=str(_p.get("spawnedBy") or "operator"),
                                          consequence=bool(_p.get("consequence")))
                    return parsed
                # ORCH-DISPATCH-TIPO-01: payload não-dict (ex.: JSON string do
                # handler) NUNCA sobe cru — derrubava o ciclo inteiro no .get().
                log(f"dispatch_via_systemd: payload não-dict de {mission_id}: "
                    f"{str(parsed)[:200]}")
                return {"ok": False, "error": f"payload não-dict: {str(parsed)[:200]}"}
            except json.JSONDecodeError:
                return {"ok": False, "error": "DISPATCH_PAYLOAD_INVALID"}
        spool("cgroups_unavailable", mission_id, f"systemd-run exit {r.returncode}: {r.stderr[:200]}")
        return None
    except FileNotFoundError:
        spool("cgroups_unavailable", mission_id, "systemd-run not found — falling back")
        return None
    except subprocess.TimeoutExpired:
        spool("cgroups_unavailable", mission_id, "systemd-run timed out — falling back")
        return None
    except Exception as e:
        spool("cgroups_unavailable", mission_id, f"systemd-run error: {str(e)[:200]} — falling back")
        return None


def get_routed_runner(class_name, routing_table):
    """Return the runner ("harness" or "cli") for a mission class.

    Reads classes[class]["runner"] with fallback to default["runner"].
    Missing/unknown value -> "cli" (legacy path untouched).
    """
    if not routing_table:
        return "cli"
    classes = routing_table.get("classes", {})
    entry = classes.get(class_name) if class_name else None
    if not isinstance(entry, dict):
        entry = routing_table.get("default", {})
    runner = entry.get("runner") if isinstance(entry, dict) else None
    if not runner and isinstance(routing_table.get("default"), dict):
        runner = routing_table["default"].get("runner")
    return runner if runner in ("harness", "cli") else "cli"


def _harness_seed(mission_id):
    """Stable daily seed: hash(mission_id, UTC date) mod 9000 + 100."""
    day = time.strftime("%Y-%m-%d", time.gmtime())
    h = hashlib.sha256(f"{mission_id}|{day}".encode()).hexdigest()
    return int(h[:8], 16) % 9000 + 100


def dispatch_via_harness(mission_id, prompt_file, cwd, budget=0.5,
                         max_turns=30, seed=None, spawned_by=None,
                         consequence=None):
    """Dispatch a mission via the harness runner (mission_run.py) under systemd.

    Second dispatch path controlled by the routing table ("runner": "harness").
    Returns a dict -- NEVER a str (the plugin handler mangles str payloads).
    """
    if seed is None:
        seed = _harness_seed(mission_id)
    # fallback honesto: cwd vazio/relativo -> base absoluta fixa (nunca vazio)
    cwd = str(cwd or "").strip()
    if not cwd or not os.path.isabs(cwd):
        cwd = "/home/worker/harness-s2"
    run_dir = os.path.join(cwd, "runs", mission_id)
    os.makedirs(run_dir, exist_ok=True)
    # donidade: mission_run.py roda como user "worker" — o dir precisa ser dele
    try:
        import pwd
        _w = pwd.getpwnam("worker")
        os.chown(run_dir, _w.pw_uid, _w.pw_gid)
    except (KeyError, PermissionError, OSError) as e:
        log(f"dispatch_via_harness: chown worker falhou em {run_dir}: {e}")
    # F2-QUEUE-PANE (cura D3/FIND-faa7ad08): a missão da fila nasce COM pane
    # herdr e ledger — mesmo caminho do despachar_missao.py/despachar_rapido.py.
    # Sem pane confirmado => erro tipado PANE_AUSENTE (nunca promovido sem run).
    cmd = [
        "/usr/bin/python3", DESPACHAR_MISSAO_PATH,
        prompt_file, cwd,
        "--seed", str(seed),
        "--budget", str(budget),
        "--turns", str(max_turns),
        "--sem-baseline",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=DISPATCH_TIMEOUT_S)
        _out = {}
        for _ln in reversed((r.stdout or "").strip().splitlines()):
            try:
                _out = json.loads(_ln)
                break
            except json.JSONDecodeError:
                continue
        if r.returncode != 0 or not _out.get("ok"):
            _err = str(_out.get("erro") or _out.get("error")
                       or f"despachar_missao exit {r.returncode}: {(r.stderr or '')[:200]}")
            spool("harness_dispatch_failed", mission_id, _err)
            return {"ok": False, "error": _err}
        _pane = _out.get("pane") or _out.get("tab")
        if not _pane:
            spool("harness_dispatch_failed", mission_id, "PANE_AUSENTE")
            return {"ok": False, "error": "PANE_AUSENTE"}
        log(f"dispatch_via_harness: {mission_id} mode=harness pane={_pane} seed={seed}")
        _emit_dispatch_ledger(mission_id, prompt_file, cwd,
                              spawned_by=str(spawned_by or "operator"),
                              consequence=bool(consequence))
        return {"ok": True, "status": "dispatched", "missionId": mission_id,
                "mode": "harness", "pane": _pane,
                "run_dir": _out.get("run_dir"),
                "seed": _out.get("seed") or seed}
    except FileNotFoundError:
        spool("harness_dispatch_failed", mission_id, "DESPACHANTE_NAO_ENCONTRADO")
        return {"ok": False, "error": "DESPACHANTE_NAO_ENCONTRADO"}
    except subprocess.TimeoutExpired:
        spool("harness_dispatch_failed", mission_id, "systemd-run timed out")
        return {"ok": False, "error": "systemd-run timed out"}
    except Exception as e:
        spool("harness_dispatch_failed", mission_id, f"error: {str(e)[:200]}")
        return {"ok": False, "error": str(e)[:200]}


def load_routing_table():
    """Read and cache the routing table JSON at startup."""
    global _routing_table_cache
    _routing_table_cache = read_json(ROUTING_TABLE_PATH, {})
    if _routing_table_cache:
        log(f"routing table loaded: {len(_routing_table_cache.get('classes', {}))} classes")
    else:
        log("routing table: no data available (file missing or invalid)")
    return _routing_table_cache


def parse_frontmatter_class(prompt_raw):
    """Parse YAML frontmatter from prompt file and return class value.

    - Extracts the ``---`` delimited frontmatter block
    - Parses YAML key-value pairs from it
    - Returns the ``class`` field value (mecanica/media/pesada) or None
    - Handles quoted values, spaces around colons, etc.
    - Falls back to None if no class field found (caller applies default)
    """
    try:
        match = re.search(r"^---\s*\n([\s\S]*?)\n---", prompt_raw, re.MULTILINE)
        if not match:
            return None
        frontmatter = match.group(1)
        data = yaml.safe_load(frontmatter)
        if isinstance(data, dict):
            return data.get("class")
        return None
    except Exception:
        return None


def get_routed_worker(class_name, routing_table):
    """Return worker model for class, or None for pesada (operator required).

    Falls back to the ``default`` entry in the routing table if the class
    is not explicitly listed.
    """
    if not routing_table:
        return None
    classes = routing_table.get("classes", {})
    if class_name and class_name in classes:
        class_config = classes[class_name]
        if isinstance(class_config, dict):
            return class_config.get("worker")
    # Fall back to default
    default = routing_table.get("default", {})
    if isinstance(default, dict):
        return default.get("worker")
    return None


def write_settings_json_pin(worker_model, mission_id, worktree=None):
    """Write the worker model pin into .claude-config/settings.json.

    Base path is ``SETTINGS_JSON_BASE``.  If a ``worktree`` is provided the
    pin is written to ``<base>/<worktree>/settings.json`` (idempotent —
    existing file is backed up before overwrite).  The pin is a minimal JSON
    object with the model and a timestamp.
    """
    try:
        if worktree:
            base_dir = os.path.join(SETTINGS_JSON_BASE, worktree)
        else:
            base_dir = SETTINGS_JSON_BASE
        os.makedirs(base_dir, exist_ok=True)
        settings_path = os.path.join(base_dir, "settings.json")

        # Backup existing settings.json idempotently
        if os.path.exists(settings_path):
            backup_path = settings_path + ".bak"
            try:
                with open(settings_path) as src, open(backup_path, "w") as dst:
                    dst.write(src.read())
            except Exception:
                pass

        pin = {"model": worker_model, "pinnedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "missionId": mission_id}
        write_json(settings_path, pin)
        log(f"settings pin written: {settings_path} model={worker_model}")
    except Exception as e:
        log(f"write_settings_json_pin failed: {e}")


def generate_trindade_line(ledger):
    """Generate a TRINDADE line from ledger role + spend data.

    Expected ledger shape (dict with role keys):
    {
      "worker":  {"model": "...", "tokens_in": N, "tokens_out": N, "cost": N},
      "advisor": {"model": "...", "tokens_in": N, "tokens_out": N, "cost": N},
      "supervisor": {"model": "...", "tokens_in": N, "tokens_out": N, "cost": N},
      "judge":   {"model": "...", "tokens_in": N, "tokens_out": N, "cost": N},
    }

    Returns a formatted string or an empty string if ledger is empty/None.
    """
    if not ledger:
        return ""

    roles = ["worker", "advisor", "supervisor", "judge"]
    parts = []
    for role in roles:
        entry = ledger.get(role)
        if not entry:
            model = "null"
            cost_str = "$0"
            tokens_str = ""
        else:
            model = entry.get("model") or "null"
            tokens_in = entry.get("tokens_in", 0)
            tokens_out = entry.get("tokens_out", 0)
            cost = entry.get("cost", 0)
            tokens_str = f"{tokens_in}/{tokens_out}"
            cost_str = f"${cost:.4f}" if cost > 0 else "$0"

        if role == "judge":
            parts.append(f"judge={model} ({cost_str})")
        else:
            token_part = f" [{tokens_str}]" if tokens_str else ""
            parts.append(f"{role}={model} ({cost_str}{token_part})")

    return "TRINDADE: " + " | ".join(parts)


def check_divergence(routed_model, actual_model, mission_id):
    """Emit orch_route_divergence event if routed model differs from actual model."""
    if not routed_model or not actual_model:
        return
    if routed_model != actual_model:
        spool(
            "orch_route_divergence",
            mission_id,
            f"routed_model={routed_model} actual_model={actual_model}",
        )
        log(f"divergence detected for {mission_id}: routed={routed_model} actual={actual_model}")


def acquire_lock():
    now = int(time.time() * 1000)
    try:
        if os.path.exists(LOCK_PATH):
            with open(LOCK_PATH) as f:
                lock = json.load(f)
            if now - lock.get("acquiredAt", 0) < LOCK_TTL_MS:
                return False
        with open(LOCK_PATH, "w") as f:
            json.dump({"acquiredAt": now, "pid": os.getpid()}, f)
        return True
    except Exception:
        return False


def release_lock():
    try:
        os.unlink(LOCK_PATH)
    except Exception:
        pass


def read_state():
    return read_json(STATE_PATH, {"status": "stopped", "lastPromotion": None, "lastPromotionId": None, "promotedCount": 0, "skippedCount": 0, "blockedCount": 0, "requeuedCount": 0, "deadLetteredCount": 0, "updatedAt": None})


def write_state(state):
    write_json(STATE_PATH, state)


def dispatch_mission(mission_id, prompt_file, worktree=None, priority=5, payload=None):
    """Call the mission-ops handler via herdr or direct python.

    When cgroups v2 is available, dispatches via systemd-run into
    mission-workers.slice with dynamic MemoryHigh/MemoryMax limits.
    Fails open to normal dispatch if cgroups is unavailable.
    """
    plugin_dir = "/root/.hermes/plugins/mission-ops"
    if not os.path.exists(os.path.join(plugin_dir, "__init__.py")):
        log(f"dispatch_mission: no plugin at {plugin_dir} for {mission_id}")
        return {"ok": False, "error": "PLUGIN_MISSING"}

    # Try cgroups-aware dispatch first (fail-open: falls back to normal)
    cg_result = dispatch_via_systemd(mission_id, prompt_file, worktree, priority, payload=payload)
    if cg_result is not None:
        return cg_result

    # Fallback: normal dispatch (no cgroups isolation)
    try:
        import subprocess as _subprocess
        code = f"""
import sys, json, importlib.util
spec = importlib.util.spec_from_file_location("mission_ops", "{plugin_dir}/__init__.py", submodule_search_locations=["{plugin_dir}"])
PKG = importlib.util.module_from_spec(spec); sys.modules["mission_ops"] = PKG
spec.loader.exec_module(PKG)
result = PKG.handle_mission_dispatch({{"missionId": "{mission_id}", "promptFile": "{prompt_file}", "worktree": {worktree!r}, "priority": {priority}}})
print(json.dumps(result))
"""
        r = _subprocess.run(["python3", "-c", code], capture_output=True, text=True,
                            timeout=DISPATCH_TIMEOUT_S, cwd=plugin_dir)  # fix 5: cobre ready 180s
        if r.returncode == 0:
            # RD-LOOP-01: o handler devolve JSON tipado ({ok, status, error, detail});
            # devolver {"ok": True} às cegas contava no_op e GATE como sucesso (loop 05/10).
            try:
                parsed = json.loads(r.stdout.strip())
                if isinstance(parsed, dict):
                    _p = payload or {}
                    _emit_dispatch_ledger(mission_id, prompt_file,
                                          str(_p.get("cwd") or ""),
                                          spawned_by=str(_p.get("spawnedBy") or "operator"),
                                          consequence=bool(_p.get("consequence")))
                    return parsed
                # ORCH-DISPATCH-TIPO-01: não-dict não é sucesso às cegas
                log(f"dispatch_mission: payload não-dict de {mission_id}: {str(parsed)[:200]}")
                return {"ok": False, "error": f"payload não-dict: {str(parsed)[:200]}"}
            except json.JSONDecodeError:
                return {"ok": False, "error": "DISPATCH_PAYLOAD_INVALID"}
        return {"ok": False, "error": r.stderr[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def run_orchestrate_plan():
    """Zero-LLM pre-flight plan: check system probes, budget, capacity."""
    # Check mission state dir is readable
    state_dir = "/root/.hermes/mission-state"
    try:
        os.listdir(state_dir)
    except Exception:
        return {"verdict": "THROTTLE", "throttleReasons": ["mission-state dir unreadable"]}

    # Check budget
    budget = read_json("/opt/mission-events/orchestrator-budget.json")
    if budget is None:
        return {"verdict": "THROTTLE", "throttleReasons": ["budget file missing"]}

    # Check agents capacity
    agents = read_json("/opt/mission-events/agents.json")
    if agents is None:
        return {"verdict": "THROTTLE", "throttleReasons": ["agents file missing"]}

    # Check cgroups slice memory consumption (integrated into plan capacity)
    if check_cgroups_v2() and os.path.isdir(CGROUP_SLICE_PATH):
        slice_mem = slice_memory_current()
        if slice_mem is not None:
            meminfo = {}
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2 and parts[0].endswith(":"):
                            meminfo[parts[0][:-1]] = int(parts[1]) * 1024
            except Exception:
                pass
            mem_available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            max_parallel = agents[0].get("max_parallel", 2) if agents else 2
            per_worker_estimate = int(2.5 * 1024 ** 3)  # 2.5GB per worker estimate
            usable = mem_available - CGROUP_MEMORY_RESERVE
            capacity_slots = max(1, usable // per_worker_estimate) if usable > 0 else 1
            if slice_mem > usable * 0.8:
                return {
                    "verdict": "THROTTLE",
                    "throttleReasons": [
                        f"cgroups slice {CGROUP_SLICE} using {slice_mem // (1024**3)}GB "
                        f"of {usable // (1024**3)}GB allocatable — "
                        f"only {capacity_slots} slot(s) available (max_parallel={max_parallel})"
                    ],
                }

    return {"verdict": "GO", "blockReasons": [], "throttleReasons": []}


def spool_finding(kind, mission_id, msg):
    """RD-LOOP-01: finding tipado no bus (mesmo schema do spool)."""
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "event": "finding", "kind": kind, "missionId": mission_id,
                       "msg": str(msg)[:400], "source": "orchestrator-consumer"})
    try:
        with open(SPOOL_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _ledger(mission_id):
    return read_json(os.path.join(MISSION_STATE_DIR, "%s.json" % mission_id)) or {}


def _emit_dispatch_ledger(mission_id, prompt_file, cwd, spawned_by=None,
                          consequence=None):
    """LEDGER-DISPATCH-01: escreve ledger de fila após spawn bem-sucedido.
    Falha de ledger NUNCA quebra o dispatch (try/except + engolir erro)."""
    if criar_ledger is None:
        return
    try:
        r = criar_ledger(mission_id, prompt_file, cwd,
                         spawned_by=str(spawned_by or "operator"),
                         consequence=bool(consequence),
                         ledger_dir=MISSION_STATE_DIR)
        log("ledger_emit: %s -> %s" % (mission_id, json.dumps(r)))
    except Exception as e:
        log("ledger_emit: falha (não fatal) para %s: %s" % (mission_id, str(e)[:200]))


def active_ledgers_count():
    """RD-LOOP-01 item 4: nº de ledgers ativos (denominador da razão do detector)."""
    n = 0
    try:
        for name in os.listdir(MISSION_STATE_DIR):
            if not name.endswith(".json") or name.endswith(".verify.json"):
                continue
            led = read_json(os.path.join(MISSION_STATE_DIR, name))
            if isinstance(led, dict) and led.get("status") in ACTIVE_LEDGER_STATUSES:
                n += 1
    except Exception:
        pass
    return n


def _cwd_writable(cwd):
    """RD-LOOP-01 item 2c: cwd existe e é gravável (W_OK + fs não-RO — classe EROFS)."""
    if not cwd or not os.path.isdir(cwd):
        return False, "cwd não existe: %s" % cwd
    if not os.access(cwd, os.W_OK):
        return False, "cwd sem permissão de escrita: %s" % cwd
    try:
        if os.statvfs(cwd).f_flag & 0x1:  # ST_RDONLY
            return False, "filesystem read-only no cwd (classe EROFS de bind): %s" % cwd
    except OSError:
        pass  # statvfs indisponível: fail-open neste check
    return True, ""


def _verify_cwd_conflict(mission_id, cwd):
    """RD-LOOP-01 item 2a: verify.json solto no cwd alvo com dono de missão ATIVA
    diferente = conflito não resolvido (só o operator resolve o estado sujo)."""
    if not cwd:
        return None
    vf = os.path.join(cwd, "verify.json")
    if not os.path.isfile(vf):
        return None
    data = read_json(vf)
    owner = str(data.get("mission") or "").strip() if isinstance(data, dict) else ""
    if not owner or owner == mission_id:
        return None
    other = _ledger(owner)
    if other.get("status") in ACTIVE_LEDGER_STATUSES:
        return ("verify.json no cwd %s pertence à missão ATIVA %s (status %s) — conflito "
                "de verify/cwd não resolvido" % (cwd, owner, other.get("status")))
    return None


def ensure_run_tab(mission_id, cwd, seed=None):
    """HEADLESS-TAB-01: garante aba herdr RUN:<id>#<seed> para missões de fila
    (headless não cria aba — invisível ao operator). Fail-open: NUNCA raise,
    NUNCA bloqueia o dispatch."""
    try:
        seed = str(seed or "")
        label = "RUN:%s#%s" % (mission_id, seed)
        # dedupe 1: ledger com tabId não-vazio
        led = _ledger(mission_id)
        if str(led.get("tabId") or "").strip():
            return {"ok": True, "dedupe": True}
        # dedupe 2: aba existente com label RUN:<id>#...
        try:
            out = subprocess.run(["herdr", "tab", "list"], capture_output=True,
                                 text=True, timeout=10.0)
            if out.returncode == 0:
                for line in (out.stdout or "").strip().splitlines():
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    tabs = None
                    if isinstance(d.get("data"), dict):
                        if isinstance(d["data"].get("tab"), dict):
                            tabs = [d["data"]["tab"]]
                        elif isinstance(d["data"].get("tabs"), list):
                            tabs = d["data"]["tabs"]
                    elif isinstance(d.get("tabs"), list):
                        tabs = d["tabs"]
                    for t in (tabs or []):
                        if isinstance(t, dict) and str(t.get("label") or "").startswith("RUN:%s#" % mission_id):
                            return {"ok": True, "dedupe": True}
        except Exception as e:
            log("TAB_CREATE_FAILED: tab list falhou (não fatal) %s: %s" % (mission_id, str(e)[:120]))
        # create
        out = subprocess.run(["herdr", "tab", "create", "--cwd", str(cwd or "/tmp"),
                              "--label", label, "--no-focus"],
                             capture_output=True, text=True, timeout=15.0)
        if out.returncode != 0:
            err = "herdr tab create rc=%s: %s" % (out.returncode, (out.stderr or out.stdout or "")[:200])
            log("TAB_CREATE_FAILED: %s %s" % (mission_id, err))
            return {"ok": False, "error": err}
        tab_id = pane_id = None
        for line in (out.stdout or "").strip().splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            data = d.get("data") if isinstance(d.get("data"), dict) else d
            tab = data.get("tab") if isinstance(data.get("tab"), dict) else {}
            pane = data.get("pane") if isinstance(data.get("pane"), dict) else {}
            tab_id = tab.get("tab_id") or data.get("tab_id") or tab_id
            pane_id = pane.get("pane_id") or data.get("pane_id") or pane_id
        if not tab_id:
            err = "tab create sem tab_id"
            log("TAB_CREATE_FAILED: %s %s" % (mission_id, err))
            return {"ok": False, "error": err}
        # rename (não fatal)
        try:
            subprocess.run(["herdr", "tab", "rename", str(tab_id), label],
                           capture_output=True, text=True, timeout=10.0)
        except Exception as e:
            log("TAB_CREATE_FAILED: rename não fatal %s: %s" % (mission_id, str(e)[:120]))
        # ledger: tabId+paneId atômico
        try:
            lp = os.path.join(MISSION_STATE_DIR, "%s.json" % mission_id)
            data = read_json(lp) or {}
            data["tabId"] = tab_id
            if pane_id:
                data["paneId"] = pane_id
            tmp = lp + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, lp)
        except Exception as e:
            log("TAB_CREATE_FAILED: ledger não fatal %s: %s" % (mission_id, str(e)[:120]))
        return {"ok": True, "tabId": tab_id, "paneId": pane_id}
    except Exception as e:
        log("TAB_CREATE_FAILED: %s %s" % (mission_id, str(e)[:200]))
        return {"ok": False, "error": str(e)}


def _promoted_recently(mission_id, window_s, now=None, promos_log=None):
    """RD-LOOP-01 items 2b/3: promoção da missão na janela? Fontes: ledger
    (createdAt/dispatchedAt) + log de promoções do consumer (promos_log = state.promotions)."""
    now = now or time.time()
    led = _ledger(mission_id)
    for field in ("dispatchedAt", "createdAt"):
        raw = str(led.get(field) or "")
        if not raw:
            continue
        try:
            ts = time.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
            import calendar
            if calendar.timegm(ts) >= now - window_s:
                return True, raw
        except ValueError:
            continue
    if promos_log is None:
        promos_log = state_promotions()
    for ts in (promos_log.get(mission_id) or []):
        if ts >= now - window_s:
            return True, ts
    return False, None


def state_promotions():
    """Log de promoções do consumer (state.promotions: {missionId: [epoch, ...]})."""
    return (read_json(STATE_PATH, {}) or {}).get("promotions") or {}


def record_promotion(mission_id, state):
    state.setdefault("promotions", {}).setdefault(mission_id, []).append(time.time())
    # cap de memória: mantém só a janela de 24h + margem
    cutoff = time.time() - (CAP_WINDOW_S + 3600)
    state["promotions"][mission_id] = [t for t in state["promotions"][mission_id] if t >= cutoff]


def dispatch_preflight(mission_id, cwd, state, now=None):
    """RD-LOOP-01 items 2+3: preflight determinístico ANTES de despachar.
    Retorna None quando pode prosseguir, ou (code, detail) do gate."""
    now = now or time.time()
    # cwd só é julgado quando o consumer o CONHECE (payload.cwd ou ledger do
    # despacho). Despacho sem cwd conhecido: o plugin resolve e valida o seu
    # INVALID_CWD — gate às cegas aqui bloquearia toda a fila (provado na suíte).
    if cwd:
        # (a) conflito de verify/cwd
        confl = _verify_cwd_conflict(mission_id, cwd)
        if confl:
            return ("VERIFY_CWD_CONFLICT", confl)
        # (c) cwd existe e é gravável
        ok, why = _cwd_writable(cwd)
        if not ok:
            return ("CWD_NOT_WRITABLE", why)
    # (b) dedupe 12h
    promos_log = state.get("promotions") if isinstance(state, dict) else None
    hit, when = _promoted_recently(mission_id, DEDUPE_WINDOW_S, now, promos_log=promos_log)
    if hit:
        return ("DISPATCH_DEDUPE_12H",
                "missão promovida em %s (< 12h) — redispatch exige ordem do operator" % when)
    # (3) cap 2 tentativas/24h
    if promos_log is None:
        promos_log = state_promotions()
    promos = [t for t in promos_log.get(mission_id) or [] if t >= now - CAP_WINDOW_S]
    if len(promos) >= CAP_MAX:
        return ("DISPATCH_CAP_EXCEEDED",
                "máx %d tentativas/24h atingido (%d na janela) — só ordem do operator libera"
                % (CAP_MAX, len(promos)))
    return None


def check_loop_breaker(state, emit=True):
    """RD-LOOP-01 item 4 + RD-DISO-01 fix 6: promoções na janela de 15min >>
    ledgers ativos (razão > 3) SÓ arma o auto-corte com (a) 3 janelas
    CONSECUTIVAS acima do limiar E (b) promoções sem consumo correspondente da
    fila (progresso real). Catch-up legítimo (burst isolado após fila parada)
    nunca mais re-arma o breaker. emit=False (shadow): só decide."""
    if state.get("loopBreaker", {}).get("active"):
        return True
    now = time.time()
    promos_15m = sum(len([t for t in (v or []) if t >= now - LOOP_WINDOW_S])
                     for v in (state.get("promotions") or {}).values())
    consumed_15m = len([t for t in (state.get("consumedLog") or [])
                        if t >= now - LOOP_WINDOW_S])
    active = max(active_ledgers_count(), 1)
    ratio = promos_15m / active
    # fix 6: progresso real = promoções SEM consumo correspondente da fila.
    # Catch-up tem promoções ≈ consumo → não progride o streak.
    no_progress = promos_15m > consumed_15m
    streak = state.get("loopStreak") or {"n": 0, "lastTs": None}
    if ratio > LOOP_RATIO_MAX and no_progress:
        streak["n"] = int(streak.get("n") or 0) + 1
    else:
        streak = {"n": 0, "lastTs": None}
    streak["lastTs"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    streak["over"] = ratio > LOOP_RATIO_MAX
    streak["noProgress"] = no_progress
    state["loopStreak"] = streak
    if streak["n"] >= LOOP_STREAK_MIN:
        state["loopBreaker"] = {
            "active": True, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "promotions15m": promos_15m, "activeLedgers": active,
            "consumed15m": consumed_15m,
            "ratio": round(ratio, 2),
            "streakWindows": streak["n"],
            "resetRequired": "operator: python3 orchestrator-consumer.py reset-loop-breaker",
        }
        if emit:
            spool_finding("dispatch_loop_detected", "*",
                          "razão promoções/ledgers=%s (%d promoções/15min, %d ativos, "
                          "%d consumos/15min, %d janelas consecutivas) — consumer em "
                          "auto-corte, intervenção obrigatória"
                          % (state["loopBreaker"]["ratio"], promos_15m, active,
                             consumed_15m, streak["n"]))
            log("LOOP BREAKER ACIONADO: %s" % json.dumps(state["loopBreaker"]))
        return True
    return False


def shadow_log(decision):
    """RD-LOOP-01 item 5: log do modo shadow — o que o consumer FARIA, sem despachar."""
    line = json.dumps({**decision, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "mode": "shadow"}, ensure_ascii=False)
    try:
        with open(SHADOW_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _entry_fingerprint(entry):
    """RD-LOOP-01: identidade da entrada para remoção pós-consumo (id+ts+payload)."""
    return json.dumps({"id": entry.get("id"), "enqueuedAt": entry.get("enqueuedAt"),
                       "payload": entry.get("payload")}, sort_keys=True, default=str)


def _mission_cwd(mission_id, payload):
    """cwd do despacho: payload primeiro, senão o cwd do ledger (autoridade)."""
    cwd = str(payload.get("cwd") or "").strip()
    if cwd:
        return cwd
    return str(_ledger(mission_id).get("cwd") or "").strip()


def consume_queue(dry_run=False, max_promotions=MAX_PROMOTIONS, shadow=False):
    state = read_state()
    if shadow:
        # RD-LOOP-01 item 5: shadow decide mas NUNCA muta o estado de produção
        import copy
        state = copy.deepcopy(state)
        # ORCH-LIVENESS-02 item 1/4: batimento do shadow vai para o ARQUIVO DELE —
        # nunca em HEARTBEAT_PATH (liveness do consumer de produção é exclusiva dele).
        _write_heartbeat(SHADOW_HEARTBEAT_PATH, "shadow")
    else:
        # ORCH-LIVENESS-02: 'alive' só sai daqui — o próprio consumer vivo, com
        # batimento (PID + ts) gravado na MESMA passada.
        _write_heartbeat(HEARTBEAT_PATH, "alive")
    state["status"] = "shadow-deciding" if shadow else "alive"
    if not shadow:
        # ORCH-LIVENESS-02 item 1: o PID do writer vivo vai no state — leitores
        # (mission_watch/orchestrate.list) passam a poder conferir kill -0.
        state["pid"] = os.getpid()
    state["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # log de promoções: em memória durante a varredura (fonte dos gates e do detector)
    state.setdefault("promotions", state_promotions())

    # Read queue
    entries = []
    try:
        with open(QUEUE_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and "id" in entry and "type" in entry:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return {"consumed": 0, "promoted": 0, "skipped": 0, "blocked": 0, "throttled": 0, "operatorRequired": 0, "deadLettered": 0, "requeued": 0, "gated": 0, "results": []}

    # Sort by priority then enqueuedAt
    entries.sort(key=lambda e: (e.get("priority", 5), e.get("enqueuedAt", "")))

    result = {"consumed": len(entries), "promoted": 0, "skipped": 0, "blocked": 0, "throttled": 0, "operatorRequired": 0, "deadLettered": 0, "requeued": 0, "gated": 0, "deferred": 0, "results": []}
    promoted_count = 0
    consumed_fps = set()   # fingerprints consumidos nesta passada (saem da fila)
    requeue_entries = []   # cópias com _attempt_count (recolocadas no reescrito final)
    components_dispatched = set()   # RD-DISO-01 item 4: grupos já despachados nesta passada

    if not acquire_lock():
        log("consume_queue: lock held by another cycle")
        return result

    try:
        # RD-LOOP-01 item 4: detector de loop antes de promover. Em shadow, só decide
        # (decisão vai para o shadow log; produção nunca é mutada).
        if shadow:
            _trip = check_loop_breaker(state, emit=False)
            shadow_log({"kind": "loopBreaker", "wouldTrip": _trip,
                        "active": bool(state.get("loopBreaker", {}).get("active")),
                        "promotions15m": state.get("loopBreaker", {}).get("promotions15m")})
        elif check_loop_breaker(state):
            log("consume_queue: loop breaker ativo — nenhuma promoção neste ciclo")
            result["results"].append({"action": "loop_breaker", "reason": "auto-corte ativo (dispatch_loop_detected) — intervenção do operator obrigatória"})
            state["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_state(state)
            return result

        for entry in entries:
            if promoted_count >= max_promotions:
                break

            payload = entry.get("payload") or {}
            mission_id = payload.get("missionId") or entry.get("id")

            # RD-ORCH-DEPS-01: checagem de depends_on ANTES de qualquer gate de
            # despacho. Flag OFF (default) → depends_on ignorado (hoje, intacto).
            if DEPS_ON:
                _unmet = deps_unmet(payload)
                if _unmet:
                    spool("orch_blocked", mission_id,
                          "DEPS_NOT_MET: prerequisitos nao satisfeitos: " + ",".join(_unmet))
                    result["results"].append({"entryId": entry["id"], "action": "blocked",
                                              "reason": "DEPS_NOT_MET", "missionId": mission_id,
                                              "unmetDeps": _unmet})
                    result["blocked"] += 1
                    consumed_fps.add(_entry_fingerprint(entry))
                    continue  # sem requeue, sem loop — operator resolve

            # ORCH-AGENT (operator 08/10): entrada type=agent → despacha direto
            # ao agente-profile, SEM gates de missão (operatorOrder no payload).
            if entry.get("type") == "agent":
                _op_ord = str((payload or {}).get("operatorOrder") or "").strip()
                if not _op_ord:
                    result["results"].append({"entryId": entry["id"], "action": "gated", "reason": "AGENT_OPERATOR_ORDER_REQUIRED"})
                    result["gated"] += 1
                    continue
                _agent_result = dispatch_agent(entry)
                if _agent_result.get("ok"):
                    result["results"].append({"entryId": entry["id"], "action": "promoted", "reason": f"agent={_agent_result['agent']}", "outfile": _agent_result["outfile"]})
                    result["promoted"] += 1
                    promoted_count += 1
                    consumed_fps.add(_entry_fingerprint(entry))
                else:
                    result["results"].append({"entryId": entry["id"], "action": "deadLettered", "reason": str(_agent_result.get("error"))[:120]})
                    result["deadLettered"] += 1
                    consumed_fps.add(_entry_fingerprint(entry))
                continue

            prompt_file = payload.get("prompt") or payload.get("promptFile") or payload.get("contractFile")
            worktree = payload.get("worktree")
            # RD-DISO-01 item 1: worktree PRÓPRIO é o default do despacho da fila
            # (payload `worktree: disabled/false/0/off` desliga explicitamente).
            _wt_raw = str(worktree or "").strip().lower()
            _worktree_req = "" if _wt_raw in ("disabled", "false", "0", "off") else "required"
            priority = entry.get("priority", 5)
            component = str(payload.get("component") or "").strip()

            # Rule: promptFile inexistent → skip
            if not prompt_file or not os.path.exists(prompt_file):
                spool("orch_skip", mission_id, f"promptFile inexistente: {prompt_file or '(nenhum)'}")
                result["results"].append({"entryId": entry["id"], "action": "skipped", "reason": "promptFile inexistente", "missionId": mission_id})
                result["skipped"] += 1
                consumed_fps.add(_entry_fingerprint(entry))
                continue

            # RD-LOOP-01 item 2: preflight determinístico ANTES de despachar.
            # Falhou → NÃO despacha; gate-operator com motivo tipado (anti-spam:
            # mesmo código na mesma entrada não re-marca).
            # OPORDER-BYPASS-0810: intent com operatorOrder (cap/dedupe, header
            # linha 20) pula o preflight — a ordem segue ao handler, que decide.
            _op_ord = str((payload or {}).get("operatorOrder") or "").strip()
            gate = None if _op_ord else dispatch_preflight(mission_id, _mission_cwd(mission_id, payload), state)
            if gate:
                code, detail = gate
                prev = (state.get("gatedEntries") or {}).get(str(entry["id"]))
                if shadow:
                    shadow_log({"kind": "gate", "entryId": entry["id"], "missionId": mission_id,
                                "code": code, "detail": detail[:200],
                                "repeat": bool(prev and prev.get("code") == code)})
                else:
                    if not (prev and prev.get("code") == code):
                        spool("orch_gate_operator", mission_id, f"{code}: {detail}")
                        state.setdefault("gatedEntries", {})[str(entry["id"])] = {
                            "code": code, "missionId": mission_id, "detail": detail[:200],
                            "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    result["results"].append({"entryId": entry["id"], "action": "gated", "reason": f"{code}: {detail[:200]}", "missionId": mission_id})
                    result["gated"] += 1
                continue

            # Rule: class-based routing via routing table
            routing_table = _routing_table_cache or load_routing_table()
            try:
                with open(prompt_file) as f:
                    prompt_raw = f.read()

                class_name = parse_frontmatter_class(prompt_raw)
                if class_name is None:
                    class_name = "mecanica"  # default class

                # RD-DISO-01 item 4: componente do intent — payload > frontmatter
                # `component:` > linha `**Componente:**` do contrato. Grupo do scheduler.
                if not component:
                    m = (re.search(r"^component:\s*(\S.*)$", prompt_raw, re.MULTILINE)
                         or re.search(r"\*\*Componente:\*\*\s*(\S.*)$", prompt_raw, re.MULTILINE))
                    if m:
                        component = m.group(1).strip().strip("\"'")[:120]

                worker_model = get_routed_worker(class_name, routing_table)

                if worker_model is None:
                    # pesada (or unknown class with null worker) → operator required
                    routing_info = json.dumps(routing_table.get("classes", {}).get(class_name, {}), default=str)
                    spool(
                        "orch_route_operator_required",
                        mission_id,
                        f"class={class_name} worker=null routing={routing_info[:200]}",
                    )
                    result["results"].append({
                        "entryId": entry["id"],
                        "action": "operator_required",
                        "reason": f"class={class_name} requires operator (no worker in routing table)",
                        "missionId": mission_id,
                        "class": class_name,
                    })
                    result["operatorRequired"] += 1
                    continue  # fica na fila aguardando operator (comportamento pré-existente)

                # Non-pesada class with a worker → write model pin to settings.json
                # (pin por path real de worktree; flag do DISO não é caminho)
                write_settings_json_pin(worker_model, mission_id,
                                        worktree if isinstance(worktree, str) and "/" in worktree else None)

            except Exception as e:
                # If frontmatter parsing or routing fails, log and skip
                spool("orch_skip", mission_id, f"routing error: {str(e)[:200]}")
                result["results"].append({"entryId": entry["id"], "action": "skipped", "reason": f"routing error: {str(e)[:200]}", "missionId": mission_id})
                result["skipped"] += 1
                consumed_fps.add(_entry_fingerprint(entry))
                continue

            # ── RD-DISO-01 item 2: LEASE de componente — componente em lease ativo de
            # OUTRA missão = recusa tipada COMPONENT_LEASED → reenfileira sozinho
            # (staggering; crash-safe: TTL vence lease sem heartbeat). item 4: dentro
            # do grupo, despacho em SÉRIE — próxima entrada do MESMO componente fica
            # na fila (ilesa) até o fecho/liberação do lease; entre grupos, paralelo.
            if component:
                _holder = _lease_holder(component)
                if _holder and _holder != mission_id:
                    _wait_since = str(payload.get("_lease_wait_since") or
                                      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                    _wait_epoch = _parse_iso_flex(_wait_since) or time.time()
                    if shadow:
                        shadow_log({"kind": "would_requeue_lease", "entryId": entry["id"],
                                    "missionId": mission_id, "component": component,
                                    "holder": _holder})
                        continue
                    if time.time() - _wait_epoch > LEASE_STAGGER_MAX_S:
                        spool("orch_dead_letter", mission_id,
                              "lease de %s não liberou em 24h (dono %s)" % (component, _holder))
                        result["results"].append({"entryId": entry["id"], "action": "dead_letter",
                                                  "reason": "COMPONENT_LEASED > 24h (dono %s)" % _holder,
                                                  "missionId": mission_id})
                        result["deadLettered"] += 1
                        consumed_fps.add(_entry_fingerprint(entry))
                    else:
                        requeue_entries.append({**entry, "payload": {**payload,
                                                                     "_lease_wait_since": _wait_since}})
                        spool("orch_requeue", mission_id,
                              "COMPONENT_LEASED: componente %s em lease de %s — staggering"
                              % (component, _holder))
                        result["results"].append({"entryId": entry["id"], "action": "requeued",
                                                  "reason": "COMPONENT_LEASED (dono %s)" % _holder,
                                                  "missionId": mission_id})
                        result["requeued"] += 1
                        consumed_fps.add(_entry_fingerprint(entry))
                    continue
                if component in components_dispatched:
                    if shadow:
                        shadow_log({"kind": "would_defer_series", "entryId": entry["id"],
                                    "missionId": mission_id, "component": component})
                        continue
                    result["results"].append({"entryId": entry["id"], "action": "deferred",
                                              "reason": "série do componente %s — aguarda fecho/liberação do lease" % component,
                                              "missionId": mission_id})
                    result["deferred"] += 1
                    continue  # fica na fila (NÃO consome) — próxima da série

            # Rule: plan GO required
            plan = run_orchestrate_plan()
            if plan["verdict"] == "BLOCK":
                spool("orch_blocked", mission_id, f"plan BLOCK: {'; '.join(plan.get('blockReasons', []))}")
                result["results"].append({"entryId": entry["id"], "action": "blocked", "reason": "plan BLOCK", "missionId": mission_id})
                result["blocked"] += 1
                break

            if plan["verdict"] == "THROTTLE":
                spool("orch_throttled", mission_id, f"plan THROTTLE: {'; '.join(plan.get('throttleReasons', []))}")
                result["results"].append({"entryId": entry["id"], "action": "throttled", "reason": "plan THROTTLE", "missionId": mission_id})
                result["throttled"] += 1
                continue

            # GO → dispatch
            # RD-LOOP-01 item 5: shadow NUNCA despacha — loga o que FARIA e segue.
            if shadow:
                shadow_log({"kind": "would_dispatch", "entryId": entry["id"],
                            "missionId": mission_id, "promptFile": str(prompt_file),
                            "worktree": _worktree_req, "worktreePayload": worktree,
                            "priority": priority, "plan": "GO"})
                continue
            if dry_run:
                spool("orch_promoted", mission_id, "dry-run: despacho simulado (GO)")
                result["results"].append({"entryId": entry["id"], "action": "promoted", "reason": "plan GO (dry run)", "missionId": mission_id})
                result["promoted"] += 1
                promoted_count += 1
                continue

            # GO → despacho (worktree próprio por default — RD-DISO-01 item 1)
            _t_dispatch = time.time()
            _runner = get_routed_runner(class_name, routing_table)
            if _runner == "harness":
                                dispatch_result = dispatch_via_harness(
                                    mission_id, prompt_file, _mission_cwd(mission_id, payload),
                                    budget=float(payload.get("budget") or 0.5),
                                    max_turns=int(payload.get("maxTurns") or 30),
                                    seed=(int(payload["seed"]) if payload.get("seed") else None),
                                    spawned_by=payload.get("spawnedBy"),
                                    consequence=payload.get("consequence"))
            else:
                dispatch_result = dispatch_mission(mission_id, prompt_file, _worktree_req, priority, payload=payload)
            # ORCH-DISPATCH-TIPO-01: defesa em profundidade — dispatch_result
            # não-dict (str/list/None de caminho futuro) vira falha tipada da
            # entrada; o ciclo NUNCA morre por causa de um dispatch individual.
            if not isinstance(dispatch_result, dict):
                log(f"consume_queue: dispatch_result não-dict de {mission_id}: "
                    f"{repr(dispatch_result)[:200]}")
                dispatch_result = {"ok": False,
                                    "error": f"payload não-dict: {repr(dispatch_result)[:200]}"}
            _record_latency("dispatch_call_ms", mission_id, (time.time() - _t_dispatch) * 1000.0,
                            fallback=not bool(dispatch_result.get("ok")),
                            detail="subprocess handle_mission_dispatch")
            _disp_status = str(dispatch_result.get("status") or "")
            if dispatch_result.get("ok") and _disp_status != "no_op":
                # HEADLESS-TAB-01: aba RUN:<id>#<seed> para missão de fila (fail-open)
                try:
                    ensure_run_tab(mission_id,
                                   str(dispatch_result.get("run_dir") or _mission_cwd(mission_id, payload)),
                                   seed=dispatch_result.get("seed"))
                except Exception as _tab_e:
                    log("TAB_CREATE_FAILED: %s %s" % (mission_id, str(_tab_e)[:200]))
                record_promotion(mission_id, state)
                if component:
                    components_dispatched.add(component)
                _record_latency("dispatch_e2e_ms", mission_id,
                                (time.time() - (_parse_iso_flex(entry.get("enqueuedAt")) or time.time())) * 1000.0,
                                detail="enqueuedAt→dispatched")
                spool("orch_promoted", mission_id, "despachado via handle_mission_dispatch")
                # VIGIA-DELIVER-01: aviso de decolagem — mission_dispatched
                # (dedupe por assinatura: emitido 1x por missão) e supersede do
                # aviso de enfileiramento anterior (superseded por missionId).
                try:
                    sys.path.insert(0, "/root/.hermes/plugins/mission-ops")
                    from notify import mission_dispatched  # noqa: E402
                    mission_dispatched(mission_id)
                    spool("orch_decolagem", mission_id,
                          "decolagem: aviso mission_dispatched emitido; aviso de enfileiramento superseded")
                except Exception as _dec_exc:
                    spool("orch_decolagem_erro", mission_id,
                          "mission_dispatched falhou: %s" % type(_dec_exc).__name__)
                result["results"].append({"entryId": entry["id"], "action": "promoted", "reason": "plan GO", "missionId": mission_id})
                result["promoted"] += 1
                promoted_count += 1
                consumed_fps.add(_entry_fingerprint(entry))
                state.get("gatedEntries", {}).pop(str(entry["id"]), None)

                # Divergence detection: compare routed model with actual model from transcript
                try:
                    mission_state = read_json(os.path.join("/root/.hermes/mission-state", f"{mission_id}.json"))
                    if mission_state:
                        actual_model = mission_state.get("engine") or mission_state.get("model") or mission_state.get("workerModel")
                        if actual_model:
                            check_divergence(worker_model, actual_model, mission_id)
                except Exception:
                    pass

                # Trindade line generation: read ledger from mission state and emit
                try:
                    mission_state = read_json(os.path.join("/root/.hermes/mission-state", f"{mission_id}.json"))
                    if mission_state:
                        ledger = mission_state.get("ledger") or mission_state.get("spend") or mission_state.get("trindade")
                        if ledger:
                            trindade_line = generate_trindade_line(ledger)
                            if trindade_line:
                                spool("orch_trindade", mission_id, trindade_line)
                except Exception:
                    pass

            else:
                _error = str(dispatch_result.get("error") or "unknown")
                # ── RD-DISO-01: recusas tipadas que a fila resolve SOZINHA (nunca
                # gate-operator, nunca fantasma). Lease: staggering sem consumir
                # tentativa (dead-letter só após 24h esperando o MESMO holder);
                # pane/worktree: backoff padrão.
                if _error == "COMPONENT_LEASED":
                    _wait_since = str(payload.get("_lease_wait_since") or
                                      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                    _wait_epoch = _parse_iso_flex(_wait_since) or time.time()
                    if time.time() - _wait_epoch > LEASE_STAGGER_MAX_S:
                        spool("orch_dead_letter", mission_id,
                              "COMPONENT_LEASED > 24h — plugin recusou lease (%s)" % _error)
                        result["results"].append({"entryId": entry["id"], "action": "dead_letter",
                                                  "reason": "COMPONENT_LEASED > 24h", "missionId": mission_id})
                        result["deadLettered"] += 1
                        consumed_fps.add(_entry_fingerprint(entry))
                    else:
                        requeue_entries.append({**entry, "payload": {**payload,
                                                                     "_lease_wait_since": _wait_since}})
                        spool("orch_requeue", mission_id,
                              "COMPONENT_LEASED (plugin) — staggering sem consumir tentativa")
                        result["results"].append({"entryId": entry["id"], "action": "requeued",
                                                  "reason": "COMPONENT_LEASED", "missionId": mission_id})
                        result["requeued"] += 1
                        consumed_fps.add(_entry_fingerprint(entry))
                    continue
                if _error in _REQUEUE_CODES:
                    attempt_count = payload.get("_attempt_count", 0) + 1
                    if attempt_count >= MAX_ATTEMPTS:
                        spool("orch_dead_letter", mission_id,
                              "%s em %d tentativas" % (_error, attempt_count))
                        result["results"].append({"entryId": entry["id"], "action": "dead_letter",
                                                  "reason": _error, "missionId": mission_id})
                        result["deadLettered"] += 1
                        consumed_fps.add(_entry_fingerprint(entry))
                    else:
                        requeue_entries.append({**entry, "payload": {**payload,
                                                                     "_attempt_count": attempt_count}})
                        spool("orch_requeue", mission_id,
                              "%s — reenfileirado (tentativa %d, backoff %ds)"
                              % (_error, attempt_count, 2 ** attempt_count))
                        result["results"].append({"entryId": entry["id"], "action": "requeued",
                                                  "reason": "%s (tentativa %d)" % (_error, attempt_count),
                                                  "missionId": mission_id})
                        result["requeued"] += 1
                        consumed_fps.add(_entry_fingerprint(entry))
                    continue
                # RD-LOOP-01: gate do PRÓPRIO plugin (handle_mission_dispatch) não é
                # falha de transporte — é gate-operator; não re-enfileira nem dead-letter.
                if _error in _PLUGIN_GATE_CODES:
                    prev = (state.get("gatedEntries") or {}).get(str(entry["id"]))
                    if not (prev and prev.get("code") == _error):
                        spool("orch_gate_operator", mission_id, f"{_error}: {str(dispatch_result.get('detail') or '')[:200]}")
                        state.setdefault("gatedEntries", {})[str(entry["id"])] = {
                            "code": _error, "missionId": mission_id,
                            "detail": str(dispatch_result.get("detail") or "")[:200],
                            "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    result["results"].append({"entryId": entry["id"], "action": "gated", "reason": _error, "missionId": mission_id})
                    result["gated"] += 1
                    continue
                # RD-LOOP-01: no_op não é promoção — a missão já está ativa; consumir a
                # entrada como skipped (era exatamente o loop vivo de 05/10: no_op
                # contado como sucesso a cada varredura).
                if dispatch_result.get("ok"):
                    spool("orch_skip", mission_id, "no_op: missão já despachada/ativa — não conta como promoção")
                    result["results"].append({"entryId": entry["id"], "action": "skipped", "reason": "already_dispatched (no_op)", "missionId": mission_id})
                    result["skipped"] += 1
                    consumed_fps.add(_entry_fingerprint(entry))
                    state.get("gatedEntries", {}).pop(str(entry["id"]), None)
                    continue
                # Failure handling with backoff
                attempt_count = payload.get("_attempt_count", 0) + 1
                error = _error
                if attempt_count >= MAX_ATTEMPTS:
                    spool("orch_dead_letter", mission_id, f"3 tentativas falhas: {error[:200]}")
                    result["results"].append({"entryId": entry["id"], "action": "dead_letter", "reason": error[:200], "missionId": mission_id})
                    result["deadLettered"] += 1
                    consumed_fps.add(_entry_fingerprint(entry))
                else:
                    # Re-enqueue with backoff (cópia recolocada no reescrito final;
                    # original sai da fila — sem duplicar a cada tentativa)
                    updated_payload = {**payload, "_attempt_count": attempt_count}
                    requeue_entries.append({**entry, "payload": updated_payload})
                    backoff = 2 ** attempt_count
                    spool("orch_requeue", mission_id, f"re-enfileirado (tentativa {attempt_count}, backoff {backoff}s): {error[:200]}")
                    result["results"].append({"entryId": entry["id"], "action": "requeued", "reason": f"requeued attempt {attempt_count}", "missionId": mission_id})
                    result["requeued"] += 1
                    consumed_fps.add(_entry_fingerprint(entry))
    finally:
        release_lock()

    # RD-DISO-01 fix 6: TODO consumo real da fila (promovido/skipped/no_op/dead-letter/
    # re-enfileirado) entra no consumedLog — a calibração do breaker compara promoções
    # com consumo da MESMA janela (progresso real), não com burst isolado.
    if not shadow and consumed_fps:
        state.setdefault("consumedLog", []).extend([time.time()] * len(consumed_fps))
        # higiene: janela útil é 15min; cap de memória (24h + margem)
        cutoff = time.time() - (CAP_WINDOW_S + 3600)
        state["consumedLog"] = [t for t in state["consumedLog"] if t >= cutoff]

    # RD-LOOP-01: consumo REAL da fila — entradas promovidas/skipped/no_op/
    # dead-lettered/re-enfileiradas SAEM da fila (antes: ficavam para sempre e
    # eram reprocessadas a cada varredura — amplificador do loop de 05/10).
    # Novas entradas chegadas durante a varredura são preservadas (por fingerprint).
    if not dry_run and not shadow and consumed_fps:
        _kept, _dropped = [], 0
        try:
            with open(QUEUE_PATH) as f:
                _live = f.readlines()
        except FileNotFoundError:
            _live = []
        for _ln in _live:
            _s = _ln.strip()
            if not _s:
                continue
            try:
                _e = json.loads(_s)
            except json.JSONDecodeError:
                _kept.append(_ln)
                continue
            if isinstance(_e, dict) and _entry_fingerprint(_e) in consumed_fps:
                _dropped += 1
                continue
            _kept.append(_ln)
        # REQUEUE-GUARD-0810 (FIND-86f9a5f3): nunca re-enfileirar um id que já
        # voltou pra fila — o requeue anterior não-consumido + append novo
        # multiplicava a MESMA intent a cada ciclo (795 duplicatas medidas).
        _kept_ids = set()
        for _ln in _kept:
            try:
                _kid = json.loads(_ln).get("id")
            except Exception:
                continue
            if isinstance(_kid, str):
                _kept_ids.add(_kid)
        _rq_deduped = 0
        for _e in requeue_entries:
            _rid = _e.get("id") if isinstance(_e, dict) else None
            if isinstance(_rid, str) and _rid in _kept_ids:
                _rq_deduped += 1
                continue
            if isinstance(_rid, str):
                _kept_ids.add(_rid)
            _kept.append(json.dumps(_e) + "\n")
        if _rq_deduped:
            log(f"consume_queue: requeue-guard pulou {_rq_deduped} re-enfileiramento(s) de id já presente")
        _tmp = QUEUE_PATH + ".tmp"
        with open(_tmp, "w") as f:
            f.writelines(_kept)
        os.replace(_tmp, QUEUE_PATH)
        if _dropped:
            log(f"consume_queue: fila reescrita — {_dropped} entradas consumidas removidas, {len(requeue_entries)} re-enfileiradas")

    # Update state (shadow: decide, mas NUNCA persiste estado de produção)
    state["promotedCount"] = (state.get("promotedCount") or 0) + result["promoted"]
    state["skippedCount"] = (state.get("skippedCount") or 0) + result["skipped"]
    state["blockedCount"] = (state.get("blockedCount") or 0) + result["blocked"]
    state["requeuedCount"] = (state.get("requeuedCount") or 0) + result["requeued"]
    state["deadLetteredCount"] = (state.get("deadLetteredCount") or 0) + result["deadLettered"]
    # RD-ORCH-GHOST-02: skip no_op/requeue/dead-letter nunca avançam lastPromotion (fonte do GHOST FIND-faa7ad08)
    if result["promoted"]:
        last = result["results"][-1]
        state["lastPromotion"] = state["updatedAt"]
        state["lastPromotionId"] = last.get("entryId")
    if not shadow:
        write_state(state)

    return result


def health_check():
    """Deterministic health endpoint. ORCH-LIVENESS-02 item 2: além das chaves
    legadas, expõe o health tipado {alive, reason} com fonte de verdade no PID
    (heartbeat + kill -0 + frescor + sd_notify)."""
    state = read_state()
    return {
        "status": "ok",
        "consumer": state.get("status", "stopped"),
        "lastPromotion": state.get("lastPromotion"),
        "promotedCount": state.get("promotedCount", 0),
        "uptime": int(time.time() - float(os.environ.get("START_TIME", time.time()))),
        "health": consumer_health(),
    }


def main():
    # RD-DISO-01 fix 5: ping do watchdog (WatchdogSec=120) DURANTE despachos longos —
    # thread que pinge a cada 30s enquanto o ciclo roda. O crash-loop de 05/10
    # (restart counter 9) era exatamente o watchdog matando o processo no meio de
    # um despacho sem ping (o script nunca chamava sd_notify).
    _wd_stop = None
    if os.environ.get("NOTIFY_SOCKET"):
        import threading
        _wd_stop = threading.Event()

        def _wd_ping_loop():
            while not _wd_stop.wait(30):
                _sd_notify()

        threading.Thread(target=_wd_ping_loop, daemon=True, name="watchdog-ping").start()
    try:
        _run_main()
    finally:
        if _wd_stop is not None:
            _wd_stop.set()


def _run_main():
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        print(json.dumps(health_check()))
        sys.exit(0)

    # RD-LOOP-01 item 5: modo shadow — varreduras só decidindo, log em SHADOW_LOG_PATH.
    if len(sys.argv) > 1 and sys.argv[1] == "shadow":
        cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 0  # 0 = contínuo até Ctrl-C
        load_routing_table()
        log("orchestrator-consumer SHADOW starting (soak de realidade — nunca despacha)")
        n = 0
        try:
            while cycles == 0 or n < cycles:
                t0 = time.time()
                try:
                    res = consume_queue(shadow=True)
                    log(f"shadow cycle {n + 1}: {json.dumps({k: v for k, v in res.items() if k != 'results'})}")
                except Exception as e:
                    log(f"shadow consume_queue error: {e}")
                n += 1
                elapsed = time.time() - t0
                time.sleep(max(5, INTERVAL - elapsed))
        except KeyboardInterrupt:
            pass
        finally:
            log(f"orchestrator-consumer SHADOW ended after {n} cycles")
        sys.exit(0)

    # ORCH-LIVENESS-02: auto-detecção de fantasma — pode ser rodada isolada
    # (mission-watcher chama reconcile_state() importando este arquivo; o CLI
    # cobre diagnóstico pontual e a prova E2E).
    if len(sys.argv) > 1 and sys.argv[1] == "reconcile":
        print(json.dumps(reconcile_state(emit=True), ensure_ascii=False))
        sys.exit(0)

    # RD-LOOP-01 item 4: liberação do auto-corte — ordem do operator (intervenção
    # obrigatória após dispatch_loop_detected). Registra a liberação no bus.
    if len(sys.argv) > 1 and sys.argv[1] == "reset-loop-breaker":
        state = read_state()
        lb = state.get("loopBreaker") or {}
        state["loopBreaker"] = {"active": False,
                                "resetAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "previous": lb}
        state["loopStreak"] = {"n": 0, "lastTs": None}  # fix 6: streak reinicia junto
        write_state(state)
        spool("orch_loop_breaker_reset", "*", "loop breaker resetado por ordem do operator")
        log("loop breaker reset by operator")
        print(json.dumps({"ok": True, "loopBreaker": state["loopBreaker"]}))
        sys.exit(0)

    # Load routing table at startup
    load_routing_table()

    log("orchestrator-consumer starting")
    # ORCH-LIVENESS-02: o consumer escreve o PRÓPRIO pid (o ExecStartPre do unit
    # gravava o pid do bash -c, já morto — era a fonte da mentira 'alive').
    try:
        with open(PID_PATH, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    while True:
        _sd_notify()  # fix 5: ping determinístico por ciclo (WatchdogSec=120)
        _write_heartbeat(HEARTBEAT_PATH, "alive")  # ORCH-LIVENESS-02: batimento por ciclo
        t0 = time.time()
        try:
            consume_queue()
        except Exception as e:
            log(f"consume_queue error: {e}")
        elapsed = time.time() - t0
        sleep_time = max(5, INTERVAL - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()

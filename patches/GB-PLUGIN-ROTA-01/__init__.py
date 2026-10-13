"""MISSION-OPS-02 — plugin mission-ops do Hermes (lado Hermes).

11 tools (toolset "mission-ops"), zero LLM:
  mission_dispatch      — cria ABA PRÓPRIA (herdr tab create) + rename MISSION:<id>, abre claude,
                          entrega o prompt com retry (deliver_prompt). Split do sourcePaneId só
                          como fallback se o tab create falhar. Idempotente (ledger-first NO_OP);
                          status prompt_failed re-tenta a entrega no pane existente.
                          CHAIN-DISPATCH-GOV-01: ledger grava spawned_by/chain_depth; worker só
                          despacha com badge allow_chain_dispatch e até mission.chain_depth_max.
  mission_batch         — MISSION-BATCH-01: 2-6 despachos SEQUENCIAIS numa chamada, tolerante a
                          falha por item, anti-fantasma (ledger morto -> cancelled -> re-despacho).
  mission_watch         — watchdog orientado a evento (herdr pane wait-output, nunca polling);
                          NOVO: pane_closed/tab_closed (missão encerrada de fora) e
                          ready_regex_error (claude parou em tela de erro/trust).
  mission_recover       — receitas DETERMINÍSTICAS: interrupted, palette, transcript400,
                          shell_fallback, autocompact, ready_regex_error (relança claude no cwd
                          com config). Desconhecido = needs_supervisor.
  mission_snapshot      — SNAPSHOT-FAST-01: ledger + pane REAL + verdict (OK/PANEID_OBSOLETO/
                          FANTASMA/INTERROMPIDA) em 1 chamada; auto-corrige SÓ o ledger (resync
                          de paneId via aba MISSION:<id>; sem aba = fantasma cancelado).
  mission_status        — ledger + último evento em 1 chamada.
  mission_read          — pane read com lines/source/maxBytes (substitui o herdr manual).
  mission_nudge         — intervenção do SUPERVISOR: nudge atômico CHECK->SEND->VERIFY
                          (recusa working ativo, dedupe <60s, sender no audit, verify).
  mission_list          — tab list + pane list + ledgers unificados numa resposta só.
  mission_close         — encerramento limpo: DELIVER-VERIFY (verify.json no cwd → runner
                          determinístico; VERDE grava badge verified_e2e, VERMELHO reabre) ->
                          /exit -> tab close -> worktree cleanup (se gravado no ledger) ->
                          ledger status closed. GUARDA DE CONSEQUÊNCIA (CLOSE-VERIFY-GUARD-01):
                          consequence declarada sem verify.json → reabre (verify_required);
                          só heurística → fecha com closed_unverified_consequence + warning.
  mission_worktree_add  — herdr worktree create ligado ao ciclo da missão (grava no ledger).
  mission_worktree_remove — remove APENAS worktree gravado no ledger (nunca remove às cegas).
  mission_verify        — roda /opt/deliver-verify/verify.py (zero-LLM) sob demanda
                          (DELIVER-VERIFY-01); o supervisor Hermes/TRINITY chama como tool.
  mission_verify_author — GERA verify.json de prova real (relatório > prompt > fallback),
                          _provenance por item, diff antes de gravar, force p/ sobrescrever,
                          mission_verify logo após (VERIFY-MANIFEST-01).
  mission_approval_request — GUARDIAN-MOBILE-01: approval card no Telegram (resumo tipado +
                          inline keyboard APROVAR/CANCELAR); toque = ordem injetada no
                          intent/ledger com identidade SEC-OPERATOR-IDENTITY-01; sem toque no
                          TTL permanece pendente (fail-closed); canal inactive = fallback
                          honesto via supervisor.
  mission_approval_status — estado do approval card (pending/approved/cancelled + ordem
                          injetada); leitura pura.
  mission_debt         — RD-DEBT-01 (DEBT-SWEEP-01): ciclo de vida das dívidas herdadas
                          (registry debts.jsonl, zero LLM): painel (list), envelhecimento
                          (aging: >3d prio 2, >7d P1 + finding no bus), citação do operator
                          (cited → P1 mecânico). Captura/dedupe/promoção/fecho vivem no
                          passo debt_sweep do mission_close.

Padrão de robustez (MISSION-OPS-02): toda falha vira {ok:false, error, detail} estruturado —
nada de crash; timeout hard por chamada herdr; retry onde faz sentido (prompt delivery).
Nenhuma tool aprova/mergea/deploa — transporte, observação e recuperação determinística apenas.
"""

from __future__ import annotations

import calendar
import datetime
import hashlib
import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

try:
    from . import mission_core as mc  # gateway carrega o plugin como pacote
except ImportError:
    import mission_core as mc        # suíte/sys.path top-level — IMPORT-FIX-02 30/09
try:
    from . import recipes as rc
except ImportError:
    import recipes as rc
try:
    from . import verify_gate as vg
except ImportError:
    import verify_gate as vg
try:
    from . import close_commit_guard as cg  # CLOSE-COMMIT-01: entrega não-commitada
except ImportError:
    import close_commit_guard as cg
try:
    from . import close_ship as cs  # CLOSE-SHIP-VISIBILITY-01: guard "merged?" + SHIP
except ImportError:
    import close_ship as cs
try:
    from . import obedience as ob  # SUP-OBEY-01: guardas de obediência do supervisor
except ImportError:
    import obedience as ob
try:
    from . import supervisor_guard as sg  # GUARD-SUPERVISOR-READONLY-01: guarda do supervisor
except ImportError:
    import supervisor_guard as sg
try:
    from . import approval_card as ac  # GUARDIAN-MOBILE-01: approval cards no Telegram
except ImportError:
    import approval_card as ac
# CLOSE-SHIP-VISIBILITY-01: entry do dispatch injetado no close_ship (import circular
# resolvido na chamada — handle_mission_dispatch é global deste módulo)
cs._dispatch = lambda args: handle_mission_dispatch(args)
try:
    from . import verify_author as va
except ImportError:
    import verify_author as va
try:
    import mission_resume as mr
except ImportError:  # OOM-GUARD 27/09: import circular/transiente sob pressão de memória
    mr = None         # resolve lazy no handler mission_resume()
try:
    from . import notify as nf  # pacote (gateway hermes_plugins.*)
except ImportError:
    import notify as nf         # top-level (suíte/sys.path) — IMPORT-FIX-02 30/09
try:
    import trinity_wire as _tw  # TRINITY-WIRE-01: advisor + supervisor checkpoints
except ImportError:
    _tw = None
try:
    from . import roadmap_debts as rd  # RD-OPS-03-SPEND-01: dívidas herdadas no close
except ImportError:
    import roadmap_debts as rd
try:
    from . import mission_debts as mdb  # RD-DEBT-01: ciclo de vida das dívidas (DEBT-SWEEP-01)
except ImportError:
    import mission_debts as mdb
try:
    from . import obey_registry as obr  # RD-OBEY-02: obediência por mecanismo (registry/gates/ack/score)
except ImportError:
    import obey_registry as obr
try:
    from . import component_leases as leases  # RD-DISO-01: lease de componente
except ImportError:
    import component_leases as leases
try:
    from . import findings as fd  # FINDINGS-01: registro/aging/digest de findings (catálogo como dado)
except ImportError:
    import findings as fd
try:
    from . import latency as lat  # RD-DISO-01 item 8: latência medida em todo caminho
except ImportError:
    import latency as lat

# MISSION-SUPERVISOR-01 (28/09): supervisor por missão — nasce no dispatch, morre no
# close, renasce no recover, vigia no watch_cycle. Wiring com fail-open fora do
# dispatch (o hook só age com STATE_DIR de produção; suíte com tmp dir não sobe).
_MS_HOOK = "/opt/mission-supervisor/mission_supervisor_hook.py"
try:
    import importlib.util as _ilu
    _ms_spec = _ilu.spec_from_file_location("mission_supervisor_hook", _MS_HOOK)
    ms = _ilu.module_from_spec(_ms_spec)
    _ms_spec.loader.exec_module(ms)
except Exception:
    ms = None


# ---------------------------------------------------------------- handlers

def handle_mission_ledger_fix(args: Dict[str, Any]) -> Dict[str, Any]:
    """Valida missionId, carrega ledger, aplica status/paneId/tabId (só campos presentes),
    rejeita status fora do enum, grava updatedAt, registra evento, retorna {ok, changes, before, after}."""
    mission_id = str(args.get("missionId") or "").strip()

    # Validação do missionId ANTES de acessar o ledger
    if e := mc.validate_mission_id(mission_id):
        return {"ok": False, "error": "INVALID_MISSION_ID", "detail": e}

    state_dir = args.get("state_dir", mc.STATE_DIR)

    # Carrega o ledger existente
    ledger_path = Path(state_dir) / f"{mission_id}.json"
    try:
        with open(ledger_path, encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, ValueError):
        return {"ok": False, "error": "LEDGER_NOT_FOUND", "detail": f"ledger não encontrado para {mission_id} em {state_dir}"}

    if not isinstance(ledger, dict):
        return {"ok": False, "error": "INVALID_LEDGER", "detail": "ledger não é um objeto JSON"}

    if not ledger.get("missionId"):
        return {"ok": False, "error": "INVALID_LEDGER", "detail": "campo missionId ausente no ledger"}

    if ledger["missionId"] != mission_id:
        return {"ok": False, "error": "MISMATCHED_MISSION_ID", "detail": "missionId no ledger não confere"}

    # Guarda estado anterior
    before = dict(ledger)
    changes = {}

    # Atualiza apenas os campos presentes na requisição
    updates = {k: v for k, v in args.items() if k in ("status", "paneId", "tabId") and v is not None}
    allowed_statuses = {"cancelled", "closed", "delivered", "dispatched", "failed", "interrupted", "recover", "working"}

    for field, value in updates.items():
        if field == "status":
            if value not in allowed_statuses:
                return {
                    "ok": False,
                    "error": "INVALID_STATUS",
                    "detail": "status 'FOO' inválido. Permitidos: cancelled, closed, delivered, dispatched, failed, interrupted, recover, working"
                }
            if ledger.get("status") == value:
                continue  # já tem esse status
        ledger[field] = value
        changes[field] = value

    # Se nenhum campo foi alterado
    if not changes:
        return {"ok": True, "message": "nada a corrigir", "before": before}

    # Atualiza timestamp e salva
    ledger["updatedAt"] = mc._now()
    mc.save_ledger(ledger)

    # Registra evento
    mc.append_event(mission_id, None, "ledger_fix", detail=str(changes))

    return {
        "ok": True,
        "changes": changes,
        "before": before,
        "after": ledger
    }


def _ms(fn: str, *a: Any) -> Any:
    if ms is None:
        return ("componente presente mas o import falhou"
                if fn == "on_dispatch" and os.path.isfile(_MS_HOOK) else None)
    try:
        return getattr(ms, fn)(*a)
    except Exception as exc:
        return f"hook mission-supervisor falhou: {str(exc)[:160]}" if fn == "on_dispatch" else None

_ctx: Any = None

_READ_SOURCES = {"visible", "recent", "recent-unwrapped", "detection"}


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _err(code: str, detail: str = "") -> str:
    return _j({"ok": False, "error": code, "detail": detail[:400]})


# ---------------------------------------------------------------- handlers

# GPU-ORCHESTRATOR-01 — engine=gpu: gpu-up antes do pane (fail-open), claude apontado
# na ponte Qwen (8102), gpu-down no mission_close (garfo anti-thrash vive no gpu-down.sh).
_GPU_ORCH = "/opt/gpu-orchestrator"


def _engine_flag(args: Dict[str, Any]) -> str:
    e = str(args.get("engine") or "").strip().lower()
    if e in ("gpu", "engine:gpu"):
        return "gpu"
    if e in ("openrouter", "engine:openrouter"):
        return "openrouter"
    return ""


def _gpu_down_detail(proc: Any) -> "tuple[str, str]":
    """GPU-DOWN-FIX-01: veredito = última linha do STDOUT do gpu-down.sh; stderr vai
    separado. Antes stdout+stderr eram concatenados e a última linha virava o
    traceback (TypeError) — mascarava o veredito real (ex. exit 4 AINDA VIVA)."""
    if proc is None:
        return "", ""
    def _last(b: Any, n: int) -> str:
        t = (b or b"")[-n:].decode("utf-8", "replace").strip()
        return t.splitlines()[-1] if t else ""
    return _last(proc.stdout, 600), _last(proc.stderr, 200)


def _spool_gpu_event(kind: str, mission_id: str, detail: str) -> Optional[str]:
    """Evento de GPU no bus (/opt/mission-events/spool.jsonl). Erro nunca derruba o fluxo."""
    try:
        # DISPATCH-FAST-03: mesmo bus do _MISSION_SPOOL (resolvido na chamada — testes redirecionam p/ tmp)
        os.makedirs(os.path.dirname(_MISSION_SPOOL), exist_ok=True)
        with open(_MISSION_SPOOL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": mc._now(), "event": "finding", "kind": kind,
                                "mission_id": mission_id, "detail": str(detail)[:400],
                                "source": "mission-ops:gpu"}, ensure_ascii=False) + "\n")
        return None
    except Exception as e:
        return str(e)


def _spool_ops_event(kind: str, mission_id: str, detail: str) -> Optional[str]:
    """MISSION-OPS-GUARD-01 F3: evento operacional do mission_core (nudge_input_garbage)
    no bus. Resolve _MISSION_SPOOL na chamada (testes redirecionam). Nunca levanta."""
    try:
        os.makedirs(os.path.dirname(_MISSION_SPOOL), exist_ok=True)
        with open(_MISSION_SPOOL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": mc._now(), "event": "finding", "kind": kind,
                                "mission_id": mission_id, "detail": str(detail)[:400],
                                "source": "mission-ops:guard"}, ensure_ascii=False) + "\n")
        return None
    except Exception as e:
        return str(e)


mc.SPOOL_HOOK = _spool_ops_event


def _findings_registry() -> str:
    """FINDINGS-01: registry dos findings segue o bus DO PROCESSO (env >
    diretório do _MISSION_SPOOL). TempState/suítes redirecionam _MISSION_SPOOL
    → o close/hook NUNCA toca o registry de produção (lição SELFTEST-LEAK-01)."""
    return (os.environ.get("MISSION_FINDINGS_REGISTRY")
            or os.path.join(os.path.dirname(_MISSION_SPOOL), "findings.jsonl"))


def _qwen_bridge_alive(timeout: float = 2.0) -> bool:
    """DISPATCH-FAST-03: sonda E2E da ponte Qwen. /health da 8102 sozinho MENTE na era
    sem-GPU (proxy node vivo + túnel ssh escutando responde ok:true com o vast morto) —
    então exige também o upstream declarado no /health responder /v1/models 200.
    Qualquer falha/timeout = morta (fail-fast). Nunca levanta."""
    import urllib.request as _ur
    try:
        with _ur.urlopen("http://127.0.0.1:8102/health", timeout=timeout) as r:
            if r.status != 200:
                return False
            upstream = str(json.loads(r.read() or b"{}").get("upstream") or "").rstrip("/")
        if not upstream:
            return False
        with _ur.urlopen(upstream + "/v1/models", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _gpu_up_for_mission(mission_id: str) -> bool:
    """gpu-up ANTES do pane. Fail-open por design: falha = evento no bus e missão
    segue no caminho claude caro (NUNCA perder missão por GPU)."""
    try:
        proc = subprocess.run(["bash", os.path.join(_GPU_ORCH, "gpu-up.sh")],
                              capture_output=True, timeout=720)
        out = ((proc.stdout or b"")[-900:] + (proc.stderr or b"")[-300:]).decode("utf-8", "replace")
        if proc.returncode == 0:
            last = out.strip().splitlines()[-1] if out.strip() else "ok"
            _spool_gpu_event("gpu_up", mission_id, last)
            return True
        _spool_gpu_event("gpu_up_failed", mission_id,
                         "exit %s: %s" % (proc.returncode, out[-300:]))
        return False
    except Exception as e:
        _spool_gpu_event("gpu_up_failed", mission_id, str(e)[:300])
        return False


# CHAIN-DISPATCH-GOV-01: trilha de TODO despacho (aceito ou recusado por cadeia) no bus.
_MISSION_SPOOL = "/opt/mission-events/spool.jsonl"


def _spool_chain_event(mission_id: str, gate: Dict[str, Any]) -> Optional[str]:
    """Evento chain_dispatch no bus com spawned_by, profundidade e veredito. Nunca levanta."""
    try:
        os.makedirs(os.path.dirname(_MISSION_SPOOL), exist_ok=True)
        entry = {"ts": mc._now(), "event": "finding", "kind": "chain_dispatch",
                 "mission_id": mission_id, "spawned_by": gate["spawned_by"],
                 "chain_depth": gate["chain_depth"], "chain_depth_max": gate["chain_depth_max"],
                 "verdict": gate["verdict"], "reason": gate["reason"],
                 "dispatcher_kind": gate["kind"], "basis": gate["basis"],
                 "chain_basis": gate.get("chain_basis") or "auto",
                 "declared": gate["declared"], "detail": str(gate["detail"])[:400],
                 "source": "mission-ops:chain"}
        with open(_MISSION_SPOOL, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return None
    except Exception as e:
        return str(e)


# ready-loop do dispatch: ponte Qwen (gpu-up ok) pode demorar a responder o 1º turno;
# qualquer outro caminho (8103/claude direto) sobe rápido — MISSION-BATCH-01.
_READY_DEADLINE_S = 180.0
_READY_DEADLINE_FAST_S = 45.0
# RD-PERF-VERIFY-01: atrasos do ready-dance configuráveis por env (mesmo padrão do
# MISSION_OPS_SESSION_WAIT_S em mission_core) — produção mantém 0.3/2.0; a suíte zera
# para provar o wiring sem dormir ~23s por despacho (TestReadyDance era 25s de 33s).
_DANCE_KEY_DELAY_S = float(os.environ.get("MISSION_OPS_DANCE_KEY_DELAY_S") or 0.3)
_DANCE_REDRAW_S = float(os.environ.get("MISSION_OPS_DANCE_REDRAW_S") or 2.0)


# ── RD-LOOP-01 (05/10): guarda-contra de loop e de realidade no despacho ─────
# Incidente de 05/10: loop de redispatch (172 promoções / 3 missões ativas) por
# verify.json compartilhado por cwd + despacho sem preflight. Gates determinísticos
# (zero LLM) ANTES de qualquer mutação; falha → NÃO despacha e marca gate-operator
# com motivo tipado (spool orch_gate_operator + evento dispatch_gate_operator).
# Liberação: só ordem do operator — payload com operatorOrder não vazio pula os
# gates de redispatch (dedupe/cap), mecanismo já suportado pelos intents da fila.
RD_LOOP_DEDUPE_WINDOW_S = 12 * 3600     # item 2b: dedupe de 12h
RD_LOOP_CAP_WINDOW_S = 24 * 3600        # item 3: janela do cap
RD_LOOP_CAP_MAX = 2                     # item 3: máx 2 tentativas por missão em 24h
# Sinais de promoção (events.jsonl do state dir):
#   chain_dispatch_accepted — 1 por TENTATIVA de despacho pós-gate de cadeia (cap conta
#     tentativas, inclusive as que caem em no_op: o loop de 05/10 era exatamente o
#     re-despacho de missão ativa retornando no_op como sucesso);
#   pane_created/prompt_sent — promoção REAL (novo pane/prompt entregue; dedupe 12h).
_RD_LOOP_PROMO_EVENTS = ("pane_created", "prompt_sent")


def _events_history(mission_id: str, window_s: int, events: Tuple[str, ...]) -> List[float]:
    """Timestamps (epoch) dos eventos da missão na janela, lidos do events.jsonl do
    state dir. Read-only; arquivo ausente = histórico vazio."""
    out: List[float] = []
    cutoff = time.time() - window_s
    try:
        path = str(Path(str(mc.STATE_DIR)) / "events.jsonl")
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if not isinstance(e, dict) or e.get("missionId") != mission_id:
                    continue
                if e.get("event") not in events:
                    continue
                try:
                    ts = datetime.datetime.strptime(
                        str(e.get("ts")), "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=datetime.timezone.utc).timestamp()
                except Exception:
                    continue
                if ts >= cutoff:
                    out.append(ts)
    except OSError:
        pass
    return sorted(out)


def _verify_cwd_conflict(mission_id: str, cwd: str) -> Optional[str]:
    """RD-LOOP-01 item 2a: verify.json solto no cwd alvo com dono de missão ATIVA
    diferente = conflito de verify/cwd NÃO resolvido (o resolvedor do verify já ignora
    cwds, mas o estado sujo só o operator resolve). None = sem conflito."""
    if not cwd:
        return None
    vf = os.path.join(cwd, "verify.json")
    if not os.path.isfile(vf):
        return None
    try:
        with open(vf, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None  # corrompido não é conflito de dono (o resolvedor o ignora)
    owner = str(data.get("mission") or "").strip() if isinstance(data, dict) else ""
    if not owner or owner == mission_id:
        return None
    other = mc.load_ledger(owner)
    if other and other.get("status") in mc.ACTIVE_STATUSES:
        return ("verify.json no cwd %s pertence à missão ATIVA %s (status %s) — "
                "conflito de verify/cwd não resolvido" % (cwd, owner, other.get("status")))
    return None


def _gate_mark(mission_id: str, gate: Tuple[str, str]) -> None:
    """RD-LOOP-01: marca gate-operator com motivo tipado (spool orch_gate_operator +
    evento dispatch_gate_operator no ledger). Nunca levanta."""
    _spool_ops_event("orch_gate_operator", mission_id, "%s: %s" % gate)
    try:
        mc.append_event(mission_id, None, "dispatch_gate_operator",
                        detail="%s: %s" % gate)
    except Exception:
        pass


def _dispatch_preflight(mission_id: str, cwd: str) -> Optional[Tuple[str, str]]:
    """RD-LOOP-01 item 2 (a+c): preflight de realidade ANTES do gate de cadeia.
    (a) conflito de verify/cwd — verify.json solto no cwd alvo com dono de missão
        ATIVA diferente não é "resolvido" (o resolvedor do verify já ignora cwds,
        mas o estado sujo só o operator resolve);
    (c) cwd existe e é gravável pelo worker (W_OK + fs não-RO via statvfs — classe
        do EROFS de bind em produção).
    Falha → NÃO despacha: recusa tipada + gate-operator marcado."""
    gate: Optional[Tuple[str, str]] = None
    confl = _verify_cwd_conflict(mission_id, cwd or "")
    if confl:
        gate = ("VERIFY_CWD_CONFLICT", confl)
    if gate is None:
        if not os.path.isdir(cwd or ""):
            gate = ("CWD_NOT_WRITABLE", "cwd não existe: %s" % cwd)
        elif not os.access(cwd, os.W_OK):
            gate = ("CWD_NOT_WRITABLE", "cwd sem permissão de escrita: %s" % cwd)
        else:
            try:
                if os.statvfs(cwd).f_flag & 0x1:  # ST_RDONLY — classe EROFS de bind
                    gate = ("CWD_NOT_WRITABLE",
                            "filesystem read-only no cwd (classe EROFS de bind): %s" % cwd)
            except OSError:
                pass  # statvfs indisponível: fail-open, demais gates decidem
    if gate:
        _gate_mark(mission_id, gate)
    return gate


def _redispatch_gate(mission_id: str, promos12: List[float],
                     operator_release: bool = False) -> Optional[Tuple[str, str]]:
    """RD-LOOP-01 item 2b: dedupe do REDISPACHO (novo ledger — caminhos no_op e
    prompt_retry do pane vivo ficam acima, ilesos). `promos12` é o snapshot das
    promoções reais (pane_created/prompt_sent) das últimas 12h, tomado ANTES de
    qualquer append desta chamada. Missão promovida nas últimas 12h → gate; só
    ordem do operator libera (payload com operatorOrder não vazio)."""
    if operator_release:
        return None
    if promos12:
        gate = ("DISPATCH_DEDUPE_12H",
                "missão promovida há %.1fh (< 12h) — redispatch exige ordem do operator"
                % ((time.time() - max(promos12)) / 3600.0))
        _gate_mark(mission_id, gate)
        return gate
    return None


# ---------------------------------------------------------------- RD-DISO-01: isolamento estrutural

WORKTREE_ROOT_DEFAULT = "/opt/mission-worktrees"

# fix 5b: deadline da confirmação de pane (pane list pós-criação) antes de qualquer
# ledger. Suíte legada zera (herdr mock sem pane list) — produção 8.0s.
_PANE_CONFIRM_S = 8.0

_ISO_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _iso_to_epoch(raw: str) -> Optional[float]:
    """Epoch de timestamp ISO do ledger (mc._now). None se vazio/inválido."""
    try:
        return calendar.timegm(time.strptime(raw, _ISO_TS_FMT))
    except (ValueError, TypeError):
        return None


def _git_out(cwd: str, *args: str, timeout_s: float = 20.0,
             env: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """git no cwd dado (read-only por default; rebase/merge passam env de
    identidade). (ok, stdout|stderr-tail). Nunca levanta."""
    try:
        proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                              text=True, timeout=timeout_s, check=False, env=env)
    except Exception as e:
        return False, str(e)[:200]
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, ((proc.stderr or proc.stdout or "").strip()[:300] or
                       ("exit %s" % proc.returncode))
    return True, out


def _component_of(args: Dict[str, Any], prompt_file: str) -> str:
    """Componente da missão: flag do dispatch > frontmatter `component:` do
    contrato > linha `**Componente:**` > rd.mission_component (regex do roadmap).
    Vazio = sem componente (sem lease, grupo _default do scheduler)."""
    comp = str(args.get("component") or "").strip()
    if comp:
        return comp
    try:
        with open(prompt_file, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        raw = ""
    m = re.search(r"^component:\s*(\S.*)$", raw, re.MULTILINE)
    if m:
        return m.group(1).strip().strip("\"'")[:120]
    m = re.search(r"\*\*Componente:\*\*\s*(\S.*)$", raw, re.MULTILINE)
    if m:
        return m.group(1).strip()[:120]
    try:
        comp = rd.mission_component(str(prompt_file))
    except Exception:
        comp = None
    return str(comp or "").strip()[:120]


def _lease_dispatch_gate(mission_id: str, component: str) -> Optional[Tuple[str, str]]:
    """RD-DISO-01 item 2: gate do lease — despacho com componente em lease ativo
    de OUTRA missão = recusa tipada COMPONENT_LEASED (fila reenfileira sozinha).
    Acquire idempotente da própria missão renova o heartbeat. None = prossegue."""
    if not component:
        return None
    ok, code, detail = leases.acquire(mission_id, component)
    if ok:
        return None
    return (code, detail)


def _release_dispatch_lease(mission_id: str, component: str) -> None:
    """Libera o lease num caminho de falha do despacho (pane nunca existiu —
    a missão não vai trabalhar). Fail-open."""
    if not component:
        return
    try:
        leases.release(mission_id, component)
    except Exception:
        pass


def _wt_requested(args: Dict[str, Any]) -> bool:
    """worktree obrigatório? Flag do dispatch: required/true/1/yes = ON.
    Default OFF no plugin — o consumer pede 'required' por contrato (toda
    missão da fila roda em worktree próprio)."""
    return str(args.get("worktree") or "").strip().lower() in ("required", "true", "1", "yes")


def _dispatch_worktree(mission_id: str, cwd: str) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
    """RD-DISO-01 item 1: worktree PRÓPRIO por missão. Retorna
    (cwd_efetivo, wt_info|None, not_applicable|None).
    - cwd já dentro de um linked worktree → (cwd, None, 'já isolado em worktree')
    - cwd repo no checkout principal → cria <WORKTREE_ROOT>/<missionId>, branch
      mission/<missionId>, base = branch default (main/master) → main intocada.
    - cwd não é repo → (cwd, None, 'não é repo git — isolation não se aplica').
    Falha de criação levanta _DispatchWtError (caller recusa tipado e reenfileira)."""
    ok, inside = _git_out(cwd, "rev-parse", "--is-inside-work-tree")
    if not ok or inside != "true":
        return cwd, None, "não é repo git — isolation não se aplica"
    ok, common = _git_out(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ok2, gd = _git_out(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    if ok and ok2 and common and gd and os.path.normpath(common) != os.path.normpath(gd):
        return cwd, None, "cwd já roda em linked worktree — isolation pré-existente"
    ok, root = _git_out(cwd, "rev-parse", "--show-toplevel")
    if not ok:
        return cwd, None, "não é repo git — isolation não se aplica"
    ok, mainb = _git_out(root, "rev-parse", "--verify", "--quiet", "main")
    main_branch = "main" if ok else ("master" if _git_out(root, "rev-parse", "--verify", "--quiet", "master")[0] else "")
    if not main_branch:
        raise _DispatchWtError("repo sem branch main/master: %s" % root)
    wt_path = os.path.join(WORKTREE_ROOT_DEFAULT, mission_id)
    branch = "mission/%s" % mission_id
    info, werr = mc.worktree_create(branch=branch, path=wt_path, base=main_branch,
                                    label="mission:%s" % mission_id, cwd=root)
    if werr or not info or not info.get("path"):
        raise _DispatchWtError("herdr worktree create: %s" % (werr or "sem path"))
    return str(info["path"]), {"path": info["path"],
                               "branch": info.get("branch") or branch,
                               "workspaceId": info.get("workspace_id") or info.get("open_workspace_id"),
                               "mainBranch": main_branch, "baseRoot": root}, None


class _DispatchWtError(Exception):
    """Falha de criação de worktree obrigatório — recusa tipada, sem ledger."""


def _pane_confirmed(pane_id: str, deadline_s: Optional[float] = None) -> Tuple[bool, str]:
    """RD-DISO-01 fix 5b: pane existe DE VERDADE (pane list pós-criação) antes de
    qualquer ledger. (True, '') confirmado; (False, detail) = recusa tipada.
    Unknown (herdr indisponível) → 1 retry, depois recusa honesta.
    _PANE_CONFIRM_S <= 0 (suíte legada com herdr mock sem pane list) = costura de
    compat: confia no pane_id do payload do tab create (comportamento pré-DISO)."""
    if deadline_s is None:
        deadline_s = _PANE_CONFIRM_S
    if deadline_s <= 0:
        return True, "confirmação desligada (_PANE_CONFIRM_S<=0, suíte legada)"
    deadline = time.time() + deadline_s
    unknown_seen = False
    while time.time() < deadline:
        pex = mc.pane_exists(pane_id)
        if pex is True:
            return True, ""
        if pex is None:
            if unknown_seen:
                return False, "pane list indisponível (herdr) — pane não confirmado"
            unknown_seen = True
        time.sleep(0.2)
    return False, "pane não apareceu no pane list em %.0fs" % deadline_s


# ---------------------------------------------------------------- WORKER-HEADLESS-01
# Workers nascem headless (claude -p stream-json, stdin=promptFile): sem pane, sem
# ready-wait — as classes de falha do TUI (diálogos de permissão, CLAUDE_START_TIMEOUT,
# pane perdido/garbage keystrokes, classifier auto-mode) ficam impossíveis por desenho.
# TUI = fallback de emergência (dispatch.tui=true). Fonte única do env/argv: mc.

def start_headless_tailer(mission_id: str, log_path: str, pid: int) -> Optional[str]:
    """Tailer DETACHED do log headless → bus spool + awaitingClose no fim. Erro é
    não-fatal (o log continua em disco). Seam de teste (PKG.start_headless_tailer)."""
    return mc.headless_tailer_spawn(mission_id, log_path, pid,
                                    spool=str(_MISSION_SPOOL))


def _headless_do_spawn(mission_id: str, cwd: str, prompt_file: str, log_path: str,
                       env: Dict[str, str], argv: List[str]) -> Tuple[Any, Optional[str]]:
    """Spawn do worker + tailer. Seam de teste (PKG._headless_do_spawn).
    O worker vai em scope systemd próprio (headless_worker_scope_cmd) quando o
    despacho roda dentro do scope efêmero do consumer — sem isso o KillMode do
    scope mataria o claude -p no fim do despacho."""
    spawn_argv = (mc.headless_worker_scope_cmd(mission_id, prompt_file, log_path, argv,
                                               env=env)
                  or mc.worker_spawn_argv(argv))
    if spawn_argv is None:  # WORKER-NOROOT-01: nunca spawn root com bypassPermissions
        return None, (mc.worker_spawn_preflight()
                      or "spawn não-root indisponível (sem systemd-run e sem setpriv)")
    proc, serr = mc.headless_spawn(cwd, prompt_file, log_path, env, spawn_argv)
    if serr or proc is None:
        return None, serr
    terr = start_headless_tailer(mission_id, str(log_path), proc.pid)
    if terr:
        mc.append_event(mission_id, None, "headless_tailer_failed", detail=str(terr)[:200])
    return proc, None


def _pid_alive(pid: Any) -> bool:
    """Processo vivo? (/proc — zumbi conta como morto; o log já não cresce)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        return stat.rsplit(")", 1)[-1].split()[0] != "Z"
    except (OSError, IndexError, ValueError):
        return False


def _headless_base_url(gpu_up_ok: bool, engine_flag: str, p8102_alive: bool) -> Optional[str]:
    """Base URL do spawn headless — espelho exato das 3 variantes do caminho TUI."""
    if gpu_up_ok:
        return "http://127.0.0.1:8102"
    if engine_flag == "openrouter" or (gpu_up_ok is False and p8102_alive is False):
        return "http://127.0.0.1:8103"
    return None


def _dispatch_headless(mission_id: str, pf: str, cwd: str, ledger: Dict[str, Any],
                       gpu_up_ok: bool, engine_flag: str, p8102_alive: bool,
                       obey_warnings: List[Any], component: Optional[str],
                       wt_info: Optional[Dict[str, Any]]) -> str:
    """Caminho headless do dispatch: sem tab/pane, sem ready-dance, sem
    CLAUDE_START_TIMEOUT (não há sinal de ready a esperar — o prompt já é ingestão
    do contrato via stdin no spawn). Paridade de governança com o TUI: worktree/
    lease/engine resolvidos a montante; supervisor nasce junto (fail-closed);
    golden config copiada (trust + allowlist + pin de modelo); tailer detached
    streama o log no bus e marca awaitingClose no fim honesto da execução."""
    _gerr = mc.golden_config_copy(cwd)
    if _gerr:  # fail-open: sem golden, trust/allowlist degradam (mesmo contrato do TUI)
        mc.append_event(mission_id, None, "headless_golden_config_degraded",
                        detail=str(_gerr)[:200])
    log_path = mc.headless_log_path(mission_id)
    ledger["creation"] = "headless"
    ledger["headless"] = True
    ledger["headlessLog"] = str(log_path)
    ledger["status"] = "dispatching"
    mc.save_ledger(ledger)  # paridade fix 5b: persiste antes de qualquer launch
    if e_ms := _ms("on_dispatch", ledger, mc):
        return _err("SUPERVISOR_SPAWN_FAILED", e_ms)
    env = mc.headless_env(cwd, _headless_base_url(gpu_up_ok, engine_flag, p8102_alive))
    argv = mc.headless_argv()
    _t_spawn = time.time()
    proc, serr = _headless_do_spawn(mission_id, cwd, str(pf), str(log_path), env, argv)
    if serr or proc is None:
        _release_dispatch_lease(mission_id, component)
        if wt_info and wt_info.get("workspaceId"):
            mc.worktree_remove(workspace=str(wt_info["workspaceId"]))
        mc.append_event(mission_id, None, "headless_spawn_failed", detail=str(serr or "")[:200])
        return _err("HEADLESS_SPAWN_FAILED", f"claude -p spawn: {serr}")
    lat.timed("headless_spawn_ms", mission_id, _t_spawn,
              fallback=env.get("ANTHROPIC_BASE_URL") is None, detail="pid=%s" % proc.pid)
    mc.append_event(mission_id, None, "headless_launched",
                    detail=f"pid={proc.pid} engine={ledger.get('engine')} "
                           f"argv={' '.join(argv)} log={log_path}")
    mc.append_event(mission_id, None, "prompt_sent", detail=f"{pf} (stdin no spawn headless)")
    ledger["headlessPid"] = proc.pid
    ledger["resumeSessionId"] = mc.own_session_id(mission_id, cwd, since=_t_spawn,
                                                  wait_s=mc.SESSION_WAIT_S)
    ledger["status"] = "dispatched"
    ledger["dispatchedAt"] = mc._now()
    ledger["updatedAt"] = mc._now()
    mc.save_ledger(ledger)
    return _j({"ok": True, "status": "dispatched", "missionId": mission_id,
               "mode": "headless", "headless": True, "pid": proc.pid,
               "creation": "headless", "headlessLog": str(log_path),
               "cwd": cwd, "promptFile": ledger["promptFile"],
               "resumeSessionId": ledger["resumeSessionId"],
               "spawned_by": ledger["spawned_by"], "chain_depth": ledger["chain_depth"],
               "obeyWarnings": obey_warnings,
               "note": "worker headless (claude -p stream-json): sem pane, sem ready-wait "
                       "— CLAUDE_START_TIMEOUT não se aplica; saída em " + str(log_path)})


def handle_mission_dispatch(args: Dict[str, Any], **_kw) -> str:
    # GB-PLUGIN-ROTA-02: despacho pelo plugin segue a ROTA CORRETA (mecanico).
    _mec = (args or {}).get("mec_prova") or (args or {}).get("payload", {}).get("mec_prova")
    _wt = (args or {}).get("worktree") or (args or {}).get("payload", {}).get("worktree") or "/home/worker/harness-s2"
    _tit = (args or {}).get("missao") or (args or {}).get("payload", {}).get("missao") or (args or {}).get("mission_id") or "missao-via-plugin"
    if not _mec:
        return json.dumps({"ok": False, "erro": "USE_ROTA_CORRETA",
                           "como": "despachar-mecanico.sh <wt> '<missao>' MEC_PROVA=<cura> (com cura) ou despachante DAG (plano.json)",
                           "por_que": "despacho de cura via mecanico; missao de trabalho via despachante DAG"})
    import subprocess as _sp
    _r = _sp.run(["bash", "/home/worker/harness-s2/scripts/despachar-mecanico.sh", _wt, _tit, "MEC_PROVA=%s" % _mec],
                 capture_output=True, text=True, timeout=900)
    return json.dumps({"ok": _r.returncode == 0, "route": "despachar-mecanico", "rc": _r.returncode,
                       "saida": (_r.stdout or "")[-400:]})
    # (corpo original preservado abaixo, inacessível pelo return acima)
    mission_id = str(args.get("missionId") or "").strip()
    mc.set_mission_sender(mission_id)  # SENDER-ID-01: pane-writes carregam a identidade da missão
    prompt_file = str(args.get("promptFile") or "").strip()
    pane_title = str(args.get("paneTitle") or "").strip() or None
    direction = str(args.get("direction") or "right")
    cwd = str(args.get("cwd") or "").strip() or os.path.dirname(prompt_file) or os.getcwd()
    _t_dispatch = time.time()  # RD-DISO-01 item 8: base do dispatch_pane_ms

    if e := mc.validate_mission_id(mission_id):
        return _err("INVALID_MISSION_ID", e)
    pf, e = mc.validate_prompt_file(prompt_file)
    if e:
        return _err("INVALID_PROMPT_FILE", e)
    if not os.path.isdir(cwd):
        return _err("INVALID_CWD", f"cwd não existe: {cwd}")

    # ---- RD-LOOP-01: preflight de realidade (a: conflito verify/cwd; c: cwd gravável)
    # + snapshot dos históricos ANTES de qualquer append desta chamada (dedupe/cap não
    # se auto-envenenam com a tentativa corrente).
    _op_release = bool(str(args.get("operatorOrder") or "").strip())
    if _gate := _dispatch_preflight(mission_id, cwd):
        return _err(_gate[0], _gate[1])
    _hist24 = _events_history(mission_id, RD_LOOP_CAP_WINDOW_S, ("chain_dispatch_accepted",))
    # item 3 (cap): máx 2 tentativas/24h vale para TODO despacho — inclusive o caminho
    # no_op, que era exatamente o loop vivo de 05/10 (re-despacho de missão ativa).
    if not _op_release and len(_hist24) >= RD_LOOP_CAP_MAX:
        _cap = ("DISPATCH_CAP_EXCEEDED",
                "máx %d tentativas/24h atingido (%d na janela) — só ordem do operator libera"
                % (RD_LOOP_CAP_MAX, len(_hist24)))
        _gate_mark(mission_id, _cap)
        return _err(_cap[0], _cap[1])
    _promos12 = _events_history(mission_id, RD_LOOP_DEDUPE_WINDOW_S, _RD_LOOP_PROMO_EVENTS)

    # ---- CHAIN-DISPATCH-GOV-01: gate tier-1 ANTES de qualquer herdr/ledger. Emissor pelo
    # pane do chamador (worker não se passa por supervisor) > spawnedBy declarado > gateway.
    # ORCH-CHAIN-CWD-01: chainBasis="payload" (despacho do consume) → pai da cadeia vem
    # EXCLUSIVAMENTE do payload.spawnedBy do intent; ambiente (pane) nunca decide.
    gate = mc.chain_gate(mission_id, args.get("spawnedBy"), os.environ.get("HERDR_PANE_ID"),
                         chain_basis=str(args.get("chainBasis") or "auto"))
    _spool_chain_event(mission_id, gate)
    mc.append_event(mission_id, None, "chain_dispatch_" + gate["verdict"],
                    detail=f"spawned_by={gate['spawned_by']} depth={gate['chain_depth']}"
                           f"/{gate['chain_depth_max']} {gate['reason'] or ''}".strip())
    if gate["verdict"] != "accepted":
        return _err(gate["reason"], gate["detail"])

    # ---- RD-OBEY-02 (gate de aplicação no dispatch): despacho da fila fora do
    # orquestrador = violação O3 — warning tipado `violates-obligation-O3` na
    # resposta (fail-open: nunca bloqueia, SEMPRE marca) + finding no bus +
    # dívida automática `obedience` P1 na fila. mission_batch herda (chama dispatch).
    try:
        _obey_dispatch = obr.gate_dispatch(
            mission_id, spool_path=_MISSION_SPOOL,
            obedience_path=os.path.join(str(mc.STATE_DIR), "obedience.jsonl"))
    except Exception:
        _obey_dispatch = []  # gate de obediência nunca derruba o despacho

    existing = mc.load_ledger(mission_id)
    if existing and existing.get("status") == "prompt_failed" and existing.get("paneId"):
        # pane vivo, prompt não entregue — re-tenta a entrega NO MESMO pane (não cria nova aba)
        pane_id = str(existing["paneId"])
        mc.append_event(mission_id, pane_id, "dispatch_prompt_retry", detail="re-delivering prompt")
        ok, derr = mc.deliver_prompt(pane_id, mc.dispatch_prompt(existing.get('promptFile'), mission_id))
        existing["updatedAt"] = mc._now()
        if ok:
            existing["status"] = "dispatched"
            mc.save_ledger(existing)
            mc.append_event(mission_id, pane_id, "prompt_sent", detail="prompt re-delivered on retry")
            return _j({"ok": True, "status": "dispatched", "missionId": mission_id,
                       "paneId": pane_id, "tabId": existing.get("tabId"),
                       "creation": existing.get("creation"), "retriedPrompt": True,
                       "promptFile": existing.get("promptFile"),
                       "obeyWarnings": _obey_dispatch,
                       "note": "supervisione com mission_watch; verificação é do supervisor"})
        existing["status"] = "prompt_failed"
        mc.save_ledger(existing)
        mc.append_event(mission_id, pane_id, "prompt_failed", detail=derr or "")
        return _err("PROMPT_DELIVERY_FAILED", derr or "retry também falhou")
    # 25/09 (prova d): delivered/closed também são NO_OP — sem isso o re-dispatch do
    # MESMO id criava uma aba duplicada com rótulo igual (provado ao vivo em w3:tM).
    # 26/09 fix (gap real ao vivo na GWS-SOVEREIGN-01): no_op para delivered/closed
    # SÓ quando o pane do ledger ainda existe no herdr; pane morto = redispatch legítimo
    # (aba/pane perdidos em realocação de telas não podem enterrar a missão pra sempre).
    _existing_status = existing.get("status") if existing else None
    _pane_still_alive = False
    if existing and _existing_status in {"delivered", "closed"}:
        _old_pane = existing.get("paneId")
        if _old_pane:
            try:
                _pe = mc.pane_exists(_old_pane)
                _pane_still_alive = bool(_pe)
            except Exception:
                _pane_still_alive = False  # herdr indisponível: no fail-safe bloqueante, segue redispatch
    if existing and (_existing_status in mc.ACTIVE_STATUSES
                     or (_existing_status in {"delivered", "closed"} and _pane_still_alive)
                     or (existing.get("headless") and _existing_status in {"delivered", "closed"})):
        mc.append_event(mission_id, existing.get("paneId"), "dispatch_no_op",
                        detail="active mission already dispatched")
        return _j({"ok": True, "status": "no_op",
                   "reason": "active mission already dispatched",
                   "missionId": mission_id, "paneId": existing.get("paneId"),
                   "tabId": existing.get("tabId"), "cwd": existing.get("cwd"),
                   "promptFile": existing.get("promptFile"),
                   "resumeSessionId": existing.get("resumeSessionId"),
                   "obeyWarnings": _obey_dispatch})

    # ---- RD-LOOP-01 item 2b: dedupe 12h no REDISPACHO (novo ledger — caminhos no_op e
    # prompt_retry do pane vivo já passaram acima, ilesos). Falha → NÃO despacha:
    # gate-operator com motivo tipado. Liberação = operatorOrder no payload.
    if _rgate := _redispatch_gate(mission_id, _promos12, operator_release=_op_release):
        return _err(_rgate[0], _rgate[1])

    # ---- RD-DISO-01 item 2: lease de componente. Componente em lease ativo de
    # OUTRA missão → recusa tipada COMPONENT_LEASED (a fila reenfileira sozinha —
    # staggering). Acquire idempotente da própria missão renova o heartbeat.
    _component = _component_of(args, str(pf))
    if _lgate := _lease_dispatch_gate(mission_id, _component):
        return _err(_lgate[0], _lgate[1])

    # ---- WORKER-NOROOT-01: fail-fast antes de worktree/pane/ledger — sem o user de
    # serviço `worker`, o claude nasce morto sob root (o CLI recusa bypassPermissions:
    # "cannot be used with root/sudo privileges for security reasons"). Erro tipado;
    # a ativação é host-side (useradd + chgrp dos cwds — ver relatório da missão).
    if _wpf := mc.worker_spawn_preflight():
        _release_dispatch_lease(mission_id, _component)
        return _err("WORKER_USER_MISSING", _wpf)

    # ---- RD-DISO-01 item 1: worktree PRÓPRIO (quando pedido — `worktree: required`
    # no payload do despacho; o consumer pede por contrato). main intocada: o trabalho
    # roda em /opt/mission-worktrees/<missionId>, branch mission/<missionId>.
    _wt_info: Optional[Dict[str, Any]] = None
    if _wt_requested(args):
        try:
            cwd, _wt_info, _wt_na = _dispatch_worktree(mission_id, cwd)
        except _DispatchWtError as _we:
            _release_dispatch_lease(mission_id, _component)
            _detail = "worktree obrigatório falhou: %s" % _we
            _spool_ops_event("dispatch_worktree_failed", mission_id, _detail)
            mc.append_event(mission_id, None, "dispatch_worktree_failed", detail=_detail[:200])
            return _err("WORKTREE_CREATE_FAILED", _detail)
        if _wt_na:
            mc.append_event(mission_id, None, "worktree_not_applicable", detail=_wt_na[:200])
        else:
            mc.append_event(mission_id, None, "worktree_created",
                            detail="%s (branch %s)" % ((_wt_info or {}).get("path"),
                                                       (_wt_info or {}).get("branch")))

    ledger: Dict[str, Any] = {
        "missionId": mission_id, "paneId": None, "tabId": None, "creation": None,
        "paneTitle": pane_title, "promptFile": str(pf), "cwd": cwd,
        "resumeSessionId": None, "status": "dispatching",
        "createdAt": mc._now(), "updatedAt": mc._now(),
        "spawned_by": gate["spawned_by"], "chain_depth": gate["chain_depth"],
        "allow_chain_dispatch": mc.detect_chain_badge(str(pf)),
    }
    # SUPERVISOR-VERIFY-01: canal real de uso do operator (URL que ele abre / comando que roda).
    # String URL ou dict {url, expect_status}. Ausência = warning no fechamento.
    if args.get("operatorChannel"):
        _oc = args["operatorChannel"]
        ledger["operatorChannel"] = (
            {"url": str(_oc).strip()} if isinstance(_oc, str) else _oc)
    # CLOSE-VERIFY-GUARD-01: escopo de consequência gravado NA ORIGEM (flag do dispatch >
    # `consequence: true|false` no prompt > heurística regex). O close decide por ele.
    _cq = mc.resolve_consequence(args.get("consequence"), str(pf))
    ledger["consequence"] = _cq["consequence"]
    ledger["consequenceSource"] = _cq["source"]
    if _cq["matches"]:
        ledger["consequenceMatches"] = _cq["matches"]
    # RD-DISO-01: componente (lease) + worktree próprios gravados no ledger — fontes
    # do heartbeat no watch e do merge gate no fecho. Ledger SÓ persiste depois do
    # pane existir de verdade (fix 5b — nunca ledger-ghost `dispatching` sem pane).
    if _component:
        ledger["component"] = _component
    if _wt_info:
        ledger["worktreePath"] = _wt_info["path"]
        ledger["worktreeBranch"] = _wt_info["branch"]
        if _wt_info.get("workspaceId"):
            ledger["worktreeWorkspaceId"] = _wt_info["workspaceId"]
        ledger["worktreeMainBranch"] = _wt_info.get("mainBranch")
        ledger["worktreeBaseRoot"] = _wt_info.get("baseRoot")

    # ---- GPU-ORCHESTRATOR-01: engine=gpu → gpu-up ANTES do pane (fail-open)
    # FIX 28/09 ~23:00 (supervisor, ordem do operator "workers=qwen"): ponte Qwen vira
    # DEFAULT — 18 missões no dia rodaram em GLM-5.3-flash pago (OpenRouter) porque o
    # engine=gpu nunca era passado. Agora TODA missão tenta a ponte; escape honesto
    # p/ OpenRouter só se a ponte falhar (gpu_up_failed no bus, visível no ledger).
    # engine=openrouter desliga explicitamente (escape declarado).
    gpu_up_ok = False
    _eflag = _engine_flag(args)
    _p8102_alive = False
    if _eflag == "openrouter":
        # MODELS-ROLES-01 (ordem do operator 28/09): worker via OpenRouter (proxy :8103).
        # FIX 29/09: modelo lido da unit or-worker-bridge (fonte única) — o 20b hardcoded
        # mentia quando o MODEL= da unit mudou para gpt-oss-120b.
        _wm = "openai/gpt-oss-20b"
        try:
            _u = open("/etc/systemd/system/or-worker-bridge.service", encoding="utf-8").read()
            _m = re.search(r"Environment=MODEL=(\S+)", _u)
            if _m:
                _wm = _m.group(1)
        except OSError:
            pass
        ledger["engine"] = "openrouter"
        ledger["worker_model"] = _wm
    else:
        # FIX 29/09 (era sem-GPU): ponte Qwen 8102 morta = caminho morto de 180s
        # (claude nasce apontado nela e o ready nunca vem — "pane morta" da 01b).
        # Fail-FAST: se a 8102 não responde /health em 2s, pula o gpu-up de vez
        # (engine=openrouter-fallback sem tentar criar instância vast).
        _t_gpu = time.time()
        _p8102_alive = _qwen_bridge_alive()
        if _p8102_alive:
            gpu_up_ok = _gpu_up_for_mission(mission_id)
        else:
            gpu_up_ok = False
            _spool_gpu_event("gpu_up_skipped", mission_id,
                             "ponte 8102 morta (era sem-GPU) — fail-fast, sem gpu-up de 720s")
        ledger["engine"] = "gpu" if gpu_up_ok else "openrouter-fallback"
        ledger["gpuUpOk"] = gpu_up_ok
        # RD-DISO-01 item 8: latência da chamada externa (ponte GPU) com fallback contabilizado
        lat.timed("gpu_up_ms", mission_id, _t_gpu, fallback=not gpu_up_ok,
                  detail="engine=%s" % ledger["engine"])

    # ---- WORKER-HEADLESS-01: modo headless é o DEFAULT (ordem do operator: workers
    # nascem headless — fim da classe de falha do TUI). TUI = fallback (dispatch.tui=true).
    if mc.worker_launch_mode(args) == "headless":
        return _dispatch_headless(mission_id, str(pf), cwd, ledger, gpu_up_ok, _eflag,
                                  _p8102_alive, _obey_dispatch, _component, _wt_info)

    # ---- caminho PRIMÁRIO: uma missão = uma aba = um pane (tela cheia)
    tab_id, pane_id, terr = mc.tab_create(cwd=cwd)
    if tab_id:
        ledger["tabId"] = tab_id
        ledger["creation"] = "tab"
        if pane_id:
            ledger["paneId"] = pane_id
        # ---- RD-DISO-01 fix 5b: pane confirmado no pane list ANTES de qualquer ledger.
        # Falha → recusa tipada PANE_CREATE_TIMEOUT (lease liberado, worktree limpo,
        # tab fechada) — NUNCA ledger-ghost `dispatching` sem pane (crash-loop 05/10).
        if pane_id:
            _pane_ok, _pane_why = _pane_confirmed(pane_id)
        else:
            _pane_ok, _pane_why = False, "tab create devolveu tab sem pane_id"
        if not _pane_ok:
            if tab_id:
                mc.tab_close(tab_id)  # sem vazamento de tab fantasma
            if _wt_info and _wt_info.get("workspaceId"):
                mc.worktree_remove(workspace=str(_wt_info["workspaceId"]))
            _release_dispatch_lease(mission_id, _component)
            _detail = "pane não confirmado pós-criação: %s" % _pane_why
            mc.append_event(mission_id, None, "pane_create_timeout", detail=_detail[:200])
            return _err("PANE_CREATE_TIMEOUT", _detail)
        ledger["status"] = "dispatching"
        ledger["createdAt"] = ledger.get("createdAt") or mc._now()
        mc.save_ledger(ledger)  # fix 5b: primeiro save SÓ com pane confirmado
        lat.timed("dispatch_pane_ms", mission_id, _t_dispatch, detail="tab %s" % tab_id)
        mc.append_event(mission_id, pane_id or tab_id, "pane_created",
                        detail=f"tab {tab_id}; cwd {cwd}")
        # MISSION-SUPERVISOR-01: supervisor nasce junto do pane (fail-closed no dispatch) —
        # ledger JÁ persistido (o supervisor espelha o ledger no boot).
        if e_ms := _ms("on_dispatch", ledger, mc):
            return _err("SUPERVISOR_SPAWN_FAILED", e_ms)
        if e2 := mc.tab_rename(tab_id, f"MISSION:{mission_id}"):
            mc.append_event(mission_id, pane_id or tab_id, "tab_rename_failed", detail=e2)
    else:
        # ---- fallback APENAS se o tab create falhar (split da pane de origem)
        source_pane = str(args.get("sourcePaneId") or "").strip() or os.environ.get("HERDR_PANE_ID", "").strip()
        if not source_pane:
            _release_dispatch_lease(mission_id, _component)
            mc.append_event(mission_id, None, "dispatch_worktree_failed",
                            detail="tab create falhou e sem sourcePaneId") if _wt_info else None
            if _wt_info and _wt_info.get("workspaceId"):
                mc.worktree_remove(workspace=str(_wt_info["workspaceId"]))
            return _err("HERDR_TAB_CREATE_FAILED",
                        f"tab create falhou ({terr or 'sem detalhe'}) e sem sourcePaneId para fallback")
        if direction not in ("right", "down"):
            _release_dispatch_lease(mission_id, _component)
            if _wt_info and _wt_info.get("workspaceId"):
                mc.worktree_remove(workspace=str(_wt_info["workspaceId"]))
            return _err("INVALID_DIRECTION", "direction deve ser right ou down")
        pane_id, serr = mc.split_pane(source_pane, cwd=cwd, direction=direction)
        if serr or not pane_id:
            _release_dispatch_lease(mission_id, _component)
            if _wt_info and _wt_info.get("workspaceId"):
                mc.worktree_remove(workspace=str(_wt_info["workspaceId"]))
            return _err("HERDR_PANE_CREATE_FAILED",
                        f"tab create: {terr or 'sem detalhe'}; split fallback: {serr or 'no pane id'}")
        _pane_ok, _pane_why = _pane_confirmed(pane_id)
        if not _pane_ok:
            _release_dispatch_lease(mission_id, _component)
            if _wt_info and _wt_info.get("workspaceId"):
                mc.worktree_remove(workspace=str(_wt_info["workspaceId"]))
            mc.append_event(mission_id, None, "pane_create_timeout", detail=_pane_why[:200])
            return _err("PANE_CREATE_TIMEOUT", _pane_why)
        ledger["status"] = "dispatching"
        ledger["creation"] = "split_fallback"
        ledger["paneId"] = pane_id
        mc.save_ledger(ledger)  # fix 5b: primeiro save SÓ com pane confirmado
        lat.timed("dispatch_pane_ms", mission_id, _t_dispatch, detail="split %s" % source_pane)
        mc.append_event(mission_id, pane_id, "pane_created",
                        detail=f"split fallback de {source_pane}; cwd {cwd}")
        if e_ms := _ms("on_dispatch", ledger, mc):
            return _err("SUPERVISOR_SPAWN_FAILED", e_ms)

    pane_id = str(ledger["paneId"] or "")
    if pane_title:
        if e3 := mc.rename_pane(pane_id, pane_title):
            mc.append_event(mission_id, pane_id, "rename_failed", detail=e3)

    # ---- GPU-ORCHESTRATOR-01: gpu-up OK → claude da missão apontado na ponte Qwen
    # DISPATCH-FAST-02: TODA missão sobe com CLAUDE_CONFIG_DIR apontando para a config
    # dourada copiada em <cwd>/.claude-config (tab_create copiou) — claude NASCE pronto,
    # zero diálogos first-run. Sem gpu-up, o mesmo env mantém o benefício.
    # RD-AUTOMODE-OFF-01: TODO launch de worker leva o env anti-classifier-billing +
    # anti-autoupdater (fonte única mc). WORKER-NOROOT-01: mode = bypassPermissions
    # (não-root via setpriv — o CLI recusa bypass sob root/sudo).
    _wlenv, _wlflag = mc.worker_launch_env(), mc.worker_launch_flag()
    # WORKER-NOROOT-01: TUI também nasce não-root (setpriv, sem sudo/su) — o CLI recusa
    # bypassPermissions sob root. O preflight do dispatch já recusou sem o user; aqui o
    # prefixo é só a materialização (os 3 variantes carregam o mesmo contrato).
    _sp = mc.worker_setpriv_prefix()
    if not _sp:
        return _err("WORKER_USER_MISSING", mc.worker_spawn_preflight()
                    or f"user de serviço '{mc.WORKER_USER}' ausente")
    if gpu_up_ok:
        claude_cmd = (f"{_sp} env ANTHROPIC_BASE_URL=http://127.0.0.1:8102 ANTHROPIC_AUTH_TOKEN=dummy "
                      f"ANTHROPIC_API_KEY=dummy CLAUDE_CONFIG_DIR={cwd}/.claude-config {_wlenv} claude {_wlflag}")
    elif _eflag == "openrouter" or gpu_up_ok is False and _p8102_alive is False:
        # MODELS-ROLES-01: worker no gpt-oss via proxy OpenRouter (or-worker-bridge :8103).
        # FIX 29/09: fallback sem-GPU TAMBÉM vai pro 8103 (antes nascia sem base URL =
        # claude caro direto, sem proxy, sem barreira).
        claude_cmd = (f"{_sp} env ANTHROPIC_BASE_URL=http://127.0.0.1:8103 ANTHROPIC_AUTH_TOKEN=dummy "
                      f"ANTHROPIC_API_KEY=dummy CLAUDE_CONFIG_DIR={cwd}/.claude-config {_wlenv} claude {_wlflag}")
        # CLASSIFIER-OFF REVERTIDO 29/09: --dangerously-skip-permissions é recusado pelo CLI
        # quando roda como ROOT ("cannot be used with root/sudo"). Ataque alternativo:
        # allowlist de permissões (settings.json) + barreira server-side da ponte.
        # RD-AUTOMODE-OFF-01: auto mode do classifier desligado no launch (Opção A).
    else:
        # ROUTE-SEAL-TUI (06/10, ordem operator): TODO spawn TUI nasce na trindade
        # (bridge 8103 + dummy) — o else antigo herdava env vazado (openrouter direto,
        # sem trim/audit). 8103 agora e o default incondicional do worker.
        claude_cmd = (f"{_sp} env ANTHROPIC_BASE_URL=http://127.0.0.1:8103 ANTHROPIC_AUTH_TOKEN=dummy "
                      f"ANTHROPIC_API_KEY=dummy CLAUDE_CONFIG_DIR={cwd}/.claude-config {_wlenv} claude {_wlflag}")
    if e4 := mc.run_command(pane_id, claude_cmd):
        return _err("HERDR_RUN_FAILED", f"claude start: {e4}")
    _launched_at = time.time()  # MISSION-OPS-GUARD-01 F1: base da sessão PRÓPRIA
    # espera o ready marker OU um marcador de tela de erro OU um diálogo do dance
    combined = f"({mc.ready_regex()})|({mc.READY_ERROR_REGEX})|({mc.MCP_PROMPT_REGEX})" \
               f"|{mc.ready_dance_regex()}"
    # DISPATCH-FAST-02 (ready-dance): diálogos first-run conhecidos ("Do you want to use
    # this API key?", trust de pasta, auto-mode banner, welcome/security notes) são
    # navegados AUTOMATICAMENTE pelas teclas mapeadas (mc.READY_DANCE) — determinístico,
    # zero LLM, sem relançar claude. Loop por DEADLINE de 180s com waits curtos: cada
    # rodada espera 15s, decide pela tela inteira (o wait_output traz só a LINHA casada,
    # e o menu do trust fica em outra linha — prova P2 real 27/09), dança quando vê um
    # diálogo conhecido e dorme 2s p/ o claude redesenhar (buffer acumulado = tela velha,
    # prova P3 real 27/09). Max 10 danças = proteção contra tela presa.
    # MISSION-BATCH-01 (ready fail-fast): claude NÃO apontado na ponte Qwen (sonda E2E
    # morta, gpu-up falho ou engine=openrouter) não tem ponte para esperar — o claude
    # local/8103 sobe em segundos; 180s só servia de cova para pane morta. 45s nesse caminho.
    _ready_s = _READY_DEADLINE_S if gpu_up_ok else _READY_DEADLINE_FAST_S
    ledger["readyDeadlineS"] = int(_ready_s)
    out, werr = None, None
    _deadline = time.time() + _ready_s
    _dances = 0
    while time.time() < _deadline:
        out, werr = mc.wait_output(pane_id, regex=combined, timeout_ms=15000)
        if out and mc.has_mcp_prompt(out) and not re.search(mc.ready_regex(), out):
            mc.append_event(mission_id, pane_id, "mcp_prompt", action="enter (continue without MCP)")
            ok2, derr2 = mc.dismiss_mcp_prompt(pane_id)
            if ok2:
                out, werr = None, None
                continue
        if out and re.search(mc.ready_regex(), out):
            break  # ready de verdade: nada a dançar
        text, _ = mc.read_output(pane_id, lines=60)
        if text and re.search(mc.ready_regex(), text):
            out = text  # ready visível na tela inteira (não veio no wait de 15s)
            break
        dance_keys = mc.ready_dance_keys(text or "")
        if dance_keys:
            if _dances >= 10:
                out, werr = None, "ready-dance excedeu 10 rodadas (tela presa)"
                break
            _dances += 1
            mc.append_event(mission_id, pane_id, "ready_dance",
                            action=dance_keys, detail=(text or "")[:200])
            derr = None
            for key in dance_keys.split():  # 1 tecla por send-keys ("down enter" = 2)
                time.sleep(_DANCE_KEY_DELAY_S)  # deixa o claude desenhar o estado entre teclas
                if derr := mc.send_keys(pane_id, key.strip()):
                    break
            if derr:
                mc.append_event(mission_id, pane_id, "ready_dance_failed", detail=derr)
                out, werr = None, f"ready-dance keys '{dance_keys}' falharam: {derr}"
                break
            time.sleep(_DANCE_REDRAW_S)  # claude redesenha; a próxima rodada re-avalia a tela
            out = None
            continue
        if not out:
            continue  # nada visível ainda: segue esperando dentro do deadline
        break  # wait casou algo que não é ready nem diálogo: deixa o pós-loop classificar
    if not out:
        text, _ = mc.read_output(pane_id, lines=60)
        if mc.has_ready_error(text or ""):
            ledger["status"] = "needs_recovery"
            ledger["updatedAt"] = mc._now()
            mc.save_ledger(ledger)
            mc.append_event(mission_id, pane_id, "ready_regex_error", detail=cwd)
            return _err("READY_REGEX_ERROR",
                        f"claude parou em tela de erro/trust (cwd={cwd}) — rode "
                        f"mission_recover(pattern='ready_regex_error', paneId='{pane_id}', "
                        f"cwd='<cwd com config do projeto>')")
        ledger["status"] = "start_timeout"
        ledger["updatedAt"] = mc._now()
        mc.save_ledger(ledger)
        mc.append_event(mission_id, pane_id, "claude_start_timeout", detail=werr or "")
        return _err("CLAUDE_START_TIMEOUT",
                    f"claude abriu mas não sinalizou pronto em {int(_ready_s)}s; pane registrado no ledger — "
                    "mission_watch para observar, mission_recover shell_fallback se virou shell")
    if mc.has_ready_error(out):
        ledger["status"] = "needs_recovery"
        ledger["updatedAt"] = mc._now()
        mc.save_ledger(ledger)
        mc.append_event(mission_id, pane_id, "ready_regex_error", detail=cwd)
        return _err("READY_REGEX_ERROR",
                    f"claude parou em tela de erro/trust (cwd={cwd}) — rode "
                    f"mission_recover(pattern='ready_regex_error', paneId='{pane_id}', "
                    f"cwd='<cwd com config do projeto>')")
    # RD-DISO-01 item 8: espera real do provider (claude lançado → ready marker)
    lat.timed("ready_ms", mission_id, _launched_at, fallback=not gpu_up_ok,
              detail="engine=%s" % ledger.get("engine"))
    ok, derr = mc.deliver_prompt(pane_id, mc.dispatch_prompt(ledger['promptFile'], mission_id))
    # MISSION-OPS-GUARD-01 F1 (SESSION-SHARE-01): sessão PRÓPRIA — nascida neste
    # lançamento e sem dono em outro ledger. A jsonl mais nova do cwd era a sessão VIVA de
    # outra missão no mesmo project dir (fix-02 herdou 8329080a do watch-fp-01).
    ledger["resumeSessionId"] = mc.own_session_id(mission_id, cwd, since=_launched_at,
                                                  wait_s=mc.SESSION_WAIT_S if ok else 0.0)
    mc.save_ledger(ledger)
    if not ok:
        ledger["status"] = "prompt_failed"
        ledger["updatedAt"] = mc._now()
        mc.save_ledger(ledger)
        mc.append_event(mission_id, pane_id, "prompt_failed", detail=derr or "")
        return _err("PROMPT_DELIVERY_FAILED",
                    f"{derr or ''} — re-dispatch do mesmo missionId re-tenta a entrega no pane existente")
    ledger["status"] = "dispatched"
    ledger["dispatchedAt"] = mc._now()  # DISPATCH-FAST-02: base da métrica despacho→working
    ledger["updatedAt"] = mc._now()
    mc.save_ledger(ledger)
    mc.append_event(mission_id, pane_id, "prompt_sent", detail=ledger["promptFile"])
    return _j({"ok": True, "status": "dispatched", "missionId": mission_id,
               "paneId": pane_id, "tabId": ledger["tabId"], "creation": ledger["creation"],
               "cwd": cwd, "promptFile": ledger["promptFile"],
               "resumeSessionId": ledger["resumeSessionId"],
               "spawned_by": ledger["spawned_by"], "chain_depth": ledger["chain_depth"],
               "obeyWarnings": _obey_dispatch,
               "note": "supervisione com mission_watch; verificação do relatório é do supervisor"})


# ---------------------------------------------------------------- MISSION-BATCH-01
# Despacho em lote determinístico: N missões numa chamada só (zero LLM entre elas),
# SEQUENCIAL (herdr é single-writer), tolerante a falha individual, com anti-fantasma
# embutido (ledger dispatching/failed/interrupted de pane morto -> cancelled -> re-despacho).
_BATCH_MIN, _BATCH_MAX = 2, 6
_GHOST_STATUSES = {"dispatching", "failed", "interrupted"}
# ledger `dispatching` SEM paneId só é fantasma depois do pior dispatch possível
# (gpu-up 720s + ready 180s) — antes disso pode ser um dispatch ainda em curso.
_GHOST_NO_PANE_AGE_S = 900
# chaves do item repassadas ao mission_dispatch (o resto do item é ignorado)
_BATCH_ITEM_KEYS = ("missionId", "promptFile", "cwd", "consequence", "paneTitle",
                    "engine", "spawnedBy", "operatorChannel", "chainBasis")


def _batch_load_manifest(args: Dict[str, Any]) -> "tuple[Optional[List[Any]], str]":
    """missions (lista inline) > manifest (caminho .json/.yaml/.yml, ou o texto do manifesto).
    Topo aceito: lista de itens ou {missions: [...]}. Devolve (itens, erro)."""
    data: Any = args.get("missions")
    if data is None:
        raw = args.get("manifest")
        if isinstance(raw, (list, dict)):
            data = raw
        else:
            raw = str(raw or "").strip()
            if not raw:
                return None, "passe manifest (arquivo JSON/YAML) ou missions (lista)"
            text = raw
            if not raw.lstrip().startswith(("[", "{")) and "\n" not in raw:
                if not os.path.isfile(raw):
                    return None, f"manifesto não existe: {raw}"
                try:
                    with open(raw, encoding="utf-8") as f:
                        text = f.read()
                except OSError as e:
                    return None, f"manifesto ilegível: {e}"
            try:
                data = json.loads(text)
            except ValueError:
                try:
                    import yaml as _yaml
                    data = _yaml.safe_load(text)
                except Exception as e:
                    return None, f"manifesto não é JSON nem YAML válido: {str(e)[:200]}"
    if isinstance(data, dict):
        data = data.get("missions")
    if not isinstance(data, list):
        return None, "manifesto deve ser uma lista de missões (ou {missions: [...]})"
    return data, ""


def _ledger_age_s(ledger: Dict[str, Any]) -> Optional[float]:
    ts = str(ledger.get("updatedAt") or ledger.get("createdAt") or "")
    try:
        import calendar
        return time.time() - calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OverflowError):
        return None


def _batch_ghost_check(mission_id: str) -> "tuple[Optional[Dict[str, Any]], str]":
    """(ledger fantasma, motivo) se o ledger é um fantasma a limpar; (None, motivo) senão.
    Fantasma = status dispatching/failed/interrupted E pane comprovadamente morto
    (pane_exists=False). herdr indisponível (None) = NÃO adivinha: deixa o dispatch decidir."""
    led = mc.load_ledger(mission_id)
    if not led or led.get("status") not in _GHOST_STATUSES:
        return None, ""
    st, pane = led.get("status"), str(led.get("paneId") or "")
    if pane:
        try:
            alive = mc.pane_exists(pane)
        except Exception:
            alive = None
        if alive is False:
            return led, f"{st} com pane {pane} morto"
        return None, f"{st} com pane {pane} " + ("vivo" if alive else "em estado desconhecido")
    age = _ledger_age_s(led)
    if st != "dispatching" or (age is not None and age >= _GHOST_NO_PANE_AGE_S):
        return led, f"{st} sem pane" + (f" há {int(age)}s" if age is not None else "")
    return None, f"dispatching sem pane há {int(age or 0)}s (< {_GHOST_NO_PANE_AGE_S}s: pode estar em curso)"


def _batch_cancel_ghost(led: Dict[str, Any], why: str, by: str = "mission_batch",
                        tail: str = "cancelado e re-despachado no lote",
                        event: str = "batch_ghost_cancelled") -> Dict[str, Any]:
    mid = led["missionId"]
    prev = led.get("status")
    reason = f"{by} anti-fantasma: {why} — {tail}"
    sup = led.get("supervisor")
    if isinstance(sup, dict) and not sup.get("stoppedAt") and ms is not None:
        # supervisor órfão do fantasma: encerra antes do re-despacho (o novo nasce no dispatch)
        killed = _ms("kill_all", mid)
        sup.update(stoppedAt=mc._now(), stopReason=f"{by}_ghost")
        if killed:
            sup["killed"] = killed
    led.update(status="cancelled", cancelReason=reason, cancelledBy=by,
               cancelledAt=mc._now(), updatedAt=mc._now(), previousStatus=prev)
    mc.save_ledger(led)
    mc.append_event(mid, led.get("paneId"), event, detail=reason)
    return {"previousStatus": prev, "paneId": led.get("paneId"), "reason": reason}


def handle_mission_batch(args: Dict[str, Any], **_kw) -> str:
    items, e = _batch_load_manifest(args)
    if e:
        return _err("INVALID_MANIFEST", e)
    if not (_BATCH_MIN <= len(items) <= _BATCH_MAX):
        return _err("BATCH_SIZE_OUT_OF_RANGE",
                    f"lote aceita {_BATCH_MIN}-{_BATCH_MAX} missões; veio {len(items)} "
                    f"(1 missão = mission_dispatch)")
    ids: List[str] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not str(it.get("missionId") or "").strip() \
                or not str(it.get("promptFile") or "").strip():
            return _err("INVALID_MANIFEST", f"item {i}: exige objeto com missionId e promptFile")
        ids.append(str(it["missionId"]).strip())
    dup = sorted({m for m in ids if ids.count(m) > 1})
    if dup:
        return _err("INVALID_MANIFEST", f"missionId repetido no lote: {', '.join(dup)}")

    t0 = time.time()
    results: List[Dict[str, Any]] = []
    for it in items:  # SEQUENCIAL de propósito: herdr single-writer
        mid = str(it["missionId"]).strip()
        t_item = time.time()
        row: Dict[str, Any] = {"missionId": mid}
        try:
            ghost, why = _batch_ghost_check(mid)
            if ghost:
                row["ghost"] = _batch_cancel_ghost(ghost, why)
            elif why:
                row["ledgerNote"] = why
            dargs = {k: it[k] for k in _BATCH_ITEM_KEYS if it.get(k) is not None}
            dargs["missionId"] = mid
            res = json.loads(handle_mission_dispatch(dargs))
        except Exception as exc:  # item nunca derruba o lote
            res = {"ok": False, "error": "BATCH_ITEM_EXCEPTION", "detail": str(exc)[:400]}
        row["seconds"] = round(time.time() - t_item, 2)
        if res.get("ok"):
            row["result"] = "fantasma-limpo" if row.get("ghost") else "ok"
            row.update(status=res.get("status"), paneId=res.get("paneId"), tabId=res.get("tabId"))
        else:
            row.update(result="erro", error=res.get("error"), detail=res.get("detail"))
        results.append(row)

    ok_rows = [r for r in results if r["result"] != "erro"]
    return _j({
        "ok": len(ok_rows) == len(results),
        "total": len(results),
        "despachadas": len(ok_rows),
        "falhas": len(results) - len(ok_rows),
        "fantasmasLimpos": sum(1 for r in results if r.get("ghost")),
        "tempoTotalS": round(time.time() - t0, 2),
        "tempoPorMissao": {r["missionId"]: r["seconds"] for r in results},
        "itens": results,
        "note": "sequencial (herdr single-writer); supervisione com mission_watch",
    })


# ---------------------------------------------------------------- SNAPSHOT-FAST-01
# "verifique a missão X" em 1 chamada: ledger + pane REAL (1 tab list + 1 pane list) +
# verdict + auto-correção determinística (só ledger). Zero LLM, zero escrita em pane.
_SNAP_FUZZY_MIN = 0.8
_SNAP_SCAN_STATUSES = mc.ACTIVE_STATUSES | {"dispatching"}
# ledger ativo com pane vivo mas parado numa tela recuperável
_SNAP_RECOVER_STATUSES = {"interrupted", "needs_recovery", "start_timeout", "prompt_failed",
                          "autocompact"}
# ANTI-GHOST-HARNESS: resumo.json só vale se realpath cair sob estas raízes
# (anti-symlink: cwd do ledger não é confiável).
_ANTIGHOST_RESUMO_ROOTS = ("/home/worker", "/opt/mission-events")
_ANTIGHOST_MID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _snap_score(fragment: str, mission_id: str) -> float:
    """Similaridade fragment x missionId: substring = 1.0; senão o melhor ratio do difflib
    contra o id inteiro, cada token (-_.) e janelas do tamanho do fragment (±1)."""
    import difflib
    f, m = fragment.lower(), mission_id.lower()
    if f in m:
        return 1.0
    cands = {m, *[t for t in re.split(r"[-_.]", m) if t]}
    for n in (len(f) - 1, len(f), len(f) + 1):
        if n > 0:
            cands.update(m[i:i + n] for i in range(max(1, len(m) - n + 1)))
    return max(difflib.SequenceMatcher(None, f, c).ratio() for c in cands)


def _snap_match(fragment: str, ledgers: List[Dict[str, Any]]) -> List[tuple]:
    scored = [(round(_snap_score(fragment, str(l.get("missionId") or "")), 3), l)
              for l in ledgers if l.get("missionId")]
    hits = [(s, l) for s, l in scored if s >= _SNAP_FUZZY_MIN]
    exact = [(s, l) for s, l in hits if s == 1.0]
    # "verifique a missão X": a ativa primeiro, depois a mais recente (não a alfabética)
    return sorted(exact or hits, key=lambda x: (x[1].get("status") not in _SNAP_SCAN_STATUSES,
                                                -x[0], _snap_desc(x[1].get("updatedAt")),
                                                str(x[1].get("missionId"))))


def _snap_desc(ts: Any) -> tuple:
    """chave de ordenação DESCENDENTE para timestamp ISO (Z) — sem parse, sem crash."""
    return tuple(-ord(c) for c in str(ts or ""))


def _snap_pane_view(p: Optional[Dict[str, Any]], tab_by_id: Dict[str, Any]) -> Dict[str, Any]:
    if not p:
        return {"exists": False}
    return {"exists": True, "paneId": p.get("pane_id"), "tabId": p.get("tab_id"),
            "agent": p.get("agent"), "agent_status": p.get("agent_status"),
            "cwd": p.get("cwd"),
            "tabLabel": (tab_by_id.get(p.get("tab_id")) or {}).get("label")}


def _snap_one(led: Dict[str, Any], tabs: Optional[List[Dict[str, Any]]],
              panes: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    mid = str(led.get("missionId"))
    st = led.get("status")
    pid, tid = led.get("paneId"), led.get("tabId")
    le = mc.last_event(mid) or {}
    row: Dict[str, Any] = {"missionId": mid, "status": st, "paneId": pid, "tabId": tid,
                           "cwd": led.get("cwd"), "lastEvent": le.get("event"),
                           "lastEventAt": le.get("ts")}
    if st not in _SNAP_SCAN_STATUSES:
        row.update(verdict="OK", pane=None,
                   remedy={"applied": False, "note": f"missão {st or 'sem status'} — nada a fazer"})
        return row
    if tabs is None or panes is None:
        row.update(verdict="DESCONHECIDO", pane=None,
                   remedy={"applied": False,
                           "suggested": "herdr indisponível — repita o mission_snapshot (nada foi alterado)"})
        return row

    tab_by_id = {t.get("tab_id"): t for t in tabs if isinstance(t, dict) and t.get("tab_id")}
    pane_by_id = {p.get("pane_id"): p for p in panes if isinstance(p, dict) and p.get("pane_id")}
    label = f"MISSION:{mid}"
    # abas da missão: label MISSION:<id> + a tabId do ledger (pane renumerado na mesma aba)
    mtabs = [t for t, v in tab_by_id.items() if v.get("label") == label or (tid and t == tid)]
    real = pane_by_id.get(pid) if pid else None
    row["pane"] = _snap_pane_view(real, tab_by_id)

    if real:
        dups = [{"tabId": t, "paneId": next((p for p, v in pane_by_id.items()
                                              if v.get("tab_id") == t), None)}
                for t in mtabs if t != real.get("tab_id")]
        if dups:
            row["duplicateTabs"] = dups
        if st in _SNAP_RECOVER_STATUSES:
            sug = (f"mission_dispatch(missionId={mid}) re-entrega o prompt" if st == "prompt_failed"
                   else f"mission_recover(paneId={pid}, pattern=interrupted, missionId={mid})")
            row.update(verdict="INTERROMPIDA", remedy={"applied": False, "suggested": sug})
        elif real.get("agent") != "claude":
            row.update(verdict="INTERROMPIDA", remedy={
                "applied": False,
                "suggested": f"pane virou shell: mission_recover(paneId={pid}, "
                             f"pattern=shell_fallback, missionId={mid})"})
        else:
            row.update(verdict="OK", remedy={"applied": False})
        if dups:
            row["remedy"]["note"] = (f"{len(dups)} aba(s) duplicada(s) com {label} — "
                                     "não fechadas (só o mission_close fecha aba)")
        return row

    # ledger aponta pane inexistente (ou não tem pane)
    cands = [p for p in pane_by_id.values() if p.get("tab_id") in mtabs]
    if len(cands) > 1:  # desempate determinístico: claude vivo no cwd do ledger
        pref = [p for p in cands if p.get("agent") == "claude"
                and (not led.get("cwd") or p.get("cwd") == led.get("cwd"))]
        cands = pref if len(pref) == 1 else cands
    if len(cands) == 1:
        new = cands[0]
        prev = {"paneId": pid, "tabId": tid}
        cur = mc.load_ledger(mid) or led  # relê: não pisa escrita concorrente
        cur.update(paneId=new.get("pane_id"), tabId=new.get("tab_id"), updatedAt=mc._now(),
                   paneResync={"at": mc._now(), "by": "mission_snapshot", "from": prev})
        mc.save_ledger(cur)
        detail = (f"paneId obsoleto {pid}/{tid} -> {new.get('pane_id')}/{new.get('tab_id')} "
                  f"(aba {label} viva)")
        mc.append_event(mid, new.get("pane_id"), "snapshot_pane_resync", detail=detail)
        row.update(verdict="PANEID_OBSOLETO", paneId=new.get("pane_id"), tabId=new.get("tab_id"),
                   pane=_snap_pane_view(new, tab_by_id),
                   remedy={"applied": True, "action": "ledger re-sincronizado", "detail": detail,
                           "from": prev})
        return row
    if cands:
        row.update(verdict="PANEID_OBSOLETO", remedy={
            "applied": False,
            "candidates": [{"paneId": p.get("pane_id"), "tabId": p.get("tab_id"),
                            "agent_status": p.get("agent_status")} for p in cands],
            "suggested": f"{len(cands)} abas {label} vivas — ambíguo, ledger NÃO alterado; "
                         "feche a duplicada com mission_close/tab close e repita"})
        return row
    if not pid and st == "dispatching":
        age = _ledger_age_s(led)
        if age is None or age < _GHOST_NO_PANE_AGE_S:
            row.update(verdict="DESPACHANDO", remedy={
                "applied": False,
                "note": f"dispatching sem pane há {int(age or 0)}s (< {_GHOST_NO_PANE_AGE_S}s: "
                        "dispatch pode estar em curso)"})
            return row
    if not pid and led.get("engine") and led.get("headless"):
        # ANTI-GHOST-HARNESS: missões harness/headless rodam sem pane POR DESIGN —
        # não são fantasmas enquanto houver sinal de vida (headlessPid vivo com
        # /proc/<pid>/cmdline não vazio, evita PID reutilizado trivial) ou artefato
        # de execução (runs/<mid>/resumo.json sob raiz confiável). Fail-open:
        # qualquer exceção aqui segue o fluxo anti-fantasma atual.
        try:
            alive = False
            try:
                hp = int(led.get("headlessPid"))
            except (TypeError, ValueError):
                hp = None
            if hp and hp > 0:
                try:
                    os.kill(hp, 0)
                    alive = True
                except PermissionError:
                    alive = True  # existe, mas é de outro user -> vivo
                except OSError:
                    alive = False
                if alive and not open(f"/proc/{hp}/cmdline", "rb").read(1):
                    alive = False
            if not alive and _ANTIGHOST_MID_RE.match(mid):
                rp = os.path.realpath(os.path.join(str(led.get("cwd") or ""),
                                                   "runs", mid, "resumo.json"))
                roots = tuple(os.path.realpath(r) for r in _ANTIGHOST_RESUMO_ROOTS)
                if os.path.isfile(rp) and any(
                        rp == r or rp.startswith(r + os.sep) for r in roots):
                    alive = True
            if alive:
                row.update(verdict="OK", pane=None,
                           remedy={"applied": False,
                                   "note": "missão harness/headless sem pane (por "
                                           "design) — sinal de vida presente, não é "
                                           "fantasma"})
                return row
        except Exception:
            pass  # fail-open: segue o fluxo atual (fantasma)
    why = (f"{st} com pane {pid} inexistente e sem aba {label}" if pid
           else f"{st} sem pane e sem aba {label}")
    g = _batch_cancel_ghost(mc.load_ledger(mid) or led, why, by="mission_snapshot",
                            tail="cancelado (re-despache com mission_dispatch se ainda devida)",
                            event="snapshot_ghost_cancelled")
    row.update(verdict="FANTASMA", status="cancelled",
               remedy={"applied": True, "action": "cancelado", "detail": g["reason"],
                       "previousStatus": g["previousStatus"]})
    return row


def _obedience_warnings() -> List[Dict[str, Any]]:
    """SUP-OBEY-01: warnings de obediência do chamador atual.

    (4) dispatch_not_orchestrator: fila do orquestrador com intents pendentes e o
    chamador NÃO é o daemon do orquestrador (ORCH_DAEMON_APPROVED) → despacho
    da fila não é trabalho do supervisor (OBRIGACOES.md item 3).
    Nunca levanta; [] se o guard está off."""
    out: List[Dict[str, Any]] = []
    try:
        if os.environ.get("ORCH_DAEMON_APPROVED") in ("1", "true", "yes"):
            return out  # o chamador É o daemon do orquestrador — sem warning
        w = ob.dispatch_owner_guard(os.environ.get("HERDR_PANE_ID"),
                                    os.environ.get("ORCH_DAEMON_PANE_ID"),
                                    queue_path=(os.environ.get("MISSION_ORCH_QUEUE")
                                                or ob.ORCH_QUEUE_PATH))
        if w:
            out.append(w)
    except Exception:
        pass  # guard de obediência nunca derruba o watch
    return out


def _announce_direct_ship() -> List[Dict[str, Any]]:
    """SUP-OBEY-01 (3): 1x por ciclo — violações de ship direto do dia ainda não
    anunciadas vão para o bus (direct_ship_violation). Retorna as NOVAS; nunca levanta."""
    try:
        fresh = ob.new_direct_ship_findings(
            events_path=os.path.join(str(mc.STATE_DIR), "events.jsonl"))
        for v in fresh:
            mc.append_event("?", None, "direct_ship_violation",
                            detail="[%s] %s (missão %s)" % (v["match"], v["pattern"],
                                                            v.get("missionId") or "?"))
            vg.emit_bus_event("direct_ship_violation", str(v.get("missionId") or "?"),
                              "%s em %s — ship é via missão SHIP-<alvo>" % (v["match"], v["pattern"]))
        return fresh
    except Exception:
        return []


def handle_mission_snapshot(args: Dict[str, Any], **_kw) -> str:
    t0 = time.time()
    mission_id = str(args.get("missionId") or "").strip()
    fragment = str(args.get("fragment") or "").strip()
    warnings: List[str] = []
    match: Dict[str, Dict[str, Any]] = {}
    if mission_id:
        if e := mc.validate_mission_id(mission_id):
            return _err("INVALID_MISSION_ID", e)
        led = mc.load_ledger(mission_id)
        if led is None:
            near = [str(l.get("missionId")) for _, l in _snap_match(mission_id, mc.list_ledgers())]
            return _err("MISSION_NOT_FOUND", f"nenhum ledger para {mission_id}"
                        + (f"; parecidas: {', '.join(near[:5])}" if near else ""))
        ledgers = [led]
    elif fragment:
        hits = _snap_match(fragment, mc.list_ledgers())
        if not hits:
            return _err("MISSION_NOT_FOUND",
                        f"nenhuma missão casa '{fragment}' (substring ou difflib >= {_SNAP_FUZZY_MIN})")
        ledgers = [l for _, l in hits[:10]]
        match = {str(l.get("missionId")): {"fragment": fragment, "score": s} for s, l in hits[:10]}
        if len(hits) > 10:
            warnings.append(f"{len(hits)} missões casam '{fragment}' — mostrando 10")
    else:
        ledgers = [l for l in mc.list_ledgers() if l.get("status") in _SNAP_SCAN_STATUSES]
        if not ledgers:
            return _j({"ok": True, "missions": [], "fixed": [], "ghosts": [],
                       "summary": {"fixed": [], "ghosts": [], "ok": []},
                       "note": "nenhuma missão ativa", "seconds": round(time.time() - t0, 2)})

    tabs = panes = None
    if any(l.get("status") in _SNAP_SCAN_STATUSES for l in ledgers):
        tabs, terr = mc.tab_list()
        panes, perr = mc.pane_list()
        if terr or perr:  # parcial não serve: sem as duas listas não se decide nada
            warnings += [f"tab list: {terr}"] * bool(terr) + [f"pane list: {perr}"] * bool(perr)
            tabs = panes = None

    rows = []
    for l in ledgers:
        try:
            r = _snap_one(l, tabs, panes)
        except Exception as exc:  # uma missão nunca derruba o snapshot
            r = {"missionId": l.get("missionId"), "status": l.get("status"),
                 "verdict": "DESCONHECIDO",
                 "remedy": {"applied": False, "error": str(exc)[:300]}}
        if l.get("missionId") in match:
            r["match"] = match[l["missionId"]]
        rows.append(r)
    fixed = [r["missionId"] for r in rows
             if r["verdict"] == "PANEID_OBSOLETO" and r["remedy"].get("applied")]
    ghosts = [r["missionId"] for r in rows if r["verdict"] == "FANTASMA"]
    oks = [r["missionId"] for r in rows if r["verdict"] == "OK"]
    out: Dict[str, Any] = {"ok": True, "missions": rows, "fixed": fixed, "ghosts": ghosts,
                           "summary": {"fixed": fixed, "ghosts": ghosts, "ok": oks},
                           "seconds": round(time.time() - t0, 2)}
    if warnings:
        out["warnings"] = warnings
    return _j(out)


def handle_mission_watch(args: Dict[str, Any], **_kw) -> str:
    target = str(args.get("missionId") or "").strip()
    watch_all = str(args.get("all") or "").strip() in ("1", "true", "all", "yes")
    timeout_ms = int(args.get("timeoutMs") or 60000)
    timeout_ms = min(max(timeout_ms, 1000), 600000)
    per_pane_ms = int(args.get("perPaneTimeoutMs") or 10000) if watch_all else timeout_ms
    # 25/09 snapshot: "verifique as missões" = STATUS AGORA, não vigília. O modo all
    # era um esperador de eventos (até 10s POR pane sequencial = 50s com 5 missões
    # quando nada acontece — cobrança do operador: "isso não é aceitável").
    # snapshot=True: 1 pane_list + 1 leitura curta por pane, SEM espera bloqueante.
    # modo all = snapshot por padrão; single-mission continua vigilância bloqueante
    # (é o caso de uso de espera de evento) a menos que snapshot=true seja pedido.
    snapshot = (str(args.get("snapshot") or "").strip() in ("1", "true", "yes")
                or watch_all or not target)

    if target and (e := mc.validate_mission_id(target)):
        return _err("INVALID_MISSION_ID", e)

    if watch_all or not target:
        ledgers = [l for l in mc.list_ledgers() if l.get("status") in mc.ACTIVE_STATUSES]
        if not ledgers:
            return _j({"ok": True, "missions": [], "note": "nenhuma missão ativa"})
        panes_exist = None
        snapshot_panes = None
        if snapshot:
            panes, perr = mc.pane_list()
            if perr is None and panes is not None:
                snapshot_panes = panes
                panes_exist = {p.get("pane_id") for p in panes}
        results = []
        for l in ledgers:
            # RD-DISO-01 item 2: heartbeat do lease no ciclo do watch (crash-safe —
            # sem batimento, o lease vence pelo TTL e a fila reaproveita o componente).
            if l.get("component"):
                try:
                    leases.heartbeat(str(l["missionId"]), str(l["component"]))
                except Exception:
                    pass  # heartbeat fail-open: vencer pelo TTL é o fallback seguro
            r = _watch_one(l["missionId"], l, per_pane_ms,
                           snapshot=snapshot, panes_exist=panes_exist)
            results.append(r)
        # MISSION-NOTIFY-01: sondas infra 1x por ciclo (asset_lost, budget_alert) +
        # varredura MULTI-WORKSPACE de panes órfãos (turn_done de claude em qualquer
        # workspace — o gap real da watchdog-02 que só via w3).
        # ORCH-LIVENESS-02: sonda do orchestrator-consumer entra no MESMO ciclo
        # (fantasma: state alive com consumer morto → stopped + evento no bus).
        infra_probes = nf.run_probes(mission_id="infra:watch-cycle", skip_consumer=False,
                                     skip_obey=False)  # OBEY-HARD-GATE-01 (T4): vigia do obey no ciclo
        orphan = _scan_orphan_panes(snapshot_panes)
        # MISSION-SUPERVISOR-01: ciclo do supervisor por missão (órfão → respawn)
        orphan += _ms("watch_cycle", mc, ledgers) or []
        # SUP-OBEY-01: guarda de ship direto (bus registra direct_ship_violation do
        # dia 1x por ciclo) + warning de despacho fora do orquestrador.
        ship_fresh = _announce_direct_ship()
        obey_warnings = _obedience_warnings()
        # RD-OBEY-02 (watchdog do ack): ordem nova desde o último sup_ack =
        # finding `obligation_stale` no bus (1x por hash) até novo ack — o ciclo
        # de watch é o batimento determinístico que compara o hash.
        try:
            _stale = obr.check_stale(spool_path=_MISSION_SPOOL)
        except Exception:
            _stale = {}
        _out_all = {"ok": True, "mode": "snapshot" if snapshot else "all",
                    "missions": results,
                    "probes": [{"kind": p["kind"], "emitted": bool(p.get("emitted")),
                                "detail": p["detail"]}
                               for p in infra_probes + orphan]}
        if ship_fresh:
            _out_all["directShipViolations"] = ship_fresh
        if obey_warnings:
            _out_all["warnings"] = obey_warnings
        if _stale.get("stale"):
            _out_all["obligationStale"] = _stale
        # ORCH-LIVENESS-02 item 3: health REAL do orchestrator-consumer no snapshot
        # (fonte de verdade = PID do heartbeat). Consumer morto → warning no
        # snapshot; a sonda acima já corrigiu o state mentiroso p/ stopped + evento.
        try:
            _orch_h = nf._orch_consumer_health()
        except Exception:
            _orch_h = {"alive": False, "reason": "probe-error"}
        _out_all["consumerHealth"] = {"alive": bool(_orch_h.get("alive")),
                                      "reason": _orch_h.get("reason"),
                                      "pid": _orch_h.get("pid"),
                                      "stateStatus": _orch_h.get("stateStatus")}
        if not _orch_h.get("alive") and _orch_h.get("reason") != "no-heartbeat":
            _orch_warn = {"kind": "orch_consumer_dead", "missionId": "infra:orchestrator",
                          "detail": "orchestrator-consumer %s (pid=%s) — a fila não está sendo consumida"
                                    % (_orch_h.get("reason"), _orch_h.get("pid"))}
            _out_all["warnings"] = list(_out_all.get("warnings") or []) + [_orch_warn]
        # RD-DISO-01 item 8: p50/p99 de latência no snapshot (mesma doutrina do custo)
        _out_all["latency"] = lat.watch_summary()
        return _j(_out_all)

    ledger = mc.load_ledger(target)
    if ledger is None:
        return _err("MISSION_NOT_FOUND", f"nenhum ledger para {target}")
    if ledger.get("component"):
        try:
            leases.heartbeat(target, str(ledger["component"]))
        except Exception:
            pass
    if not ledger.get("paneId"):
        return _err("NO_PANE", "ledger sem paneId (dispatch falhou?)")
    r = _watch_one(target, ledger, timeout_ms, snapshot=snapshot)
    _out_single: Dict[str, Any] = {**r, "mode": "snapshot" if snapshot else "single",
                                   "latency": lat.watch_summary()}
    _obey = _obedience_warnings()
    if _obey:
        _out_single["warnings"] = _obey
    return _j(_out_single)


def _watch_one(mission_id: str, ledger: Dict[str, Any], timeout_ms: int,
               snapshot: bool = False,
               panes_exist: Optional[set] = None) -> Dict[str, Any]:
    # WATCH-DETECTOR-FIX-01 (FP1): relê o ledger — o snapshot do modo all lista os
    # ledgers ANTES de ler os panes e o mission_close pode gravar closed no meio
    # (judge-deploy-01, 28/09: flag needs_supervisor pós-close). Missão encerrada
    # não é supervisionada: sem evento, sem flag, sem mutação.
    fresh = mc.load_ledger(mission_id)
    if fresh is not None:
        ledger = fresh
    if ledger.get("status") in _UNWATCHED_STATUSES:
        return {"missionId": mission_id, "ok": True, "event": "no_event",
                "verdict": "closed", "status": ledger.get("status"),
                "note": "missão %s — snapshot não supervisiona (sem flag)" % ledger.get("status")}
    pane_id = ledger.get("paneId")
    # MISSION-OPS-02: pane/aba fechada de fora -> evento dedicado (não é shell_fallback)
    if pane_id:
        if panes_exist is not None:
            exists = pane_id in panes_exist
        else:
            exists = mc.pane_exists(pane_id)
        if exists is False:
            tab_id = ledger.get("tabId")
            tex = mc.tab_exists(tab_id) if tab_id else False
            event = "tab_closed" if (tex is False or not tab_id) else "pane_closed"
            return _on_event(mission_id, ledger, event, "")
    if snapshot:
        # 25/09: status AGORA — leitura curta, sem espera bloqueante (era wait_output
        # de até timeout_ms/pane por eventos que não acontecem).
        out, werr = mc.read_output(pane_id, lines=40)
    else:
        out, werr = mc.wait_output(pane_id, regex=rc.WATCH_REGEX, timeout_ms=timeout_ms)
    # 25/09 liveness (cobrança do operador: missão PARADA reportada como saudável —
    # "no_event" não distingue trabalhando de estacionada). Em toda leitura:
    # working = claude processando (footer "esc to interrupt"); idle = claude no
    # prompt ⏵⏵ sem processar (missão estacionada: acabou a fase, stall, ou morreu
    # de fome de tarefa); shell/none = o classify_pane pega.
    liveness = None
    if out:
        if "esc to interrupt" in out:
            liveness = "working"
        elif "⏵⏵" in out or "accept edits on" in out:
            liveness = "idle"
    # DISPATCH-FAST-02 (P4): 1º "working" marca workingAt + badge/finding no ledger.
    if liveness == "working" and not ledger.get("workingAt"):
        ledger["workingAt"] = mc._now()
        metric = mc.dispatch_metric(ledger)
        if metric:
            ledger["badge"] = metric["badge"]
            mc.save_ledger(ledger)
        if metric:
            badge = metric["badge"]
            detail = (f"despacho→working {metric['dispatchToWorkingMs']}ms badge={badge}"
                      if badge == "dispatch_fast" else
                      f"FINDING: despacho→working {metric['dispatchToWorkingMs']}ms >= 90s "
                      f"(badge={badge})")
            mc.append_event(mission_id, pane_id, "mission_working", detail=detail)
    event = None
    if out:
        event = rc.classify_text(out)
    # RD-DISO-01 item 8: turno do worker — dispatchedAt → turn_done (p99 do turno)
    if event == "turn_done":
        _t_disp = _iso_to_epoch(str((ledger or {}).get("dispatchedAt") or ""))
        if _t_disp:
            lat.record("turn_ms", mission_id, (time.time() - _t_disp) * 1000.0,
                       detail="turn_done no watch")
    # TEMPLATE-PROTOCOL-01: prova de ingestão — o worker ecoa `CONTRATO OK <missionId>`
    # logo após ler o contrato. Registrar 1x (dedupe no ledger); nunca bloqueia.
    if out and not ledger.get("contractIngestedAt"):
        m = re.search(r"CONTRATO OK\s+([A-Za-z0-9._-]+)", out)
        if m:
            ledger["contractIngestedAt"] = mc._now()
            mc.save_ledger(ledger)
            mc.append_event(mission_id, pane_id, "contract_ingested",
                            detail=f"eco detectado: CONTRATO OK {m.group(1)}")
    if event is None:
        # sem match de regex: o pane virou shell? (claude saiu / nunca subiu)
        event, cerr = rc.classify_pane(pane_id)
        if cerr:
            return {"missionId": mission_id, "ok": False, "error": cerr}
        if event is None:
            note = ("claude idle/estacionada — sem evento, sem processamento"
                    if liveness == "idle" else "sem evento no período observado")
            return {"missionId": mission_id, "ok": True, "event": "no_event",
                    "liveness": liveness or "unknown", "note": note}
    result = _on_event(mission_id, ledger, event, out or "")
    result["liveness"] = liveness or ("shell" if event == "shell_fallback" else "unknown")
    # MISSION-NOTIFY-01: sondas por-pane (context_low, transcript_corrupt, pane_lost)
    # com emissão no bus — determinístico, dedupe por assinatura. asset/budget rodam
    # 1x por ciclo de watch (caller), não por pane.
    probes = nf.run_probes(text=(out or "") if event is not None else None,
                           mission_id=mission_id, pane_id=pane_id,
                           panes_exist=panes_exist,
                           skip_asset=True, skip_budget=True)
    result["probes"] = [{"kind": p["kind"], "emitted": bool(p.get("emitted"))}
                        for p in probes]
    return result


def _on_event(mission_id: str, ledger: Dict[str, Any], event: str, snippet: str) -> Dict[str, Any]:
    """Update ledger + events.jsonl; auto-apply ONLY the safe recipes."""
    pane_id = ledger.get("paneId")
    result: Dict[str, Any] = {"missionId": mission_id, "paneId": pane_id, "event": event}
    mc.append_event(mission_id, pane_id, event, detail=snippet.strip()[:200] or None)

    if event == "interrupted":
        ledger["status"] = "interrupted"
        r, err = rc.recover(pane_id, "interrupted", ledger)
        result.update({"autoRecipe": r, "error": err} if err else {"autoRecipe": r})
    elif event == "palette":
        ledger["status"] = "dispatched"
        r, err = rc.recover(pane_id, "palette", ledger)
        result.update({"autoRecipe": r, "error": err} if err else {"autoRecipe": r})
    elif event == "mcp_prompt":
        # auto-safe: Enter no default ❯ "Continue without using this MCP server"
        ledger["status"] = "dispatched"
        r, err = rc.recover(pane_id, "mcp_prompt", ledger)
        result.update({"autoRecipe": r, "error": err} if err else {"autoRecipe": r})
    elif event == "autocompact":
        ledger["status"] = "autocompact"
        result["autoRecipe"] = {"recipe": "autocompact", "applied": "marked only"}
    elif event == "ready_regex_error":
        ledger["status"] = "needs_recovery"
        result["note"] = ("marcado needs_recovery — rode mission_recover(pattern='ready_regex_error', "
                          f"paneId='{pane_id}', cwd='<cwd com config do projeto>')")
    elif event in ("pane_closed", "tab_closed"):
        ledger["status"] = "closed"
        result["note"] = "missão encerrada de fora (pane/aba fechada)"
    elif event == "waiting_operator":
        # MISSION-NOTIFY-01: pergunta legítima ao operator = transição waiting_operator
        # + PUSH no bus (NÃO é nudge da watchdog — camadas distintas).
        ledger["status"] = "waiting_operator"
        w_notify = nf.mission_waiting_operator(mission_id, snippet.strip()[:200] or "?")
        result["notifyWaitingOperator"] = bool(w_notify.get("emitted"))
    elif event in ("transcript400", "shell_fallback"):
        ledger["status"] = "needs_recovery"
        result["note"] = f"marcado needs_recovery — rode mission_recover(pattern={event})"
        result["autoRecipe"] = None
    elif event == "contract_ingested":
        # TEMPLATE-PROTOCOL-01: prova de ingestão do contrato — só registra, nunca bloqueia.
        result["note"] = "contrato confirmado lido pelo worker (eco CONTRATO OK)"
    elif event == "delivered":
        ledger["status"] = "delivered"
        result["note"] = "status=delivered (relatório detectado — verificação é do supervisor)"
    else:
        verdict, why = _supervisor_verdict(ledger, event, snippet)
        result["verdict"] = verdict
        result["note"] = verdict if verdict == "needs_supervisor" else "%s — %s" % (verdict, why)
        # RD-GUARD-CLOSE-STATE-01 (04/10): veredito awaiting_close (turn_done +
        # relatório + verify.json no cwd) grava a flag `awaitingClose: true` no
        # ledger — mesmo padrão atômico do needs_recovery usado para `recover`
        # — para o close do supervisor passar SEM token de ordem. Nunca clobber
        # estados terminais (closed/cancelled/failed); idempotente (re-watch
        # não re-marca nem duplica a trilha).
        if verdict == "awaiting_close" and not ledger.get("awaitingClose") \
                and ledger.get("status") not in ("closed", "cancelled", "failed"):
            ledger["awaitingClose"] = True
            ledger["awaitingCloseAt"] = mc._now()
            mc.save_ledger(ledger)
            mc.append_event(mission_id, pane_id, "awaiting_close_marked",
                            detail="ledger.awaitingClose=true — close de supervisor isento de token")
            result["awaitingCloseMarked"] = True
        # TRINITY-WIRE-01: advisor on ambiguous decision (JEV fail-open, 5s timeout)
        if verdict == "needs_supervisor" and _tw is not None:
            try:
                _tw.increment_role_call(ledger, "advisor", "nex-n2.5-pro")
                _tw.consult_advisor(
                    {"event": event, "snippet": snippet[:200], "missionId": mission_id},
                    mission_id,
                )
            except Exception:
                pass  # fail-open

    if ledger.get("status") in mc.ACTIVE_STATUSES | {"delivered", "closed"}:
        ledger["updatedAt"] = mc._now()
        mc.save_ledger(ledger)
    return result


# ---------------------------------------------------------------- WATCH-DETECTOR-FIX-01
# needs_supervisor dispara o supervisor (caro): só vale para missão dispatched, pane vivo,
# evento posterior à última intervenção, e sem sinal de conclusão em disco.
_UNWATCHED_STATUSES = mc.TERMINAL_STATUSES - {"delivered"}
_TURN_DONE_TS_RE = re.compile(r"· done (\d{1,2}):(\d{2}) (AM|PM)")
_REPORT_PREFIXES = ("relatorio", "relatório", "report")


def _turn_done_epoch(text: str, now: Optional[float] = None) -> Optional[float]:
    """Epoch do ÚLTIMO rodapé '· done H:MM AM|PM' (hora local do claude, granularidade
    de minuto). Hora no futuro = rodapé de ontem. None sem rodapé."""
    hits = _TURN_DONE_TS_RE.findall(text or "")
    if not hits:
        return None
    h, mi, ampm = hits[-1]
    hour = int(h) % 12 + (12 if ampm == "PM" else 0)
    now = time.time() if now is None else now
    lt = time.localtime(now)
    try:
        ts = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, int(mi), 0, 0, 0, -1))
    except (OverflowError, ValueError):
        return None
    if ts > now + 120:
        ts -= 86400
    return ts


def _final_report_on_disk(ledger: Dict[str, Any]) -> Optional[str]:
    """Relatório final da missão no disco: reportPath do ledger ou, no cwd,
    RELATORIO-*/relatorio-*/report-* .md com o missionId no nome."""
    rp = ledger.get("reportPath")
    if rp and os.path.isfile(str(rp)):
        return str(rp)
    cwd, mid = ledger.get("cwd"), str(ledger.get("missionId") or "").lower()
    if not cwd or not mid:
        return None
    try:
        names = os.listdir(str(cwd))
    except OSError:
        return None
    for name in sorted(names):
        low = name.lower()
        if low.startswith(_REPORT_PREFIXES) and low.endswith(".md") and mid in low:
            path = os.path.join(str(cwd), name)
            if os.path.isfile(path):
                return path
    return None


def _supervisor_verdict(ledger: Dict[str, Any], event: str, snippet: str) -> "tuple[str, str]":
    """Veredito do evento sem receita: closed | awaiting_close | stale | observed |
    needs_supervisor. Determinístico, zero LLM, nunca levanta."""
    status = ledger.get("status")
    mid = str(ledger.get("missionId") or "")
    if status in _UNWATCHED_STATUSES:
        return "closed", "missão %s" % status
    if event == "turn_done":
        report = _final_report_on_disk(ledger)
        cwd = ledger.get("cwd")
        if report and cwd and os.path.isfile(os.path.join(str(cwd), "verify.json")):
            return "awaiting_close", ("CONCLUÍDO: turn_done + relatório (%s) + verify.json no "
                                      "cwd — rode mission_close" % os.path.basename(report))
    ev_ts = _turn_done_epoch(snippet) if event == "turn_done" else None
    try:
        last_iv = float((mc._load_nudges().get(mid) or {}).get("ts") or 0)
    except (TypeError, ValueError):
        last_iv = 0.0
    # rodapé tem granularidade de minuto: só é stale se o minuto INTEIRO precede a intervenção
    if ev_ts is not None and last_iv and ev_ts + 60 <= last_iv:
        return "stale", ("evento %s (%s) anterior à última intervenção do supervisor (%s) — "
                         "não é AGORA" % (event, time.strftime("%H:%M", time.localtime(ev_ts)),
                                          time.strftime("%H:%M:%S", time.localtime(last_iv))))
    if status != "dispatched":
        return "observed", "status=%s — needs_supervisor só vale para dispatched" % status
    return "needs_supervisor", ""


def _scan_orphan_panes(panes: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """MISSION-NOTIFY-01: watcher MULTI-WORKSPACE — claude com turn_done num pane que
    NENHUM ledger conhece (missão despachada em w4/w5 fora do mission-ops, o gap real
    da watchdog-02) vira evento mission_orphan_turn_done no bus. Determinístico."""
    if panes is None:
        panes, perr = mc.pane_list()
        if perr is not None or panes is None:
            return []
    tracked = set()
    for l in mc.list_ledgers():
        if l.get("paneId"):
            tracked.add(l["paneId"])
    alerts = []
    for p in panes:
        pid = p.get("pane_id")
        if not pid or pid in tracked:
            continue
        out, _oerr = mc.read_output(pid, lines=40)
        if not out:
            continue
        if rc.classify_text(out) == "turn_done":
            res = nf.emit_event("mission_orphan_turn_done", str(pid),
                                "turn_done em pane fora do mission-ops: %s"
                                % str(p.get("title") or p.get("pane_id"))[:150],
                                transition="turn_done")
            alerts.append({"kind": "mission_orphan_turn_done", "detail": pid,
                           "emitted": bool(res.get("emitted"))})
        else:
            alerts.extend(nf.run_probes(text=out, mission_id=pid, pane_id=pid,
                                        skip_asset=True, skip_budget=True))
    return [a for a in alerts if a.get("emitted") or a.get("kind")]


def _headless_rerun(mission: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str], str]:
    """WORKER-HEADLESS-01: recipe headless_rerun — re-sobe o claude -p da missão
    (mesmo env/argv da fonte única, log continuado com marcador). Recusa tipada se o
    processo anterior ainda estiver vivo (sem respawn duplicado).
    Retorna (resultado, código_de_erro|None, detalhe)."""
    mission_id = str(mission.get("missionId") or "")
    pid = mission.get("headlessPid")
    if _pid_alive(pid):
        return {}, "HEADLESS_STILL_RUNNING", \
            f"processo anterior ainda vivo (pid={pid}) — encerre antes do rerun"
    cwd = str(mission.get("cwd") or "")
    pf = str(mission.get("promptFile") or "")
    if not cwd or not os.path.isdir(cwd) or not pf:
        return {}, "RECOVER_FAILED", "ledger sem cwd/promptFile válidos para o rerun"
    base_url = {"gpu": "http://127.0.0.1:8102",
                "openrouter": "http://127.0.0.1:8103",
                "openrouter-fallback": "http://127.0.0.1:8103"}.get(
        str(mission.get("engine") or ""))
    log_path = mc.headless_log_path(mission_id)
    try:
        with open(str(log_path), "a", encoding="utf-8") as f:
            f.write(f"\n== headless_rerun {mc._now()} ==\n")
    except OSError:
        pass  # log é best-effort no rerun
    env = mc.headless_env(cwd, base_url)
    argv = mc.headless_argv()
    proc, serr = _headless_do_spawn(mission_id, cwd, pf, str(log_path), env, argv)
    if serr or proc is None:
        return {}, "RECOVER_FAILED", f"respawn headless falhou: {serr}"
    mission["headlessPid"] = proc.pid
    mission["status"] = "dispatched"
    mission["dispatchedAt"] = mc._now()
    mission["updatedAt"] = mc._now()
    mc.save_ledger(mission)
    mc.append_event(mission_id, None, "headless_rerun",
                    detail=f"pid={proc.pid} log={log_path}")
    mc.append_event(mission_id, None, "prompt_sent", detail=f"{pf} (stdin no rerun headless)")
    return {"rerun": True, "pid": proc.pid, "headlessLog": str(log_path)}, None, ""


def handle_mission_recover(args: Dict[str, Any], **_kw) -> str:
    pane_id = str(args.get("paneId") or "").strip()
    pattern = str(args.get("pattern") or "").strip().lower()
    mission_id = str(args.get("missionId") or "").strip()
    mc.set_mission_sender(mission_id)  # SENDER-ID-01
    cwd = str(args.get("cwd") or "").strip() or None

    # WORKER-HEADLESS-01: headless_rerun não tem pane — missionId identifica a missão
    if not pane_id and not (pattern == "headless_rerun" and mission_id):
        return _err("INVALID_PANE_ID", "paneId é obrigatório (headless_rerun: missionId)")
    if not pattern:
        return _err("INVALID_PATTERN",
                    "pattern é obrigatório: interrupted|palette|transcript400|shell_fallback|"
                    "autocompact|ready_regex_error|mcp_prompt|headless_rerun")

    mission = mc.load_ledger(mission_id) if mission_id else None
    if mission is None:
        for l in mc.list_ledgers():
            if l.get("paneId") == pane_id:
                mission = l
                break

    # GUARD-SUPERVISOR-READONLY-01: recover pelo canal do supervisor exige
    # operatorOrder, salvo ledger marcado needs_recovery pelo watcher (fluxo
    # registrado). Recusa tipada ANTES de qualquer evento/mutação de pane.
    _gref = sg.assert_action_allowed("recover", args, ledger=mission, spool_path=_MISSION_SPOOL)
    if _gref:
        return _err(_gref["code"], _gref["detail"])

    # ---- WORKER-HEADLESS-01: recipe headless_rerun (sem pane; responde antes do
    # caminho de receitas de pane — missão sem ledger aqui seria recusa tipada)
    if pattern == "headless_rerun":
        if mission is None:
            return _err("MISSION_NOT_FOUND", f"nenhum ledger para {mission_id}")
        if not mission.get("headless"):
            return _err("NOT_HEADLESS",
                        "headless_rerun exige missão headless (ledger.headless=true) — "
                        "os demais padrões são de pane")
        r, err_code, err_detail = _headless_rerun(mission)
        if err_code:
            mc.append_event(mission_id, None, "recover_failed", detail=str(err_detail)[:200])
            return _err(err_code, err_detail)
        rec_notify = nf.mission_recovering(mission_id, "recover pattern=headless_rerun")
        r_ms = _ms("on_recover", mission, mc)
        return _j({"ok": True, "notifyRecovering": bool(rec_notify.get("emitted")),
                   **r, **({"supervisor": r_ms} if r_ms else {})})

    mc.append_event(mission.get("missionId") if mission else "?", pane_id,
                    f"recover_{pattern}", action="recipe_requested")
    r, err = rc.recover(pane_id, pattern, mission, cwd=cwd)
    if err:
        if "unknown" in (err or ""):
            mc.append_event(mission.get("missionId") if mission else "?", pane_id,
                            "needs_supervisor", detail=pattern)
            return _j({"ok": False, "needsSupervisor": True,
                       "reason": "padrão desconhecido — nenhuma ação tomada; supervisor decide"})
        mc.append_event(mission.get("missionId") if mission else "?", pane_id,
                        "recover_failed", detail=err or "")
        return _err("RECOVER_FAILED", err or "")
    # MISSION-NOTIFY-01: transição recovering — evento obrigatório no bus.
    rec_notify = nf.mission_recovering(mission.get("missionId") if mission else "?",
                                       "recover pattern=%s" % pattern)
    # MISSION-SUPERVISOR-01: recover → supervisor renasce rebindado (trilha herdada)
    r_ms = _ms("on_recover", mission, mc)
    return _j({"ok": True, "notifyRecovering": bool(rec_notify.get("emitted")),
               **r, **({"supervisor": r_ms} if r_ms else {})})



def _resolve_ledger_by(args: Dict[str, Any]) -> "tuple[Optional[Dict[str, Any]], Optional[str]]":
    """ENG-MCP-TOOLS-FIX-02: resolução missionId XOR paneId XOR fragment para verify/close.
    fragment = substring case-insensitive no missionId (mesma semântica declarada do
    mission_status); >=2 matches = AMBIGUOUS (nunca escolhe no escuro). Retorna
    (ledger, None) ou (None, json de erro)."""
    mission_id = str(args.get("missionId") or "").strip()
    pane_id = str(args.get("paneId") or "").strip()
    fragment = str(args.get("fragment") or "").strip()
    n_resolvers = sum(bool(x) for x in (mission_id, pane_id, fragment))
    if n_resolvers == 0:
        # contrato antigo preservado: sem nenhum resolvedor = id ausente/inválido
        return None, _err("INVALID_MISSION_ID", "informe missionId OU paneId OU fragment")
    if n_resolvers > 1:
        return None, _err("INVALID_INPUT",
                          "exatamente 1 resolvedor é obrigatório: missionId OU paneId OU fragment")
    if mission_id:
        if e := mc.validate_mission_id(mission_id):
            return None, _err("INVALID_MISSION_ID", e)
        ledger = mc.load_ledger(mission_id)
        if ledger is None:
            return None, _err("MISSION_NOT_FOUND", f"nenhum ledger para {mission_id}")
        return ledger, None
    if pane_id:
        for l in mc.list_ledgers():
            if l.get("paneId") == pane_id:
                return l, None
        return None, _err("MISSION_NOT_FOUND", f"nenhum ledger com paneId {pane_id}")
    frag = fragment.lower()
    hits = [l for l in mc.list_ledgers() if frag in str(l.get("missionId") or "").lower()]
    if len(hits) > 1:
        ids = sorted(str(l.get("missionId")) for l in hits)[:8]
        return None, _err("AMBIGUOUS", "fragment '%s' casa %d missões: %s"
                          % (fragment, len(hits), ", ".join(ids)))
    if not hits:
        return None, _err("MISSION_NOT_FOUND",
                          "nenhuma missão casa '%s' (substring case-insensitive)" % fragment)
    return hits[0], None


def _pane_agent_status(pane_id: str) -> "tuple[Optional[str], Optional[str]]":
    """ENG-MCP-TOOLS-FIX-02: (agent_status, None) do pane, ou (None, erro)."""
    pane, err = mc.pane_get(pane_id)
    if err or not pane:
        return None, err or "pane não listado"
    return pane.get("agent_status"), None


# PROOF-LINT-03 (adendo do operator, 01/10): o subprocess do deliver_verify no close tinha teto FIXO
# de 35s — watch-fp-01 fechou SEM BADGE com prova real verde de ~36s (P3 timeout 300). Teto agora =
# max(teto base, maior timeout cmd declarado no manifesto do cwd + 10s de margem).
# RD-PERF-VERIFY-01 (05/10): provas legítimas de ~99s estouravam os 35s (2 falhas + re-execução
# manual host-side em RD-EV-03/LEG-01/SEC-01) — teto base 35s -> 150s, também no mission_verify
# (default e clamp). Estouro segue fail-open honesto no close e runner_error retryable no verify.
DV_CLOSE_TIMEOUT_S = 150
DV_CLOSE_MARGIN_S = 10


def _flag(args: Dict[str, Any], key: str) -> bool:
    """Flag bool ou string 'true'/'1' (routers mandam string)."""
    v = args.get(key)
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "1"))


def _compact_flag(args: Dict[str, Any]) -> bool:
    """WATCHDOG-LANE2-01: compact=true (bool ou string 'true') é opt-in do router."""
    return _flag(args, "compact")


# MISSION-LIST-COMPACTO-01: visão de leitura de estado.
#   full    -> resposta completa (comportamento pré-01, byte a byte)
#   compact -> formato watchdog-lane2 (só não-closed + contadores), opt-in compact=true
#   chat    -> 1 linha por missão ativa + resumo das encerradas (~1-2KB)
# Precedência: full=true|verbose=true > compact=true > default do chamador. A TOOL registrada
# (chat) tem default "chat"; chamada Python direta (fast-router) mantém default "full".
# MISSION-LIST-COMPACT-DEFAULT-01: verbose=true é alias de full=true (opt-in da verbosidade).
CLOSED_LAST_N = 5
_PENDING_BY_STATUS = {"needs_recovery": "recover", "prompt_failed": "reentregar prompt",
                      "start_timeout": "start timeout", "interrupted": "interrompida",
                      "autocompact": "autocompact", "waiting_operator": "aguarda operator"}


def _view(args: Dict[str, Any], default: str) -> str:
    if _flag(args, "full") or _flag(args, "verbose"):
        return "full"
    if _flag(args, "compact"):
        return "compact"
    return default


def _fmt_age(sec: Optional[int]) -> str:
    if sec is None:
        return "?"
    for div, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if sec >= div:
            return "%d%s" % (sec // div, unit)
    return "%ds" % sec


def _chat_view(ledgers: List[Dict[str, Any]], skipped: List[str],
               liveness=None, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """1 linha por missão ativa: id | status | último evento + idade | [pane] | pendência.
    liveness(ledger) -> str só no mission_list (pane viva/MORTA/? — '?' se o herdr falhou,
    nunca 'MORTA' sem prova)."""
    now = time.time()
    counts: Dict[str, int] = {}
    active, ended, no_status = [], [], 0
    for l in ledgers:
        st = l.get("status")
        counts[str(st or "unknown")] = counts.get(str(st or "unknown"), 0) + 1
        if not st:
            no_status += 1
        elif st in mc.TERMINAL_STATUSES:
            ended.append(l)
        else:
            active.append(l)
    evs = mc.last_events(l.get("missionId") for l in active)
    lines = []
    for l in sorted(active, key=lambda x: str(x.get("missionId") or "")):
        mid = l.get("missionId")
        st = l.get("status")
        le = evs.get(mid)
        parts = [str(mid), str(st),
                 "%s há %s" % (le.get("event"), _fmt_age(mc.age_s(le.get("ts"), now)))
                 if le else "sem evento"]
        if liveness is not None:
            parts.append("pane " + liveness(l))
        pend = []
        if st in _PENDING_BY_STATUS:
            pend.append(_PENDING_BY_STATUS[st])
        if liveness is not None and parts[-1] == "pane MORTA":
            pend.append("pane morta")
        if l.get("consequence") is True:
            pend.append("close exige verify")
        parts.append("pend: " + (", ".join(pend) or "-"))
        lines.append(" | ".join(parts))
    ended.sort(key=lambda x: str(x.get("updatedAt") or ""), reverse=True)
    out: Dict[str, Any] = {
        "ok": True, "view": "compact", "total": len(ledgers), "counts": counts,
        "active": lines,
        "closed": {"count": len(ended),
                   "last": ["%s (%s)" % (l.get("missionId"), _fmt_age(mc.age_s(l.get("updatedAt"), now)))
                            for l in ended[:CLOSED_LAST_N]]},
        "hint": "full=true -> ledger completo",
    }
    if no_status:
        out["semStatus"] = no_status
    if skipped:
        out["skipped"] = len(skipped)
    if warnings:
        out["warnings"] = warnings
    return out


def handle_mission_status(args: Dict[str, Any], _view_default: str = "full", **_kw) -> str:
    mission_id = str(args.get("missionId") or "").strip()
    view = _view(args, _view_default)
    compact = view == "compact"
    if mission_id:
        if e := mc.validate_mission_id(mission_id):
            return _err("INVALID_MISSION_ID", e)
        ledgers = [l for l in [mc.load_ledger(mission_id)] if l]
        skipped: List[str] = []
    else:
        ledgers, skipped = mc.list_ledgers_report()
    if not ledgers:
        return _j({"ok": True, "missions": [], "note": "nenhuma missão registrada",
                   "skipped": skipped})
    if view == "chat" and not mission_id:
        return _j(_chat_view(ledgers, skipped))

    out = []
    for l in ledgers:
        if not l:
            continue
        le = mc.last_event(l.get("missionId") or "")
        out.append({
            "missionId": l.get("missionId"),
            "paneId": l.get("paneId"),
            "tabId": l.get("tabId"),
            "creation": l.get("creation"),
            "cwd": l.get("cwd"),
            "status": l.get("status"),
            "lastEventAt": (le or {}).get("ts"),
            "lastEvent": (le or {}).get("event"),
            "resumeSessionId": l.get("resumeSessionId"),
            "promptFile": l.get("promptFile"),
            "updatedAt": l.get("updatedAt"),
        })
    if compact and not mission_id:
        # MODO COMPACTO (watchdog-lane2-01): só não-closed + contadores — 35KB -> ~1KB.
        # Single-mission (missionId) ignora o filtro; default intacto.
        counts: Dict[str, int] = {}
        for l in ledgers:
            s = str(l.get("status") or "unknown")
            counts[s] = counts.get(s, 0) + 1
        return _j({"ok": True, "compact": True, "total": len(ledgers), "counts": counts,
                   "missions": [o for o in out if o.get("status") != "closed"],
                   "skipped": skipped})
    return _j({"ok": True, "missions": out, "skipped": skipped})


# ---------------------------------------------------------------- ESCOPO EXPANDIDO (MISSION-OPS-02)

def handle_mission_nudge(args: Dict[str, Any], **_kw) -> str:
    """MISSION-NUDGE-01: intervenção do supervisor — nudge atômico CHECK->SEND->VERIFY.
    Nunca fecha missão, nunca autoriza consequência, nunca envia em pane sem ledger."""
    mission_id = str(args.get("missionId") or "").strip()
    message = str(args.get("message") or "").strip()
    sender = str(args.get("sender") or mc.NUDGE_SENDER_DEFAULT).strip() or mc.NUDGE_SENDER_DEFAULT
    force = bool(args.get("force"))
    try:
        verify_s = int(args.get("verifySeconds") if args.get("verifySeconds") is not None
                       else mc.NUDGE_VERIFY_S_DEFAULT)
    except (TypeError, ValueError):
        return _err("INVALID_VERIFY_SECONDS", "verifySeconds deve ser inteiro")
    if verify_s < 0 or verify_s > 600:
        return _err("INVALID_VERIFY_SECONDS", "verifySeconds deve estar em 0..600")
    if not message:
        return _err("INVALID_MESSAGE", "message é obrigatório")
    if e := mc.validate_mission_id(mission_id):
        return _err("INVALID_MISSION_ID", e)
    # GUARD-SUPERVISOR-READONLY-01: nudge pelo canal do supervisor é ação de
    # curso que exige operatorOrder (ordem do operator: ação só com ordem
    # explícita). Sem isenção — nudge nunca é passo de automação registrada.
    _gref = sg.assert_action_allowed("nudge", args, spool_path=_MISSION_SPOOL)
    if _gref:
        return _err(_gref["code"], _gref["detail"])
    try:
        return _j(mc.nudge_mission(mission_id, message, sender=sender,
                                   force=force, verify_s=verify_s))
    except mc.HerdrError as exc:
        return _err("HERDR_FAILED", str(exc))


def _headless_read(ledger: Dict[str, Any], lines: int, max_bytes: Optional[int]) -> str:
    """WORKER-HEADLESS-01: mission_read de missão headless = tail do LOG do worker
    (mesma forma de resposta; pane não existe)."""
    log = str(ledger.get("headlessLog") or "")
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        return _err("HEADLESS_LOG_READ_FAILED", str(e))
    all_lines = raw.splitlines()
    text = "\n".join(all_lines[-lines:])
    truncated = False
    if max_bytes:
        b = text.encode("utf-8", errors="replace")
        if len(b) > max_bytes:
            text = b[-max_bytes:].decode("utf-8", errors="ignore")
            truncated = True
    return _j({"ok": True, "missionId": ledger.get("missionId"), "paneId": None,
               "source": "headless_log", "headlessLog": log,
               "headlessPid": ledger.get("headlessPid"), "status": ledger.get("status"),
               "lines": lines, "truncated": truncated, "text": text})


def handle_mission_read(args: Dict[str, Any], **_kw) -> str:
    mission_id = str(args.get("missionId") or "").strip()
    pane_id = str(args.get("paneId") or "").strip()
    if mission_id:
        if e := mc.validate_mission_id(mission_id):
            return _err("INVALID_MISSION_ID", e)
        ledger = mc.load_ledger(mission_id)
        if ledger is None:
            return _err("MISSION_NOT_FOUND", f"nenhum ledger para {mission_id}")
        pane_id = str(ledger.get("paneId") or "").strip()
        # WORKER-HEADLESS-01: missão headless não tem pane — lê o log do worker
        try:
            _hl_lines = min(max(int(args.get("lines") or 40), 1), 2000)
        except (TypeError, ValueError):
            return _err("INVALID_LINES", "lines deve ser inteiro")
        _hl_max = args.get("maxBytes")
        if _hl_max is not None:
            try:
                _hl_max = int(_hl_max)
            except (TypeError, ValueError):
                return _err("INVALID_MAX_BYTES", "maxBytes deve ser inteiro")
            if _hl_max <= 0:
                return _err("INVALID_MAX_BYTES", "maxBytes deve ser positivo")
        if ledger.get("headless"):
            return _headless_read(ledger, _hl_lines, _hl_max)
    if not pane_id:
        return _err("INVALID_PANE_ID", "paneId ou missionId é obrigatório")
    try:
        lines = int(args.get("lines") or 40)
    except (TypeError, ValueError):
        return _err("INVALID_LINES", "lines deve ser inteiro")
    lines = min(max(lines, 1), 2000)
    source = str(args.get("source") or "recent-unwrapped")
    if source not in _READ_SOURCES:
        return _err("INVALID_SOURCE", f"source deve ser um de: {', '.join(sorted(_READ_SOURCES))}")
    max_bytes = args.get("maxBytes")
    if max_bytes is not None:
        try:
            max_bytes = int(max_bytes)
        except (TypeError, ValueError):
            return _err("INVALID_MAX_BYTES", "maxBytes deve ser inteiro")
        if max_bytes <= 0:
            return _err("INVALID_MAX_BYTES", "maxBytes deve ser positivo")
    text, err = mc.read_output(pane_id, lines=lines, source=source)
    if err:
        return _err("HERDR_READ_FAILED", err or "read failed")
    truncated = False
    if max_bytes:
        raw = (text or "").encode("utf-8", errors="replace")
        if len(raw) > max_bytes:
            text = raw[-max_bytes:].decode("utf-8", errors="ignore")
            truncated = True
    return _j({"ok": True, "paneId": pane_id, "source": source, "lines": lines,
               "truncated": truncated, "text": text or ""})


def _agentes_em_voo_espelho() -> Dict[str, Any]:
    """GB-MIGRA-B-01: sessões de AGENTE NOSSO em voo via espelho.sh — fail-open.

    Carrega scripts/espelho_em_voo.py por caminho (env ESPELHO_EMV_PATH, ou o
    padrão /home/worker/harness-s2/scripts/espelho_em_voo.py). Qualquer falha
    (arquivo ausente, import quebrado) devolve lista vazia + ressalva em
    agentsNote — nunca derruba handle_mission_list."""
    fallback = {"agentes_em_voo": [], "agentsTotal": 0,
                "agentsNote": "espelho_indisponivel"}
    try:
        import glob as _glob
        import importlib.util
        import os as _os
        cand = _os.environ.get("ESPELHO_EMV_PATH", "").strip()
        paths = [cand] if cand else sorted(_glob.glob(
            "/home/worker/harness-s2/scripts/espelho_em_voo.py"))
        for p in paths:
            if not p or not _os.path.isfile(p):
                continue
            spec = importlib.util.spec_from_file_location("espelho_em_voo", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _coletar = getattr(mod, "coletar_sessoes", None)  # GB-MIGRA-B-02
            if _coletar is None:
                # espelho pré-02: só em voo, sem campo estado
                data = mod.coletar_em_voo()
            else:
                data = _coletar()
            return {"agentes_em_voo": data["sessoes"],
                    "agentsTotal": data["total"], "agentsNote": None}
        fallback["agentsNote"] = "espelho_em_voo nao encontrado"
        return fallback
    except Exception as e:
        fallback["agentsNote"] = "espelho_indisponivel: " + type(e).__name__
        return fallback


def handle_mission_list(args: Dict[str, Any], _view_default: str = "full", **_kw) -> str:
    warnings: List[str] = []
    view = _view(args, _view_default)
    compact = view == "compact"
    tabs, terr = mc.tab_list()
    if terr:
        warnings.append(f"tab list: {terr}")
        tabs = tabs or []
    panes, perr = mc.pane_list()
    if perr:
        warnings.append(f"pane list: {perr}")
        panes = panes or []
    pane_by_id = {p.get("pane_id"): p for p in panes if isinstance(p, dict) and p.get("pane_id")}
    tab_by_id = {t.get("tab_id"): t for t in tabs if isinstance(t, dict) and t.get("tab_id")}
    missions = []
    _emv = _agentes_em_voo_espelho()  # GB-MIGRA-B-01: agentes nossos em voo
    ledgers, skipped = mc.list_ledgers_report()
    if skipped:
        warnings.append("ignorados (não são mission-records): " + ", ".join(skipped))
    if view == "chat":
        def _live(l: Dict[str, Any]) -> str:
            p = pane_by_id.get(l.get("paneId"))
            if p:
                return "viva/%s" % (p.get("agent_status") or "?")
            return "?" if perr else "MORTA"
        return _j(_chat_view(ledgers, [], liveness=_live,
                             warnings=[w for w in warnings if not w.startswith("ignorados")]))
    for l in ledgers:
        pid = l.get("paneId")
        tid = l.get("tabId")
        p = pane_by_id.get(pid) or {}
        t = tab_by_id.get(tid) or {}
        missions.append({
            "missionId": l.get("missionId"),
            "paneId": pid,
            "tabId": tid,
            "creation": l.get("creation"),
            "headless": bool(l.get("headless")),
            "status": l.get("status"),
            "cwd": l.get("cwd"),
            "live": bool(p),
            "agentStatus": p.get("agent_status"),
            "paneCwd": p.get("cwd"),
            "tabLabel": t.get("label"),
            "updatedAt": l.get("updatedAt"),
        })
    if compact:
        # MODO COMPACTO (watchdog-lane2-01): só não-closed + contadores; default intacto.
        counts: Dict[str, int] = {}
        for l in ledgers:
            s = str(l.get("status") or "unknown")
            counts[s] = counts.get(s, 0) + 1
        return _j({"ok": True, "compact": True, "total": len(ledgers), "counts": counts,
                   "missions": [m for m in missions if m.get("status") != "closed"]})
    return _j({"ok": True, "missions": missions, "tabsTotal": len(tabs),
               "panesTotal": len(panes), "warnings": warnings,
               "agentes_em_voo": _emv["agentes_em_voo"],
               "agentsTotal": _emv["agentsTotal"],
               "agentsNote": _emv["agentsNote"]})


def _resolve_close_manifest(ledger: Dict[str, Any]):
    """CLOSE-VERIFY-PATH-01: o close usa a MESMA resolução de manifesto do verify
    (/opt/deliver-verify/verify.py resolve_manifest_with_owner — cwd-mission >
    cwd-legacy > search-specific em dirs legítimos com owner==mission). Fallback
    honesto para a convenção cwd-mission se o runner não puder ser importado.
    Retorna (path|None, how)."""
    mid = str((ledger or {}).get("missionId") or "")
    cwd = str((ledger or {}).get("cwd") or "")
    try:
        import sys
        if "/opt/deliver-verify" not in sys.path:
            sys.path.insert(0, "/opt/deliver-verify")
        from verify import resolve_manifest_with_owner
        # RD-LOOP-01: resolvedor do verify com ledger_dir do PRÓPRIO state dir — canônico
        # verify-<missionId>.json em mission-state; cwd só via migração read-once-and-move.
        path, how, _stale = resolve_manifest_with_owner(
            mid, ledger, ledger_dir=str(mc.STATE_DIR))
        return path, how
    except Exception:
        if mid and mc.STATE_DIR:
            return os.path.join(str(mc.STATE_DIR), "verify-%s.json" % mid), "fallback-state-dir"
        if mid and cwd:
            return os.path.join(cwd, "verify-%s.json" % mid), "fallback-cwd-mission"
        return None, None


def _recent_verify_pass(mission_id: str, max_age_s: int = 1800) -> bool:
    """CLOSE-VERIFY-PATH-01: relatório do verify (<missionId>.verify.json no state dir)
    com verdict=pass e idade <= 30 min é prova E2E do close. Ausente, corrompido ou
    velho = False (nunca prova fabricada)."""
    try:
        rep = Path(str(mc.STATE_DIR)) / ("%s.verify.json" % mission_id)
        if time.time() - rep.stat().st_mtime > max_age_s:
            return False
        with open(rep, encoding="utf-8") as f:
            return json.load(f).get("verdict") == "pass"
    except Exception:
        return False



def _dv_close_timeout(cwd: str, mission_id: str, extra_dirs: Any = None) -> int:
    # mesmos dirs que o runner resolve (RD-LOOP-01: canônico verify-<ID>.json no state dir
    # + cwd + extraDirs + parent do cwd: stale_manifest_ignored, caso watch-fp-01);
    # teto = máximo entre os candidatos (superestimar só alarga o teto).
    cwd = str(cwd or "")
    dirs = [str(mc.STATE_DIR), cwd] + [str(d) for d in (extra_dirs or []) if d]
    if cwd:
        dirs.append(os.path.dirname(os.path.normpath(cwd)))
    best = 0.0
    for path in [os.path.join(d, n) for d in dirs for n in ("verify-%s.json" % mission_id, "verify.json")]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for spec in (data.get("cmd") or []) if isinstance(data, dict) else []:
            try:
                best = max(best, float(spec.get("timeout") or 0))
            except (AttributeError, TypeError, ValueError):
                continue
    return int(max(DV_CLOSE_TIMEOUT_S, best + DV_CLOSE_MARGIN_S if best else 0))


# RD-CLOSE-TIMEOUT-01: reuso de verify fresco no close — o deliver-verify re-executa
# provas de ~99s a CADA fechamento (close levava 68-139s e estourava o wrapper de
# 90s com erro genérico). Antes de re-rodar o runner, aceita verify-<missionId>.json
# do CWD do ledger com mtime < 30 min, verdict "pass" e mission==missionId gravados
# no PRÓPRIO arquivo: badge verified_e2e SEM re-execução, com evidence do caminho +
# mtime no step. Arquivo ausente, vermelho, antigo (>30 min), missionId divergente
# ou kill switch env -> re-executa o runner como hoje (fallback 100% preservado).
DV_REUSE_ENV = "MISSION_CLOSE_VERIFY_REUSE"
DV_REUSE_MAX_AGE_S = 1800  # 30 min


def _reuse_disabled() -> bool:
    return os.environ.get(DV_REUSE_ENV, "").strip().lower() in ("0", "off", "false")


_CMD_SPEC_HASH_FIELDS = ("run", "expect_exit", "timeout", "cwd", "env")
_PATH_TOKEN_SUFFIXES = (".py", ".json", ".sh", ".md", ".txt", ".yaml", ".yml")


def _manifest_content_hash(manifest: Dict[str, Any], cwd: str) -> str:
    """RD-PERF-VERIFY-01: hash determinístico do CONTEÚDO provado pelo manifesto —
    specs cmd/file canônicos + conteúdo atual dos arquivos referenciados (paths das
    entradas file + tokens com cara de path nos runs cmd). Qualquer mudança nos specs
    ou nos arquivos provados muda o hash; manifesto sem arquivos mudando = hash estável."""
    parts: List[Any] = []
    cwd = os.path.normpath(str(cwd or "."))

    def _fhash(token: str) -> List[str]:
        p = token if os.path.isabs(token) else os.path.join(cwd, token)
        p = os.path.normpath(p)
        if os.path.isfile(p):
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return [p, "file", h.hexdigest()]
        return [p, "absent"]

    for spec in manifest.get("cmd") or []:
        spec = spec if isinstance(spec, dict) else {}
        parts.append(["cmd", {k: spec.get(k) for k in _CMD_SPEC_HASH_FIELDS
                              if spec.get(k) is not None}])
        proof_cwd = os.path.normpath(str(spec.get("cwd") or cwd))
        seen: set = set()
        # tokens com cara de path (extensão conhecida) -> hash do conteúdo atual;
        # flags (--x) e comandos sem extensão são ignorados.
        for tok in re.split(r"\s+", str(spec.get("run") or "")):
            tok = tok.strip("\"'")
            cand = tok[2:] if tok.startswith("--") else tok
            if not cand or cand in seen:
                continue
            seen.add(cand)
            if ("/" not in cand and not cand.endswith(_PATH_TOKEN_SUFFIXES)) \
                    or "=" in cand.split("/")[-1]:
                continue
            parts.append(_fhash(cand if os.path.isabs(cand)
                                else os.path.relpath(os.path.join(proof_cwd, cand))))
    for spec in manifest.get("file") or []:
        spec = spec if isinstance(spec, dict) else {}
        path = str(spec.get("path") or "")
        parts.append(["file", {k: spec.get(k) for k in spec if k != "path"}])
        if path:
            parts.append(_fhash(path if os.path.isabs(path)
                                else os.path.relpath(os.path.join(cwd, path))))
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _fresh_verify_manifest(ledger):
    """RD-CLOSE-TIMEOUT-01: evidência de reuso ({path, mtime, age_s}) quando
    verify-<missionId>.json é fresco (< 30 min), verdict=pass e owner==missionId;
    None em qualquer outro caso (fallback = re-executar runner).
    RD-LOOP-01: canônico primeiro — verify-<missionId>.json no STATE DIR; cwd do ledger
    só como fallback legado (o resolvedor do verify migra read-once-and-move).
    RD-PERF-VERIFY-01: com contentHash gravado no próprio manifesto, o reuso passa a
    ser POR CONTEÚDO — hash atual dos arquivos provados batendo = reuso independente
    de idade (touch falso não criava reuso real; 31 min reais re-executavam provas
    idênticas); hash divergente ou arquivo alterado -> re-executa. Manifesto SEM
    contentHash (legado) segue a regra de mtime de 30 min."""
    if _reuse_disabled():
        return None
    mid = str((ledger or {}).get("missionId") or "")
    cwd = str((ledger or {}).get("cwd") or "")
    if not mid or not cwd:
        return None
    # RD-LOOP-01: canônico no state dir; cwd legado como fallback
    _candidates = [os.path.join(str(mc.STATE_DIR), "verify-%s.json" % mid),
                   os.path.join(cwd, "verify-%s.json" % mid)]
    data = None
    path = None
    for path in _candidates:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            break
        except Exception:
            continue
    if data is None:
        return None
    try:
        if data.get("verdict") != "pass":
            return None
        if str(data.get("mission") or "").strip() != mid:
            return None
        st = os.stat(path)
        age = time.time() - st.st_mtime
        # contentHash presente: reuso por CONTEÚDO (independente de idade).
        stored_hash = str(data.get("contentHash") or "")
        if stored_hash:
            if _manifest_content_hash(data, cwd) != stored_hash:
                return None  # arquivos provados mudaram -> re-executa o runner
            return {"path": path, "mtime": int(st.st_mtime), "age_s": int(age),
                    "contentHash": stored_hash, "reuse_by": "content-hash"}
        # legado (sem contentHash): regra de mtime < 30 min
        if age >= DV_REUSE_MAX_AGE_S or age < 0:
            return None
        return {"path": path, "mtime": int(st.st_mtime), "age_s": int(age)}
    except Exception:
        return None


def _git_identity_env() -> Dict[str, str]:
    """Identidade determinística para rebase/merge mecânico (commits criados pelo
    gate, não por humano). Nunca sobrescreve config existente — só garante default."""
    env = dict(os.environ)
    env.setdefault("GIT_COMMITTER_NAME", "mission-ops")
    env.setdefault("GIT_COMMITTER_EMAIL", "mission-ops@hermes.local")
    env.setdefault("GIT_AUTHOR_NAME", "mission-ops")
    env.setdefault("GIT_AUTHOR_EMAIL", "mission-ops@hermes.local")
    return env


def _merge_gate(ledger: Dict[str, Any], steps: List[Dict[str, Any]],
                pane_id: str) -> Optional[str]:
    """RD-DISO-01 item 3: MERGE GATE no fecho — worktree → main. Integra só com
    (a) badge verified_e2e VERDE, (b) rebase fresco de main sem conflito, (c) o
    verify REAL (badge acima). Conflito → evento tipado merge_conflict — nunca
    auto-resolve, nunca force (abort devolve a árvore ao estado anterior).
    Retorna None = integrado (ou gate não se aplica); str = detalhe do conflito
    (caller REABRE a missão)."""
    wt, branch = str(ledger.get("worktreePath") or ""), str(ledger.get("worktreeBranch") or "")
    if not wt or not branch or not os.path.isdir(wt):
        return None
    if not (isinstance(ledger.get("verified_e2e"), dict)
            and ledger["verified_e2e"].get("verdict") == "pass"):
        steps.append({"step": "merge_gate", "ok": True, "verdict": "skipped",
                      "note": "sem badge verified_e2e verde — integração não executa "
                              "(worktree mantido; ship guard segue)"})
        return None
    # (b0) "só se commitado": worktree sujo não integra (close_commit_guard nudged o worker)
    ok, dirty = _git_out(wt, "status", "--porcelain")
    if ok and dirty.strip():
        steps.append({"step": "merge_gate", "ok": True, "verdict": "skipped_dirty",
                      "note": "worktree com entrega não-commitada — integração não executa"})
        return None
    ok, common = _git_out(wt, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not ok or not common:
        steps.append({"step": "merge_gate", "ok": True, "verdict": "skipped",
                      "note": "git-common-dir indisponível: %s" % common[:160]})
        return None
    maindir = os.path.dirname(common) if common.endswith(".git") else common
    main_branch = str(ledger.get("worktreeMainBranch") or "")
    if not main_branch:
        main_branch = "main" if _git_out(maindir, "rev-parse", "--verify", "--quiet", "main")[0] \
            else ("master" if _git_out(maindir, "rev-parse", "--verify", "--quiet", "master")[0] else "")
    if not main_branch:
        steps.append({"step": "merge_gate", "ok": True, "verdict": "skipped",
                      "note": "sem branch main/master no repo base"})
        return None
    ok, cur = _git_out(maindir, "branch", "--show-current")
    if ok and cur and cur != main_branch:
        steps.append({"step": "merge_gate", "ok": True, "verdict": "skipped",
                      "note": "checkout principal em '%s' (≠ %s) — integração manual "
                              "não automática" % (cur, main_branch)})
        return None
    env = _git_identity_env()
    # (b) rebase fresco de main — CONFLITO = abort + reabertura (nunca resolve)
    ok, out = _git_out(wt, "rebase", main_branch, timeout_s=120, env=env)
    if not ok:
        _git_out(wt, "rebase", "--abort", timeout_s=30, env=env)
        detail = ("rebase de %s conflitou (abortado — nada resolvido à força): %s"
                  % (main_branch, out[:220]))
        steps.append({"step": "merge_gate", "ok": False, "verdict": "merge_conflict",
                      "detail": detail})
        return detail
    # merge worker→main (nunca force; conflito de corrida → abort + reabertura)
    ok, out = _git_out(maindir, "merge", "--no-ff", "-m",
                       "merge %s (fecho %s)" % (branch, ledger.get("missionId")),
                       branch, timeout_s=120, env=env)
    if not ok:
        _git_out(maindir, "merge", "--abort", timeout_s=30, env=env)
        detail = "merge em %s conflitou (abortado): %s" % (main_branch, out[:220])
        steps.append({"step": "merge_gate", "ok": False, "verdict": "merge_conflict",
                      "detail": detail})
        return detail
    _ok_sha, sha = _git_out(maindir, "rev-parse", "--short", "HEAD")
    ledger["mergeState"] = {"merged": True, "branch": branch, "mainBranch": main_branch,
                            "mainDir": maindir, "commit": sha, "ts": mc._now()}
    steps.append({"step": "merge_gate", "ok": True, "verdict": "merged",
                  "commit": sha, "mainBranch": main_branch})
    mc.append_event(str(ledger["missionId"]), pane_id or None, "merge_done",
                    detail="branch %s integrada em %s (%s)" % (branch, main_branch, sha))
    vg.emit_bus_event("merge_done", str(ledger["missionId"]),
                      "branch %s integrada em %s (%s)" % (branch, main_branch, sha))
    return None


def _close_reopen(ledger: Dict[str, Any], pane_id: str, steps: List[Dict[str, Any]],
                  nudge: str, t_close: float) -> str:
    """RD-DISO-01: reabertura tipada do close (merge_conflict) — mesmo molde de
    deliver_verify_red: interrupted + nudge + evento/bus + notify. Nunca resolve
    à força; o worker (ou operator) decide a resolução."""
    ledger["status"] = "interrupted"
    ledger["updatedAt"] = mc._now()
    mc.save_ledger(ledger)
    steps.append({"step": "merge_gate_reopen", "ok": False})
    if pane_id and mc.pane_exists(pane_id) is True:
        nud_ok, nud_err = mc.deliver_prompt(pane_id, nudge)
        steps.append({"step": "merge_conflict_nudge", "ok": bool(nud_ok), "error": nud_err})
    mc.append_event(str(ledger["missionId"]), pane_id or None, "merge_conflict", detail=nudge)
    vg.emit_bus_event("merge_conflict", str(ledger["missionId"]), nudge)
    nf.mission_reopened(str(ledger["missionId"]), "merge_conflict: " + nudge)
    lat.timed("close_ms", str(ledger["missionId"]), t_close, detail="reopened merge_conflict")
    return _j({"ok": False, "missionId": ledger["missionId"], "paneId": pane_id or None,
               "reopenedByMergeConflict": True, "steps": steps})


def handle_mission_close(args: Dict[str, Any], **_kw) -> str:
    _t_close = time.time()  # RD-DISO-01 item 8: base do close_ms
    mc.set_mission_sender(str(args.get("missionId") or ""))  # SENDER-ID-01
    # ENG-MCP-TOOLS-FIX-02: flags novas do contrato (todas opt-in; ausentes = caminho
    # anterior 100% preservado).
    _dry = _flag(args, "dryRun")
    _expect_badge = _flag(args, "expectBadge")
    _keep_pane = _flag(args, "keepPane")
    _decision_note = str(args.get("decisionNote") or "").strip()
    _cancel = str(args.get("cancel") or "").strip().lower() in ("1", "true", "yes")
    _accept_unv = str(args.get("acceptUnverified") or "").strip()

    ledger, rerr = _resolve_ledger_by(args)
    if rerr is not None:
        return rerr
    pane_id = str(args.get("paneId") or (ledger or {}).get("paneId") or "").strip()
    mission_id = str((ledger or {}).get("missionId") or "")

    # GUARD-SUPERVISOR-READONLY-01: ação de supervisor fora de fluxo registrado
    # (ledger awaiting_close / verify verde / dryRun) exige operatorOrder — recusa
    # tipada ANTES do lock e de qualquer mutação (missão intocada). Canais
    # daemon/direct (daemons determinísticos, wrapper eng-mcp) nunca são supervisor.
    _gref = sg.assert_action_allowed("close", args, ledger=ledger, spool_path=_MISSION_SPOOL)
    if _gref:
        return _err(_gref["code"], _gref["detail"])

    # ENG-MCP-TOOLS-FIX-02 (lock de corrida): flock curto no lock-file da missão contra
    # dois chamadores simultâneos (o save_ledger já é atômico; o lock evita lost-update
    # entre os múltiplos save_ledger do fluxo). Non-blocking: 2º chamador recusa CLOSE_BUSY.
    _lock_fd: Optional[int] = None
    # RD-MOPS-01: try/finally em torno de TODO o corpo pós-lock — o fd do
    # close.lock é fechado em finally em TODOS os caminhos de saída (sucesso,
    # reabertura por deliver_verify/supervisor_gate, recusa tipada, exceção).
    # O flock fica preso ao processo chamador: fd que sobrevivesse ao turno
    # faria TODO re-close seguinte da missão falhar CLOSE_BUSY (Errno 11)
    # até o lock ser removido à mão (2 ocorrências reais em 04/10).
    try:
        if mission_id:
            try:
                import fcntl
                _lock_fd = os.open(os.path.join(mc.STATE_DIR, ".%s.close.lock" % mission_id),
                                   os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                if _lock_fd is not None:
                    os.close(_lock_fd); _lock_fd = None
                return _err("CLOSE_BUSY", "outro mission_close em andamento para %s (%s); "
                                           "repita em alguns segundos" % (mission_id, str(e)[:80]))
            # re-leitura DEPOIS do lock: idempotência honesta contra corrida
            ledger = mc.load_ledger(mission_id) or ledger
            if (ledger or {}).get("status") == "closed":
                os.close(_lock_fd); _lock_fd = None
                badge = (ledger.get("verified_e2e") or {}).get("verdict")
                return _j({"ok": True, "missionId": mission_id, "paneId": pane_id or None,
                           "idempotent": True, "badge": "verified_e2e" if badge else None,
                           "steps": [{"step": "idempotent_close", "ok": True,
                                      "note": "missão já closed — nada a fazer"}]})

        steps: List[Dict[str, Any]] = []

        # ENG-MCP-TOOLS-FIX-02 (WORKER_ACTIVE): turno vivo no pane = recusa ANTES de qualquer
        # mutação. Exceção normal: o /exit CONFIRMADO do próprio close — o gate tenta o /exit
        # cedo e só segue se o turno parou; /exit não confirmado = WORKER_ACTIVE honesto.
        if not _dry and pane_id and mc.pane_exists(pane_id) is True:
            astat, aerr = _pane_agent_status(pane_id)
            if not aerr and astat == "working":
                name, _fe = mc.foreground_agent_name(pane_id)
                if name == "claude" and not mc.run_command(pane_id, "/exit"):
                    _stopped = False
                    for _ in range(5):
                        time.sleep(1.0)
                        n2, _e2 = mc.foreground_agent_name(pane_id)
                        if n2 != "claude":
                            _stopped = True
                            break
                    if _stopped:
                        steps.append({"step": "worker_gate", "ok": True,
                                      "note": "turno vivo — /exit do close confirmado (exceção normal)"})
                    else:
                        if _lock_fd is not None:
                            os.close(_lock_fd); _lock_fd = None
                        return _err("WORKER_ACTIVE",
                                    "worker com turno vivo e /exit não confirmado — feche quando o "
                                    "pane estiver idle (evita corrida de escrita no projeto)")
                else:
                    if _lock_fd is not None:
                        os.close(_lock_fd); _lock_fd = None
                    return _err("WORKER_ACTIVE",
                                "worker com turno vivo no pane (%s=%s) — close recusado; o /exit "
                                "do close só excepciona quando o foreground é claude e para"
                                % (pane_id, astat))

        # ENG-MCP-TOOLS-FIX-02 (dryRun): executa pre_close + deliver-verify em modo espelho
        # (zero mutação: sem dv_report, sem save_ledger, sem nudge/spool/notify/pane) e devolve
        # o PLANO que o close real executaria. Recusa do pre_close É o plano.
        if _dry:
            if refusal := _ms("pre_close", ledger, args, mc, pane_id):
                return _j(refusal)
            steps.append({"step": "pre_close", "ok": True})
            # RD-PERF-VERIFY-01: o dryRun passa a resolver o manifesto pelo MESMO
            # resolvedor do close real (_resolve_close_manifest — CLOSE-VERIFY-PATH-01);
            # antes só reconhecia verify.json e ignorava verify-<missionId>.json.
            dv_manifest_dry, _dv_how_dry = _resolve_close_manifest(ledger)
            has_manifest = bool(dv_manifest_dry) and os.path.isfile(str(dv_manifest_dry))
            # RD-CLOSE-TIMEOUT-01: o dryRun espelha o veredito que o close real
            # executaria — reuso de verify fresco ANTES do runner (zero mutação).
            _reuse = _fresh_verify_manifest(ledger)
            dv: Dict[str, Any] = {"manifest": dv_manifest_dry if has_manifest else None}
            if _cancel:
                dv["verdict"] = "skipped-cancel"
            elif _reuse is not None:
                dv["verdict"] = "pass"
                dv["resolved_by"] = "reuse-fresh"
                dv["evidence"] = _reuse
            elif not has_manifest:
                dv["verdict"] = "no-manifest"
            else:
                try:
                    proc = subprocess.run(
                        ["python3", "/opt/deliver-verify/verify.py", "--mission", mission_id,
                         "--ledger-dir", str(mc.STATE_DIR)],
                        capture_output=True,
                        timeout=_dv_close_timeout(str(ledger["cwd"]), mission_id,
                                                  ledger.get("extraDirs")))  # PROOF-LINT-03
                    out = (proc.stdout or b"")[:8192].decode("utf-8", "replace")
                    real_failed: List[Dict[str, Any]] = []
                    try:
                        real_failed = [c for c in json.loads(out).get("checks", [])
                                       if not c.get("ok")
                                       and c.get("id") not in ("manifest-parse", "inference")]
                    except Exception:
                        pass
                    if proc.returncode == 0:
                        dv["verdict"] = "pass"
                    elif proc.returncode == 2 and real_failed:
                        dv["verdict"] = "fail"
                        dv["failed"] = [c.get("id") for c in real_failed[:5]]
                    else:
                        dv["verdict"] = "fail-open"
                except Exception as e:
                    dv["verdict"] = "fail-open"
                    dv["note"] = str(e)[:120]
            steps.append({"step": "deliver_verify", "ok": True, **dv})
            # preview do consequence guard (mc.ledger_consequence é leitura pura)
            warnings: List[str] = []
            if dv.get("verdict") == "fail":
                warnings.append("close real REABRIRIA (deliver_verify_red): provas reais "
                                "falharam %s" % ", ".join(dv.get("failed") or []))
            elif not _cancel and not (ledger.get("verified_e2e") or dv.get("verdict") == "pass"):
                cq = mc.ledger_consequence(ledger)
                if cq["consequence"]:
                    declared = cq["source"] in ("dispatch", "prompt")
                    if declared and not has_manifest and not _accept_unv:
                        warnings.append("close real REABRIRIA (verify_required): consequência "
                                        "declarada sem verify.json e sem acceptUnverified")
                    else:
                        warnings.append("close real fecharia sem badge (closed_unverified_consequence)")
            if _expect_badge and dv.get("verdict") != "pass" and not ledger.get("verified_e2e"):
                warnings.append("expectBadge=true: close real recusaria com BADGE_REQUIRED "
                                "(verdict=%s)" % dv.get("verdict"))
            if _keep_pane:
                warnings.append("keepPane=true: aba preservada")
            planned = [p for p in ("deliver_verify", "consequence_guard", "operator_channel_proof",
                                   "claude_exit", "tab_close" if not _keep_pane else "tab_close(keepPane)",
                                   "worktree_remove" if ledger.get("worktreeWorkspaceId") else None) if p]
            if _lock_fd is not None:
                os.close(_lock_fd); _lock_fd = None
            return _j({"ok": True, "dryRun": True, "missionId": mission_id,
                       "paneId": pane_id or None, "ledgerStatus": ledger.get("status"),
                       "deliverVerify": dv, "plannedSteps": planned,
                       "warnings": warnings, "steps": steps})

        # MISSION-SUPERVISOR-01: PRÉ-CLOSE GATE — o supervisor local roda as provas do
        # contrato e RECUSA o close se vermelho (a decisão final continua do Hermes).
        # ENG-MCP-TOOLS-FIX-02: movido para depois do gate de worker (turno vivo recusa
        # antes de gastar as provas do contrato).
        if refusal := _ms("pre_close", ledger, args, mc, pane_id):
            if _lock_fd is not None:
                os.close(_lock_fd); _lock_fd = None
            return _j(refusal)

        # ENG-MCP-TOOLS-FIX-02 (decisionNote): cancelamento governado nunca é mudo —
        # aceita acceptUnverified OU decisionNote como motivo (trilha vai pro ledger + bus).
        if _cancel and not (_accept_unv or _decision_note):
            if _lock_fd is not None:
                os.close(_lock_fd); _lock_fd = None
            return _err("CANCEL_REASON_REQUIRED",
                        "cancel=true exige acceptUnverified ou decisionNote (motivo não vazio)")

        # ---- passo 0: DELIVER-VERIFY-01 — gate de verificação ponta a ponta no fechamento.
        # Se a missão declara verify.json no seu cwd, roda o runner determinístico ANTES de
        # valer "entregue" (lições: "pronto só é pronto quando funciona na mão de quem pediu";
        # "a op aplicou" ≠ "o usuário VÊ"). VERDE grava badge verified_e2e no ledger e segue o
        # fechamento normal; VERMELHO com provas reais NÃO fecha — reabre (status interrupted +
        # nudge no pane + evento deliver_verify_red no spool para o supervisor). Falha do
        # PRÓPRIO runner (manifest-parse / crash / timeout) é fail-open: fecha sem badge.
        # Sem verify.json: caminho 100% inalterado (gate é a existência do arquivo).
        # CANCEL governado (28/09, ordem do operator): acceptUnverified + cancel=true pula o
        # deliver-verify — cancelamento não é claim de entrega; reabrir por prova vermelha
        # de um runner alheio seria falso-positivo. Evento mission_cancelled no bus.
        _cancel = str(args.get("cancel") or "").strip().lower() in ("1", "true", "yes")
        _accept_unv = str(args.get("acceptUnverified") or "").strip()
        if _cancel and _accept_unv:
            steps.append({"step": "deliver_verify", "ok": True, "verdict": "skipped-cancel",
                          "note": "cancel=true — deliver-verify não se aplica a cancelamento"})
        elif ledger and ledger.get("cwd") and ledger.get("missionId"):
            # CLOSE-VERIFY-PATH-01: mesma resolução de manifesto do verify (resolve_manifest_with_owner)
            dv_manifest, dv_how = _resolve_close_manifest(ledger)
            # RD-CLOSE-TIMEOUT-01: verify fresco (<30min) com verdict=pass e owner==missionId
            # no próprio arquivo -> badge verified_e2e SEM re-executar o runner (close <30s).
            # Kill switch MISSION_CLOSE_VERIFY_REUSE; qualquer outro caso -> caminho antigo.
            _reuse = _fresh_verify_manifest(ledger)
            if _reuse is not None:
                steps.append({"step": "deliver_verify", "ok": True, "verdict": "pass",
                              "resolved_by": "reuse-fresh", "evidence": _reuse})
                ledger["verified_e2e"] = {"verdict": "pass", "ts": mc._now(),
                                          "report": _reuse["path"], "reuse": True}
                ledger["updatedAt"] = mc._now()
                mc.save_ledger(ledger)
            elif dv_manifest and os.path.isfile(dv_manifest):
                dv_report = str(Path(str(mc.STATE_DIR)) / ("%s.verify.json" % ledger["missionId"]))
                try:
                    dv_timeout = _dv_close_timeout(str(ledger["cwd"]), ledger["missionId"],
                                                   ledger.get("extraDirs"))  # PROOF-LINT-03
                    _t_verify = time.time()
                    proc = subprocess.run(
                        ["python3", "/opt/deliver-verify/verify.py", "--mission",
                         str(ledger["missionId"]),
                         "--ledger-dir", str(mc.STATE_DIR)],
                        capture_output=True,
                        timeout=dv_timeout)
                    # RD-DISO-01 item 8: latência da prova do fecho (verify real)
                    lat.timed("verify_ms", str(ledger["missionId"]), _t_verify,
                              detail="exit %s" % proc.returncode)
                    out = (proc.stdout or b"")[:8192].decode("utf-8", "replace")
                    try:
                        with open(dv_report, "w", encoding="utf-8") as f:
                            f.write(out)
                    except Exception:
                        pass
                    failed: List[Dict[str, Any]] = []
                    try:
                        failed = [c for c in json.loads(out).get("checks", []) if not c.get("ok")]
                    except Exception:
                        failed = []
                    # manifest-parse/inference = erro de USO do runner, não prova vermelha
                    real_failed = [c for c in failed
                                   if c.get("id") not in ("manifest-parse", "inference")]
                    if proc.returncode == 0:
                        steps.append({"step": "deliver_verify", "ok": True, "verdict": "pass",
                                      "resolved_by": dv_how})
                        ledger["verified_e2e"] = {"verdict": "pass", "ts": mc._now(),
                                                  "report": dv_report}
                        ledger["updatedAt"] = mc._now()
                        mc.save_ledger(ledger)
                    elif proc.returncode == 2 and real_failed:
                        parts = ["%s falhou — %s" % (c.get("id"), (c.get("error") or "sem detalhe"))[:180]
                                 for c in real_failed[:3]]
                        nudge = ("REABERTA POR DELIVER-VERIFY: " + "; ".join(parts))[:900]
                        # status ANTES do evento: pane2mission ignora closed; interrupted reabre
                        ledger["status"] = "interrupted"
                        ledger["updatedAt"] = mc._now()
                        mc.save_ledger(ledger)
                        steps.append({"step": "deliver_verify", "ok": False, "verdict": "fail",
                                      "failed": [c.get("id") for c in real_failed[:5]],
                                      "report": dv_report})
                        if pane_id and mc.pane_exists(pane_id) is True:
                            # DELIVER-NUDGE-FIX-01: deliver_prompt retorna (bool, err) —
                            # walrus tratava (True, None) como truthy -> ok:False
                            # error:[true,null] silencioso. Desempacotar a tupla.
                            nud_ok, nud_err = mc.deliver_prompt(pane_id, nudge)
                            if not nud_ok:
                                steps.append({"step": "deliver_verify_nudge", "ok": False,
                                              "error": nud_err or "prompt delivery failed"})
                            else:
                                steps.append({"step": "deliver_verify_nudge", "ok": True})
                        else:
                            steps.append({"step": "deliver_verify_nudge", "ok": True,
                                          "note": "pane inexistente — só ledger + bus"})
                        sperr = _spool_deliver_verify_red(ledger, pane_id, nudge)
                        steps.append({"step": "deliver_verify_bus", "ok": not sperr,
                                      "error": sperr})
                        mc.append_event(ledger["missionId"], pane_id or None,
                                        "deliver_verify_red", detail=nudge)
                        # MISSION-NOTIFY-01: transição reopened — evento obrigatório no bus.
                        reopen_notify = nf.mission_reopened(ledger["missionId"],
                                                            "deliver_verify_red: " + nudge)
                        steps.append({"step": "notify_mission_reopened",
                                      "ok": bool(reopen_notify.get("ok")),
                                      "emitted": bool(reopen_notify.get("emitted")),
                                      "error": reopen_notify.get("error")})
                        return _j({"ok": False, "missionId": ledger.get("missionId"),
                                   "paneId": pane_id or None, "reopenedByDeliverVerify": True,
                                   "steps": steps})
                    else:
                        steps.append({"step": "deliver_verify", "ok": True, "verdict": "fail-open",
                                      "note": "verify exit %s sem provas reais parseáveis — "
                                              "fechando sem badge" % proc.returncode})
                except subprocess.TimeoutExpired:
                    steps.append({"step": "deliver_verify", "ok": True, "verdict": "fail-open",
                                  "note": "verify timeout %ds — fechando sem badge" % dv_timeout})
                except Exception as e:
                    steps.append({"step": "deliver_verify", "ok": True, "verdict": "fail-open",
                                  "note": "verify indisponível (%s) — fechando sem badge"
                                          % str(e)[:120]})

        # ---- passo 0.3: CLOSE-COMMIT-01 — guard de entrega não-commitada (classe recorrente:
        # MISSION-MANIFEST-PATCH-01-R2 fechou PASS com src/test/RELATORIO untracked; o close
        # verificava o relatório, mas nunca o git). Antes de valer "entregue": se o cwd do
        # ledger é um repo git com dirt de ENTREGA (deploy paths src/test/tests/scripts/
        # package.json, arquivos novos do componente untracked, RELATORIO* — session files
        # verify*/.claude/.glgpd são ignorados pelo classificador), o close BLOQUEIA o badge
        # verified_e2e, grava closeWarning acionável (worker: commit os artefatos antes do
        # PARE, ou recover-<id>-fim) e faz auto-nudge ao worker. Fail-closed honesto:
        # o supervisor NUNCA auto-commita. Sem repo git no cwd: caminho inalterado.
        # Cancelamento governado (acceptUnverified+cancel) pula o guard, como pula o deliver-verify.
        if ledger and ledger.get("cwd") and not (_cancel and _accept_unv):
            try:
                cg_report = cg.classify_worktree(str(ledger["cwd"]))
            except Exception as e:
                cg_report = None
                steps.append({"step": "close_commit_guard", "ok": True, "verdict": "fail-open",
                              "note": "guard indisponível (%s) — fechando sem checagem de git"
                                      % str(e)[:120]})
            if cg_report is not None:
                dirty = cg_report.get("deliveryPaths") or []
                if dirty:
                    shown = dirty[:8]
                    tail = " (+%d)" % (len(dirty) - 8) if len(dirty) > 8 else ""
                    warning = ('entrega não-commitada em %s%s — worker: commit os artefatos '
                               'antes do PARE (git add/commit no cwd da missão) ou abre '
                               'recover-%s-fim' % (", ".join(shown), tail,
                                                   ledger["missionId"]))[:600]
                    badge_blocked = False
                    if ledger.get("verified_e2e"):
                        ledger.pop("verified_e2e", None)  # bloqueia o badge (fail-closed)
                        badge_blocked = True
                    ledger["closeWarning"] = warning
                    ledger["updatedAt"] = mc._now()
                    mc.save_ledger(ledger)
                    steps.append({"step": "close_commit_guard", "ok": False,
                                  "verdict": "uncommitted_delivery",
                                  "badgeBlocked": badge_blocked,
                                  "paths": dirty[:10]})
                    # CLOSE auto-nudge ao worker (antes do /exit; pane inexistente = só ledger).
                    nudge = ("CLOSE-COMMIT GUARD: %s" % warning)[:900]
                    if pane_id and mc.pane_exists(pane_id) is True:
                        nud_ok, nud_err = mc.deliver_prompt(pane_id, nudge)
                        steps.append({"step": "close_commit_guard_nudge", "ok": bool(nud_ok),
                                      "error": nud_err})
                    else:
                        steps.append({"step": "close_commit_guard_nudge", "ok": True,
                                      "note": "pane inexistente — só ledger + evento"})
                    mc.append_event(ledger["missionId"], pane_id or None,
                                    "close_commit_dirty", detail=warning)
                elif cg_report.get("repo"):
                    steps.append({"step": "close_commit_guard", "ok": True, "verdict": "clean",
                                  "head": cg_report.get("head")})
                else:
                    steps.append({"step": "close_commit_guard", "ok": True, "verdict": "not-git",
                                  "note": "cwd do ledger não é repo git — guard não se aplica"})
                # ---- passo 0.3b: CLOSE-SHIP-VISIBILITY-01 — guard "merged?". Segunda classe
                # de perda de entregável: SNAPSHOT-WRAP-01 fechou PASS com o entregável na
                # branch do worktree SEM merge em main e ninguém percebeu por horas. Branch
                # não-mergeada em main -> veredito unshipped_delivery (além do
                # uncommitted_delivery existente). NÃO bloqueia o close (badge segue): grava
                # shipState {merged, branch, headSha16, ...} no ledger + evento
                # unshipped_delivery, e auto-despacha a missão SHIP-<alvo>-01 (caminho
                # governado, idempotente — ship consciente de voos fica no close_ship).
                if cg_report.get("repo"):
                    try:
                        ship = cg.classify_ship(str(ledger["cwd"]), ledger)
                    except Exception as e:
                        ship = None
                        steps.append({"step": "ship_guard", "ok": True, "verdict": "fail-open",
                                      "note": "classify_ship indisponível (%s)" % str(e)[:120]})
                    if ship and ship.get("applicable"):
                        ledger["shipState"] = {"merged": False, "branch": ship.get("branch"),
                                               "headSha16": ship.get("headSha16"),
                                               "mainBranch": ship.get("mainBranch"),
                                               "mainSha16": ship.get("mainSha16"),
                                               "diverged": ship.get("diverged")}
                        ledger["updatedAt"] = mc._now()
                        mc.save_ledger(ledger)
                        detail = ("branch %s (head %s) não-mergeada em %s — shipState gravado"
                                  % (ship.get("branch"), ship.get("headSha16"),
                                     ship.get("mainBranch")))
                        mc.append_event(ledger["missionId"], pane_id or None,
                                        "unshipped_delivery", detail=detail)
                        vg.emit_bus_event("unshipped_delivery", ledger["missionId"], detail)
                        steps.append({"step": "ship_guard", "ok": True,
                                      "verdict": "unshipped_delivery",
                                      "branch": ship.get("branch"),
                                      "headSha16": ship.get("headSha16"),
                                      "mainBranch": ship.get("mainBranch"),
                                      "diverged": ship.get("diverged")})
                        # auto-despacho da SHIP-<alvo>-01 (idempotente; janela de release
                        # ocupada -> awaiting_ship_window; nunca derruba o close)
                        try:
                            ship_res = cs.dispatch_ship(str(ledger["missionId"]),
                                                        str(ledger["cwd"]), ship)
                        except Exception as e:
                            ship_res = {"verdict": "dispatch_failed", "error": str(e)[:200]}
                        steps.append({"step": "ship_dispatch", "ok": True, **ship_res})
                    elif ship and ship.get("repo"):
                        steps.append({"step": "ship_guard", "ok": True,
                                      "verdict": ("merged" if ship.get("merged")
                                                  else "not-applicable"),
                                      "branch": ship.get("branch"),
                                      "reason": ship.get("reason")})

        # ---- passo 0.1: ENG-MCP-TOOLS-FIX-02 (expectBadge) — fail-closed opt-in para
        # missão crítica: se o fechamento terminaria SEM badge verified_e2e (no-manifest,
        # fail-open do runner, cancelamento), NÃO fecha — retorno BADGE_REQUIRED sem mutar.
        # Prova vermelha real continua seguindo o caminho próprio (reabre, acima).
        if _expect_badge and not ((ledger or {}).get("verified_e2e")):
            if _lock_fd is not None:
                os.close(_lock_fd); _lock_fd = None
            dv_steps = [s for s in steps if s.get("step") == "deliver_verify"]
            dverdict = (dv_steps[-1].get("verdict") if dv_steps else None) or "no-manifest"
            return _j({"ok": False, "missionId": mission_id, "paneId": pane_id or None,
                       "error": "BADGE_REQUIRED",
                       "reason": "expectBadge=true e fechamento terminaria sem badge "
                                 "verified_e2e (deliver_verify verdict=%s)" % dverdict,
                       "steps": steps})

        # ---- passo 0.2: CLOSE-VERIFY-GUARD-01 — guarda de consequência. Missão com escopo de
        # infra de produção (systemd/.service/opt/deploy/produção/restart) que chega aqui SEM
        # badge verified_e2e não fecha em silêncio:
        #   (b) escopo DECLARADO (flag do dispatch ou `consequence: true` no prompt) e sem
        #       verify.json no cwd → recusa e reabre (interrupted + nudge + evento
        #       verify_required no bus), no mesmo molde de deliver_verify_red/operator_channel_red.
        #       Escape auditável: acceptUnverified="<motivo>" rebaixa para (a).
        #   (a) escopo só HEURÍSTICO (regex tem falso-positivo), runner fail-open ou override
        #       → fecha, mas com evento closed_unverified_consequence + warning na resposta.
        # Missão sem escopo de consequência: caminho inalterado (verify.json segue opcional).
        unverified_consequence: Optional[str] = None
        if ledger and ledger.get("missionId") and not ledger.get("verified_e2e"):
            cq = mc.ledger_consequence(ledger)
            if cq["consequence"]:
                # CLOSE-VERIFY-PATH-01: has_manifest pela MESMA resolução do verify (qualquer
                # resolução válida: cwd-mission/cwd-legacy/search-specific), não só verify.json.
                _cq_manifest, _cq_how = _resolve_close_manifest(ledger)
                has_manifest = bool(_cq_manifest) and os.path.isfile(_cq_manifest)
                accept = str(args.get("acceptUnverified") or "").strip()
                declared = cq["source"] in ("dispatch", "prompt")
                # CLOSE-VERIFY-PATH-01: verdict=pass do verify RECENTE (< 30 min) é prova E2E —
                # vale tanto para não reabrir quanto para não marcar unverified_consequence
                # (ex.: gate falhou aberto agora por timeout, mas o verify passou minutos antes).
                recent_pass = _recent_verify_pass(str(ledger["missionId"]))
                if declared and not has_manifest and not accept and not recent_pass:
                    nudge = ("VERIFY_REQUIRED: missão de consequência (escopo %s) não fecha sem "
                             "prova — crie verify.json no cwd (%s) com checks determinísticos do "
                             "que foi alterado e chame mission_close de novo"
                             % (cq["source"], ledger.get("cwd")))[:900]
                    ledger["status"] = "interrupted"
                    ledger["updatedAt"] = mc._now()
                    mc.save_ledger(ledger)
                    steps.append({"step": "consequence_guard", "ok": False,
                                  "verdict": "verify_required", "source": cq["source"],
                                  "matches": cq["matches"]})
                    if pane_id and mc.pane_exists(pane_id) is True:
                        nud_ok, nud_err = mc.deliver_prompt(pane_id, nudge)
                        steps.append({"step": "consequence_guard_nudge", "ok": bool(nud_ok),
                                      "error": nud_err})
                    mc.append_event(ledger["missionId"], pane_id or None, "verify_required",
                                    detail=nudge)
                    vg.emit_bus_event("verify_required", ledger["missionId"], nudge)
                    # MISSION-NOTIFY-01: transição reopened — evento obrigatório no bus.
                    nf.mission_reopened(ledger["missionId"], "verify_required: " + nudge)
                    return _j({"ok": False, "missionId": ledger["missionId"],
                               "paneId": pane_id or None, "reopenedByVerifyRequired": True,
                               "steps": steps})
                if recent_pass:
                    steps.append({"step": "consequence_guard", "ok": True,
                                  "verdict": "proof_recent_verify_pass",
                                  "source": cq["source"], "matches": cq["matches"],
                                  "resolved_by": _cq_how})
                else:
                    why = ("override acceptUnverified: %s" % accept[:200] if declared and accept
                           else "verify.json presente mas runner fail-open" if has_manifest
                           else "sem verify.json no cwd")
                    unverified_consequence = ("FECHADA SEM VERIFICAÇÃO E2E em missão de consequência "
                                              "(escopo %s: %s) — %s"
                                              % (cq["source"], ", ".join(cq["matches"][:5]) or "-",
                                                 why))[:600]
                    ledger["consequenceWarning"] = unverified_consequence
                    steps.append({"step": "consequence_guard", "ok": True,
                                  "verdict": "closed_unverified_consequence",
                                  "source": cq["source"], "matches": cq["matches"],
                                  "warning": unverified_consequence})

        # ---- passo 0.3: OBEY-HARD-GATE-01 (T1) — O1 vira GATE MECÂNICO: close de
        # missão com veredito/fecho executável (awaiting_close/awaitingClose/verde)
        # SEM evento relatorio_integra_delivered ABORTA antes de gravar status
        # closed — a regra que dependia de disciplina (warning violates-obligation-O1)
        # agora amarra na ferramenta. Missão volta/mantém awaiting_close + evento no
        # bus + trilha reopened (mesma mecânica do consequence_guard); a recusa grava
        # chatDeliveryPending no ledger — o mission_report_ack seguinte é o fluxo
        # registrado do próprio gate (isento de token no guard do supervisor).
        # Não aborta: cancelamento governado, chatDeliverableExempt (isenção do
        # despachante operator), fecho fantasma/FAIL de nascedouro (fora do gatilho;
        # o vigia T4 OBEY_GATE_LEAK cobra o ack). Fail-open: erro do gate nunca
        # derruba o close (recusa só quando o gate decide recusar).
        if ledger and ledger.get("missionId") and not _dry:
            try:
                _gate = sg.obey_chat_gate(ledger, cancel=_cancel)
            except Exception as _gate_exc:
                _gate = None
                steps.append({"step": "obey_chat_gate", "ok": True, "verdict": "fail-open",
                              "error": str(_gate_exc)[:160]})
            if isinstance(_gate, dict) and _gate.get("code") == "CHAT_DELIVERY_MISSING":
                _first = not ledger.get("chatDeliveryPending")  # dedupe de evento/nudge
                ledger["status"] = "awaiting_close"
                ledger["chatDeliveryPending"] = {"at": mc._now(), "code": "CHAT_DELIVERY_MISSING"}
                ledger["updatedAt"] = mc._now()
                mc.save_ledger(ledger)
                steps.append({"step": "obey_chat_gate", "ok": False,
                              "verdict": "CHAT_DELIVERY_MISSING",
                              "ghost": bool(_gate.get("ghost"))})
                if _first:
                    mc.append_event(ledger["missionId"], pane_id or None,
                                    "chat_delivery_missing", detail=_gate["detail"])
                    vg.emit_bus_event("chat_delivery_missing", ledger["missionId"],
                                      _gate["detail"])
                    nf.mission_reopened(ledger["missionId"],
                                        "chat_delivery_missing: " + _gate["detail"])
                    if pane_id and mc.pane_exists(pane_id) is True:
                        nud_ok, nud_err = mc.deliver_prompt(pane_id, _gate["detail"][:900])
                        steps.append({"step": "obey_chat_gate_nudge", "ok": bool(nud_ok),
                                      "error": nud_err})
                if _lock_fd is not None:
                    os.close(_lock_fd); _lock_fd = None
                return _j({"ok": False, "error": "CHAT_DELIVERY_MISSING",
                           "missionId": ledger["missionId"], "paneId": pane_id or None,
                           "detail": _gate["detail"], "reopenedByChatDelivery": True,
                           "steps": steps})
            elif _gate is None:
                steps.append({"step": "obey_chat_gate", "ok": True,
                              "verdict": "pass" if not ledger.get("chatDeliverableExempt")
                                         else "exempt"})

        # ---- passo 0.4: RD-DISO-01 item 3 — MERGE GATE (worktree → main). Integra só
        # com badge verified_e2e VERDE + rebase fresco sem conflito + worktree commitado.
        # Conflito = REABERTURA tipada merge_conflict (nunca auto-resolve, nunca force).
        _merge_conflict: Optional[str] = None
        if ledger and ledger.get("missionId") and not _cancel:
            _merge_conflict = _merge_gate(ledger, steps, pane_id)
            if _merge_conflict:
                nudge = ("MERGE CONFLICT: %s — resolva na branch mission/* e rode o close "
                         "de novo (nunca auto-resolve, nunca force)" % _merge_conflict)[:900]
                return _close_reopen(ledger, pane_id, steps, nudge, _t_close)

        # ---- passo 0.5: SUPERVISOR-VERIFY-01 — gate do canal real do operator. Com
        # operatorChannel declarado no dispatch, roda a prova NO CANAL antes de aceitar o
        # fechamento (lição photopea: motor provado no canal interno ≠ operator usou o real).
        # Canal morto → reabre (interrupted + nudge + evento operator_channel_red no spool).
        if ledger and ledger.get("operatorChannel"):
            ch_ok, ch_proof = vg.run_channel_proof(ledger["operatorChannel"])
            if not ch_ok:
                nudge = ("OPERATOR_CHANNEL_PROOF_FAILED: canal do operator não respondeu — %s"
                         % str(ch_proof.get("error") or ch_proof))[:900]
                ledger["status"] = "interrupted"
                ledger["updatedAt"] = mc._now()
                mc.save_ledger(ledger)
                steps.append({"step": "operator_channel_proof", "ok": False,
                              "proof": ch_proof})
                if pane_id and mc.pane_exists(pane_id) is True:
                    nud_ok, nud_err = mc.deliver_prompt(pane_id, nudge)
                    if not nud_ok:
                        steps.append({"step": "operator_channel_nudge", "ok": False, "error": nud_err})
                vg.emit_bus_event("operator_channel_red", ledger["missionId"], nudge)
                # MISSION-NOTIFY-01: transição reopened — evento obrigatório no bus.
                nf.mission_reopened(ledger["missionId"],
                                    "operator_channel_red: " + nudge)
                if _lock_fd is not None:
                    os.close(_lock_fd); _lock_fd = None
                return _j({"ok": False, "missionId": ledger["missionId"],
                           "paneId": pane_id or None, "reopenedByOperatorChannel": True,
                           "proof": ch_proof, "steps": steps})
            steps.append({"step": "operator_channel_proof", "ok": True,
                          "url": ch_proof.get("url"), "status": ch_proof.get("status")})
        elif ledger and not ledger.get("operatorChannel") and not ledger.get("closeWarning"):
            ledger["closeWarning"] = "fechada SEM operator_channel declarado (recomendado declarar)"
            # TEMPLATE-PROTOCOL-01: warning sem step é invisível na resposta — registra o skip
            steps.append({"step": "operator_channel_proof", "ok": None, "skipped": True,
                          "note": "sem operatorChannel declarado — prova do canal não se aplica"})

        # ---- passo 1: /exit no claude (se o pane existe e o foreground é claude)
        # MISSION-SUPERVISOR-01: o supervisor morre junto (on_close registra o step)
        if st_ms := _ms("on_close", ledger, mc):
            if isinstance(st_ms, dict) and st_ms.get("refusal"):
                return _j(st_ms["refusal"])
            steps.append(st_ms)
        pex = mc.pane_exists(pane_id) if pane_id else None
        if pane_id and pex is True:
            name, ferr = mc.foreground_agent_name(pane_id)
            if ferr:
                steps.append({"step": "claude_exit", "ok": False, "error": ferr})
            elif name == "claude":
                if err := mc.run_command(pane_id, "/exit"):
                    steps.append({"step": "claude_exit", "ok": False, "error": err})
                else:
                    exited = False
                    for _ in range(5):
                        time.sleep(1.0)
                        name, _e = mc.foreground_agent_name(pane_id)
                        if name != "claude":
                            exited = True
                            break
                    steps.append({"step": "claude_exit_confirmed" if exited else "claude_exit_unconfirmed",
                                  "ok": exited})
            else:
                steps.append({"step": "claude_exit", "ok": True,
                              "note": "foreground não é claude — nada a encerrar"})
        elif pex is False:
            steps.append({"step": "claude_exit", "ok": True, "note": "pane já não existe"})
        elif not pane_id and ledger and ledger.get("headless"):
            # WORKER-HEADLESS-01: sem pane por desenho — o worker é processo próprio
            # (claude -p), cuja saída está no log da missão; nada a encerrar no herdr.
            steps.append({"step": "claude_exit", "ok": True,
                          "note": "worker headless (claude -p): sem pane — processo próprio, "
                                  "saída no log da missão"})

        # ---- passo 2: fechar a aba da missão
        tab_id = (ledger or {}).get("tabId")
        if not tab_id and pane_id:
            pane, perr = mc.pane_get(pane_id)
            if pane and not perr:
                tab_id = pane.get("tab_id")
        if _keep_pane:
            # ENG-MCP-TOOLS-FIX-02 (keepPane): fecha ledger mas preserva a aba (forense/
            # pós-incidente — supervisor audita o pane depois).
            steps.append({"step": "tab_close", "tabId": tab_id or None, "ok": True,
                          "note": "keepPane=true — aba preservada"})
        elif tab_id:
            cerr = mc.tab_close(tab_id)
            steps.append({"step": "tab_close", "tabId": tab_id, "ok": not cerr, "error": cerr})
        else:
            steps.append({"step": "tab_close", "ok": True, "note": "sem tabId conhecido — nada a fechar"})

        # ---- passo 3: worktree cleanup APENAS se gravado no ledger
        if ledger and ledger.get("worktreeWorkspaceId"):
            werr = mc.worktree_remove(workspace=str(ledger["worktreeWorkspaceId"]),
                                      force=bool(args.get("force")))
            steps.append({"step": "worktree_remove", "workspaceId": ledger["worktreeWorkspaceId"],
                          "ok": not werr, "error": werr})

        # ---- passo 3.5: RD-DISO-01 item 2 — lease do componente liberado no fecho
        # (o componente volta à fila; próximo intent do grupo despacha)
        if ledger and ledger.get("missionId"):
            _lcomp = str(ledger.get("component") or "")
            try:
                lok, lcode, ldet = leases.release(str(ledger["missionId"]),
                                                  _lcomp or None)
            except Exception as _lr_exc:
                lok, lcode, ldet = False, "LEASE_RELEASE_FAILED", str(_lr_exc)[:200]
            steps.append({"step": "lease_release", "ok": bool(lok),
                          "component": _lcomp or None, "code": lcode,
                          "detail": str(ldet)[:160]})

        # ---- passo 4: ledger status closed
        if ledger:
            ledger["status"] = "closed"
            ledger["closedAt"] = mc._now()
            ledger["updatedAt"] = mc._now()
            mc.save_ledger(ledger)
            mc.append_event(ledger["missionId"], pane_id or None, "mission_closed",
                            detail="; ".join(s.get("step", "") for s in steps))
            # ENG-MCP-TOOLS-FIX-02: trilha decisionNote + evento mission_cancelled no bus
            # (o comentário do deliver-verify prometia o evento — nunca foi emitido).
            if _decision_note:
                ledger["decisionNote"] = _decision_note
                mc.save_ledger(ledger)
            if _cancel:
                _cdet = (_decision_note or _accept_unv or "cancel=true")[:600]
                mc.append_event(ledger["missionId"], pane_id or None, "mission_cancelled",
                                detail=_cdet)
                vg.emit_bus_event("mission_cancelled", ledger["missionId"], _cdet)
            # MISSION-NOTIFY-01: transição completed — mission_completed no bus com
            # badge verified_e2e + custo GPU + veredito (o fim do regime "descobrimos olhando").
            badge = "verified_e2e" if ledger.get("verified_e2e") else None
            verdict = ((ledger.get("verified_e2e") or {}).get("verdict")
                       if badge else "unverified_consequence" if unverified_consequence
                       else "no_verify_manifest")
            if unverified_consequence:
                # CLOSE-VERIFY-GUARD-01 (a): fechou, mas a trilha auditável registra o furo.
                mc.append_event(ledger["missionId"], pane_id or None,
                                "closed_unverified_consequence", detail=unverified_consequence)
                vg.emit_bus_event("closed_unverified_consequence", ledger["missionId"],
                                  unverified_consequence)
        else:
            mc.append_event("?", pane_id or None, "mission_closed", detail="sem ledger — fechamento físico")

        # ---- passo 5: GPU-ORCHESTRATOR-01 — missão engine=gpu → gpu-down (garfo
        # anti-thrash interno no script: adia se outra missão gpu viva/recente). Fail-open.
        if ledger and ledger.get("engine") == "gpu":
            try:
                proc = subprocess.run(["bash", os.path.join(_GPU_ORCH, "gpu-down.sh")],
                                      capture_output=True, timeout=180,
                                      env={**os.environ,
                                           "GPU_SKIP_MISSION": str(ledger["missionId"])})
                last, err_tail = _gpu_down_detail(proc)
                gdown_ok = proc.returncode == 0
                step = {"step": "gpu_down", "ok": gdown_ok, "exit": proc.returncode, "detail": last}
                if err_tail:
                    step["stderr_tail"] = err_tail
                steps.append(step)
                if not gdown_ok:
                    _spool_gpu_event("gpu_down_failed", str(ledger["missionId"]),
                                     "exit %s: %s" % (proc.returncode, last))
            except Exception as e:
                steps.append({"step": "gpu_down", "ok": False, "error": str(e)[:200]})
                _spool_gpu_event("gpu_down_failed", str(ledger["missionId"]), str(e)[:300])

        # ---- passo 6: GPU-COST-FIX-01 — custo MEDIDO por missão, DEPOIS do gpu-down (state com
        # destroyedAt/cost_ledger final). Um número só: ledger + spool + mission_completed.
        _cost_warning: Optional[Dict[str, Any]] = None  # ORCH-SPEND-LEDGER-01
        if ledger:
            cost_rec: Optional[Dict[str, Any]] = None
            if ledger.get("engine") == "gpu":
                cost_rec = nf.mission_cost_record(ledger)
                trail = nf.record_mission_cost(cost_rec)
                ledger["cost"] = cost_rec
                mc.save_ledger(ledger)
                steps.append({"step": "mission_cost", "ok": bool(trail.get("ok")),
                              "emitted": bool(trail.get("emitted")),
                              **{k: cost_rec[k] for k in ("cost_usd", "final", "cost_unmeasured",
                                                          "tokens_proxy", "instance_id")
                                 if k in cost_rec}})
            else:
                # ORCH-SPEND-LEDGER-01: custo LLM REAL por transcript (engineering.orchestrate.
                # mission_spend, HTTP MCP direto ao mesmo servidor das sessões) para missões
                # engine!=gpu — o passo mission_cost conectado ao cálculo real em vez de omissão.
                # Fail-open TOTAL: qualquer erro → cost_unmeasured com motivo tipado + warning,
                # close SEGUE ok (contrato itens 2-3). Idempotente: re-close idempotente nem
                # chega aqui; re-execução sobrescreve ledger["cost"] com o mesmo payload.
                try:
                    cost_rec = nf.transcript_cost_record(ledger)
                    trail = nf.record_mission_cost(cost_rec)
                    ledger["cost"] = cost_rec
                    # RD-OPS-03-B: campo spend no ledger (contrato item 2) — mesma forma
                    # do writeMissionSpend server-side ({inputTokens, outputTokens,
                    # cacheReadTokens, costUsdEstimate, source} com a fonte citada).
                    # Closes via gateway/supervisor não passam pelo wrapper MCP
                    # (runMissionClose) e por isso o campo nunca era gravado em
                    # produção; o plugin grava agora, unmeasured → custo null + causa.
                    ledger["spend"] = nf.spend_ledger_record(cost_rec)
                    mc.save_ledger(ledger)
                    _step = {"step": "mission_cost", "ok": True,  # nunca vira all_ok False (fail-open)
                             "emitted": bool(trail.get("emitted")),
                             **{k: cost_rec[k] for k in ("cost_usd", "final", "cost_unmeasured",
                                                         "tokens_in", "tokens_out", "source")
                                if k in cost_rec}}
                    if trail.get("error"):
                        _step["trail_error"] = str(trail["error"])[:200]
                    steps.append(_step)
                    if cost_rec.get("cost_unmeasured"):
                        _cost_warning = {"code": "mission_cost_unmeasured",
                                         "detail": str(cost_rec["cost_unmeasured"])[:300]}
                except Exception as _spend_exc:  # cinto E suspensa: close nunca trava por custo
                    steps.append({"step": "mission_cost", "ok": True,
                                  "error": str(_spend_exc)[:200]})
                    _cost_warning = {"code": "mission_cost_unmeasured",
                                     "detail": str(_spend_exc)[:300]}
            close_notify = nf.mission_completed(
                ledger["missionId"], badge=badge,
                cost_usd=(cost_rec or {}).get("cost_usd"), verdict=str(verdict),
                cost_unmeasured=(cost_rec or {}).get("cost_unmeasured"))
            # OBEY-HARD-GATE-01 (T2): o evento mission_completed carrega o pacote
            # canônico pronto pra colar (chatDeliveryPackage) — mecanismo, não
            # memória do modelo. Fail-open.
            try:
                _pkg = ob.chat_delivery_package(
                    str(ledger["missionId"]),
                    str(ledger.get("cwd") or os.getcwd()),
                    ledger=ledger, cost_rec=cost_rec)
                close_notify["package"] = {k: _pkg.get(k) for k in
                                           ("veredito", "resumo_1linha", "custo_usd",
                                            "custo_txt", "caminho_relatorio",
                                            "template_chat") if _pkg.get(k) is not None}
                if _pkg.get("conteudo_integral"):
                    close_notify["package"]["conteudo_integral_bytes"] = \
                        len(_pkg["conteudo_integral"])
            except Exception as _pkg2_exc:
                steps.append({"step": "notify_package", "ok": True, "verdict": "fail-open",
                              "error": str(_pkg2_exc)[:160]})
            steps.append({"step": "notify_mission_completed",
                          "ok": bool(close_notify.get("ok")),
                          "emitted": bool(close_notify.get("emitted")),
                          "error": close_notify.get("error")})

        # ---- MEMORY-CAPTURE-01: capture durável no fecho (best-effort, não-fatal).
        # RD-EV-03: projectId resolvido da tabela declarada (fonte única com o
        # server-side); o capture AUTO no close agora vive server-side
        # (eng-mcp runMissionClose → missionMemoryCapture) — este passo segue
        # como best-effort redundante (idempotente pelo MESMO marker).
        try:
            _cap_ok, _cap_err, _cap_dedup = mc.memory_capture(
                ledger.get("missionId") or mission_id,
                str((ledger.get("summary") or ledger.get("relatorio") or ""))[:2900]
                or ("fecho da missão %s" % (ledger.get("missionId") or mission_id)),
                project_id=mc.resolve_project_for_cwd(str(ledger.get("cwd") or "")))
            steps.append({"step": "memory_capture", "ok": True if _cap_ok else None,
                          "deduped": bool(_cap_dedup), "error": _cap_err})
        except Exception as _cap_exc:
            steps.append({"step": "memory_capture", "ok": None,
                          "error": str(_cap_exc)[:200]})  # nunca derruba o close

        # ---- RD-OPS-03-SPEND-01: dívidas herdadas visíveis no fechamento (mecanismo).
        # Componente do promptFile do ledger → dívidas abertas do ROADMAP relevantes;
        # tag [operator-charged] sobe a dívida para Prio 1 no ROADMAP automaticamente
        # (idempotente, atômico). Fail-open: nunca derruba o close.
        try:
            _component = rd.mission_component((ledger or {}).get("promptFile"))
            _promoted = rd.promote_operator_charged()
            _debts, _rd_err = rd.inherited_debts_checked(
                _component, exclude_ids=[str((ledger or {}).get("missionId") or "")])
            if _rd_err:
                _line = "Dívidas herdadas: indisponível (%s)" % _rd_err
            else:
                _line = rd.herdadas_line(_debts, _component)
            _debt_step: Dict[str, Any] = {"step": "inherited_debts",
                                          "ok": None if _rd_err else True,
                                          "component": _component, "count": len(_debts),
                                          "line": _line,
                                          "operator_charged_promoted": _promoted.get("changed") or []}
            if _rd_err:
                _debt_step["roadmap_error"] = str(_rd_err)[:160]
            if _promoted.get("error"):
                _debt_step["promotion_error"] = str(_promoted["error"])[:160]
        except Exception as _rd_exc:
            _debts, _line, _component = [], None, None
            _rd_err = "inherited_debts_exception: %s" % str(_rd_exc)[:140]
            _debt_step = {"step": "inherited_debts", "ok": None,
                          "error": str(_rd_exc)[:200]}  # nunca derruba o close
        steps.append(_debt_step)

        # ---- RD-ORCH-FILA-01: retroalimentação close→ROADMAP. Fecho real (não
        # cancelamento) atualiza a linha RD-* correspondente no ROADMAP.md —
        # Estado → `resolvido <data> (<missionId>: commit <hash|sem-commit>;
        # fonte: RELATORIO|ledger>)`. Fail-open: erro é step ok=None tipado,
        # nunca derruba o close; linha sem correspondência → unmapped-rd tipado.
        if not _cancel and ledger and ledger.get("missionId"):
            _fb_verdict = next((s.get("verdict") for s in reversed(steps)
                                if s.get("step") == "deliver_verify"), None)
            try:
                _fb = rd.close_feedback(str(ledger["missionId"]),
                                        cwd=(ledger.get("cwd") or None),
                                        verdict=(_fb_verdict if isinstance(_fb_verdict, str) else None))
                _fb_step: Dict[str, Any] = {"step": "roadmap_feedback",
                                            "ok": None if _fb.get("error") else True,
                                            "mapped": _fb.get("mapped"),
                                            "changed": _fb.get("changed", False)}
                if _fb.get("reason"):
                    _fb_step["reason"] = _fb["reason"]
                if _fb.get("estado"):
                    _fb_step["estado"] = _fb["estado"]
                if _fb.get("commit"):
                    _fb_step["commit"] = _fb["commit"]
                if _fb.get("error"):
                    _fb_step["error"] = str(_fb["error"])[:160]
                steps.append(_fb_step)
            except Exception as _fb_exc:
                steps.append({"step": "roadmap_feedback", "ok": None,
                              "error": str(_fb_exc)[:160]})  # nunca derruba o close

        # ---- RD-DEBT-01 (DEBT-SWEEP-01): ciclo de vida das dívidas herdadas.
        # Captura das dívidas herdadas (regex puro, mesmas linhas do ROADMAP do
        # passo inherited_debts) no registry debts.jsonl + dedupe por texto
        # normalizado (1 registro, N fontes) + promoção mecânica (worker-doable →
        # intent dispatch_mission na fila do orquestrador; credencial/orçamento →
        # gate-operator) + envelhecimento + fecho (missão dona fechou PASS →
        # closed; dívida só sai por ledger fechado). Fail-open: nunca derruba o
        # close; cancelamento não captura nem fecha.
        if not _cancel and ledger and ledger.get("missionId"):
            try:
                _ds_verdict = next((s.get("verdict") for s in reversed(steps)
                                    if s.get("step") == "deliver_verify"), None)
                if _ds_verdict != "pass" and (ledger.get("verified_e2e") or {}).get("verdict") == "pass":
                    _ds_verdict = "pass"
                _ds = mdb.debt_sweep(
                    str(ledger["missionId"]), _component, _debts,
                    rd_err=_rd_err if _rd_err else None,
                    verdict=(_ds_verdict if isinstance(_ds_verdict, str) else None),
                    cancel=_cancel)
                _ds_step: Dict[str, Any] = {
                    "step": "debt_sweep", "ok": _ds.get("ok"),
                    "captured": len(_ds.get("captured") or []),
                    "deduped": len(_ds.get("deduped") or []),
                    "promoted": len(_ds.get("promoted") or []),
                    "gateOperator": len(_ds.get("gateOperator") or []),
                    "closed": _ds.get("closed") or []}
                if _ds.get("roadmapError"):
                    _ds_step["roadmapError"] = _ds["roadmapError"]
                if _ds.get("needsContract"):
                    _ds_step["needsContract"] = _ds["needsContract"]
                if _ds.get("agingFindings"):
                    _ds_step["agingFindings"] = _ds["agingFindings"]
                if _ds.get("errors"):
                    _ds_step["errors"] = _ds["errors"][:5]
                _debt_step_out = _ds_step
            except Exception as _ds_exc:
                _debt_step_out = {"step": "debt_sweep", "ok": None,
                                  "error": str(_ds_exc)[:200]}  # nunca derruba o close
            steps.append(_debt_step_out)

        # ---- FINDINGS-01: registro + ciclo de vida dos findings (catálogo como
        # dado, custo-zero). Fontes determinísticas do próprio fecho
        # (unverified_consequence → P2; custo não medido → P3) + resolve dos ids
        # declarados no arg resolveFindings (a missão que tratou fecha o finding)
        # + aging scan idempotente (o ciclo existe também sem o timer 24h).
        # Registry/bus seguem o _MISSION_SPOOL do processo (suítes nunca tocam
        # produção). Fail-open: erro tipado no step, nunca derruba o close.
        if not _cancel and ledger and ledger.get("missionId"):
            try:
                _fitems: List[Dict[str, Any]] = []
                if unverified_consequence:
                    _fitems.append({"texto": unverified_consequence,
                                    "severidade": "P2",
                                    "componente": _component or "mission-ops"})
                if _cost_warning and _cost_warning.get("detail"):
                    _fitems.append({"texto": _cost_warning["detail"],
                                    "severidade": "P3",
                                    "componente": _component or "mission-ops"})
                _fh = fd.close_hook(
                    str(ledger["missionId"]), register_items=_fitems,
                    resolve_ids=args.get("resolveFindings"),
                    registry=_findings_registry(),
                    bus=_MISSION_SPOOL)
                _f_step: Dict[str, Any] = {
                    "step": "findings_register", "ok": _fh.get("ok"),
                    "registered": _fh.get("registered") or [],
                    "deduped": _fh.get("deduped") or [],
                    "resolved": _fh.get("resolved") or [],
                    "agingEscalated": _fh.get("agingEscalated") or []}
                if _fh.get("agingFindings"):
                    _f_step["agingFindings"] = _fh["agingFindings"]
                if _fh.get("errors"):
                    _f_step["errors"] = _fh["errors"][:5]
                _findings_step_out = _f_step
            except Exception as _fh_exc:
                _findings_step_out = {"step": "findings_register", "ok": None,
                                      "error": str(_fh_exc)[:200]}  # nunca derruba o close
            steps.append(_findings_step_out)

        # ---- CLOSE-SHIP-VISIBILITY-01: janela de release — um voo aterrissou (este close):
        # SHIPs em awaiting_ship_window são reavaliadas e despachadas quando a janela abre.
        # Fail-open: nunca derruba o close.
        if ledger:
            try:
                _released = cs.release_awaiting_ships(str(ledger["missionId"]))
                if _released:
                    steps.append({"step": "ship_window_release", "ok": True,
                                  "released": _released})
            except Exception as _rel_exc:
                steps.append({"step": "ship_window_release", "ok": True,
                              "verdict": "fail-open", "error": str(_rel_exc)[:160]})

        all_ok = all(s.get("ok") for s in steps if s.get("ok") is not None)
        resp: Dict[str, Any] = {"ok": all_ok, "missionId": (ledger or {}).get("missionId"),
                                "paneId": pane_id or None, "steps": steps}
        if unverified_consequence:
            resp["warnings"] = [unverified_consequence]
        # ORCH-SPEND-LEDGER-01: warning tipado quando o custo não pôde ser medido
        # (fail-open honesto — a omissão tem motivo, nunca silêncio).
        if _cost_warning:
            resp.setdefault("warnings", []).append(_cost_warning)
        # RD-OPS-03-SPEND-01: resumo do close carrega a linha Dívidas herdadas +
        # lista estruturada (uma entrada por dívida herdada relevante ao componente).
        resp["inheritedDebtsLine"] = _line
        resp["inheritedDebts"] = _debts
        if _component:
            resp["component"] = _component
        # ---- SUP-OBEY-01 (guard de fecho): chatDeliverable = conteúdo INTEGRAL do
        # RELATORIO-<id>.md do cwd do close — o payload que o supervisor DEVE reproduzir
        # no chat na mesma resposta (OBRIGACOES.md item 1). Ausente → warning tipado
        # relatorio_nao_entregado_chat. Guard ship: violações diretas do dia
        # (git push/merge/release fora de missão SHIP-*) listadas no fecho. Fail-open:
        # nunca derruba o close.
        try:
            resp = ob.relatorio_pendente_guard(
                str((ledger or {}).get("missionId") or mission_id),
                str((ledger or {}).get("cwd") or os.getcwd()), resp)
            # events do ESTADO do plugin (TempState dos testes redireciona com o resto)
            _viol = ob.scan_day_direct_ship(
                events_path=os.path.join(str(mc.STATE_DIR), "events.jsonl"))
            if _viol:
                resp["directShipViolations"] = _viol
            # GUARD-SUPERVISOR-READONLY-01 (RELATÓRIO-INTEGRA): evento tipado
            # relatorio_integra_missing enquanto a colagem INTEGRAL do relatório no
            # chat do supervisor não for registrada (mission_report_ack). Fail-open.
            resp = sg.relatorio_integra_guard(
                str((ledger or {}).get("missionId") or mission_id),
                str((ledger or {}).get("cwd") or os.getcwd()), resp,
                spool_path=_MISSION_SPOOL)
            # RD-OBEY-02 (gates de aplicação): violação clara de ordem → warning
            # tipado `violates-obligation-<id>` na resposta (fail-open: nunca
            # bloqueia a operação, SEMPRE marca) + finding no bus + dívida
            # automática tipada `obedience` (P1, intent na fila). O1: close sem
            # relatório entregável ao chat; O2: ship direto desta missão.
            # RD-LOOP-01: cancelamento não é claim de entrega (mesma doutrina do
            # deliver-verify skip-cancel) — O1 não se aplica a close cancelado.
            if not _cancel:
                resp = obr.gate_close(
                    str((ledger or {}).get("missionId") or mission_id), resp,
                    spool_path=_MISSION_SPOOL,
                    obedience_path=os.path.join(str(mc.STATE_DIR), "obedience.jsonl"))
        except Exception as _ob_exc:
            resp.setdefault("warnings", []).append(
                {"code": "obedience_guard_off", "detail": str(_ob_exc)[:160]})
        # RD-GUARD-CLOSE-STATE-01 (04/10): relatório integral anexado ao payload
        # do close (SUP-OBEY-01) registra a entrega no ledger —
        # chatDeliverable.delivered: true — isentando o mission_report_ack de
        # token (fluxo registrado). Fail-open: erro de escrita nunca derruba o
        # close; sem entrega, ledger intocado (recusa do ack mantida).
        _cd = resp.get("chatDeliverable")
        if isinstance(_cd, dict) and str(_cd.get("content") or "").strip():
            try:
                ledger["chatDeliverable"] = {"delivered": True,
                                             "path": _cd.get("path"),
                                             "deliveredAt": mc._now()}
                ledger["updatedAt"] = mc._now()
                mc.save_ledger(ledger)
            except Exception:
                pass
        # ---- RELATORIO-INTEGRA-V2-HARD (ordem do operator 05/10 ~14:05 BRT):
        # todo close devolve o bloco 'chatIntegra' PRONTO (resumo + caminhos +
        # custo + dívidas) — o supervisor cola no chat SEM recompor nada.
        # Mecânico: a omissão não depende de memória do modelo. Fail-open.
        try:
            _reli = []
            for _rel in ("RELATORIO-%s.md" % str((ledger or {}).get("missionId")),
                         "relatorio-%s.md" % str((ledger or {}).get("missionId")).lower()):
                _p = os.path.join(str((ledger or {}).get("cwd") or os.getcwd()), _rel)
                if os.path.exists(_p):
                    _reli.append(_p)
            _p2 = os.path.join(str(mc.STATE_DIR), "%s.verify.json" % str((ledger or {}).get("missionId")))
            if os.path.exists(_p2):
                _reli.append(_p2)
            _cd2 = resp.get("chatDeliverable")
            if isinstance(_cd2, dict) and _cd2.get("path"):
                _reli.insert(0, str(_cd2.get("path")))
            _cos = (ledger or {}).get("cost") or {}
            _resumo = str((ledger or {}).get("summary") or (ledger or {}).get("relatorio") or "")
            _resumo = _resumo.strip().split("\n")[0][:280]
            resp["chatIntegra"] = {
                "missionId": (ledger or {}).get("missionId"),
                "status": (ledger or {}).get("status"),
                "verdict": (ledger or {}).get("verdict"),
                "badge": (ledger or {}).get("verified_e2e", {}).get("verdict") if isinstance((ledger or {}).get("verified_e2e"), dict) else None,
                "resumo_1linha": _resumo,
                "caminhos": _reli,
                "custo": (_cos if _cos and not _cos.get("cost_unmeasured")
                          else {"cost_unmeasured": str((_cos or {}).get("cost_unmeasured") or (_cost_warning or {}).get("detail") or "sem medida (transcript) — ver RD-OPS-03")}),
                "dividas_herdadas": _line,
                "template_chat": (
                    "## Resumo do fecho — %s\n**O que entregou:** %s\n**Caminho:** %s\n**Custo:** %s\n**Dívidas:** %s"
                    % ((ledger or {}).get("missionId"), _resumo,
                       "; ".join(_reli) or "(sem arquivo de relatório pousado)",
                       (("%s" % _cos.get("cost_usd")) if isinstance(_cos, dict) and _cos.get("cost_usd") is not None
                        else "não medido (ver RD-OPS-03)"),
                       _line or "—")),
            }
            resp["chatAckRequired"] = True
        except Exception as _ci_exc:
            resp.setdefault("warnings", []).append(
                {"code": "chat_integra_block_off", "detail": str(_ci_exc)[:160]})
        # ---- OBEY-HARD-GATE-01 (T2): PACOTE PRONTO NO CLOSE — {veredito,
        # resumo_1linha, custo_usd, caminho_relatorio, conteudo_integral} unificado
        # num objeto canônico (chatDeliveryPackage) pronto pra colar no chat do
        # operator. Zero LLM, custo-zero; também vai no evento mission_completed
        # (abaixo, campo package_summary). Fail-open.
        try:
            ob.chat_delivery_package(
                str((ledger or {}).get("missionId") or mission_id),
                str((ledger or {}).get("cwd") or os.getcwd()),
                ledger=ledger, cost_rec=cost_rec, resp=resp)
        except Exception as _pkg_exc:
            resp.setdefault("warnings", []).append(
                {"code": "chat_delivery_package_off", "detail": str(_pkg_exc)[:160]})
        # RD-DISO-01 item 8: fecho completo medido (close_ms) + turno medido no
        # close só quando o watch não viu o turn_done (evita dupla contagem)
        if ledger and ledger.get("missionId"):
            lat.timed("close_ms", str(ledger["missionId"]), _t_close, detail="close ok")
            _le = mc.last_event(str(ledger["missionId"])) or {}
            if not _cancel and str(_le.get("event") or "") != "turn_done":
                _t_disp = _iso_to_epoch(str(ledger.get("dispatchedAt") or ""))
                if _t_disp:
                    lat.record("turn_ms", str(ledger["missionId"]),
                               (time.time() - _t_disp) * 1000.0, detail="close (sem turn_done no watch)")
        if _lock_fd is not None:
            os.close(_lock_fd); _lock_fd = None
        return _j(resp)
    finally:
        # RD-MOPS-01: liberação garantida — os closes internos setam
        # _lock_fd = None (idempotentes); return direto em qualquer passo
        # ou exceção não tratada também passam por aqui. O lock por inode
        # morre com o processo chamador, nunca sobrevive ao turno.
        if _lock_fd is not None:
            try:
                os.close(_lock_fd)
            except OSError:
                pass
            _lock_fd = None


def handle_mission_worktree_add(args: Dict[str, Any], **_kw) -> str:
    mission_id = str(args.get("missionId") or "").strip()
    branch = str(args.get("branch") or "").strip()
    if not mission_id:
        return _err("INVALID_MISSION_ID", "missionId é obrigatório")
    if e := mc.validate_mission_id(mission_id):
        return _err("INVALID_MISSION_ID", e)
    if not branch:
        return _err("INVALID_BRANCH", "branch é obrigatório")
    ledger = mc.load_ledger(mission_id)
    if ledger is None:
        return _err("MISSION_NOT_FOUND", f"nenhum ledger para {mission_id}")
    if ledger.get("worktreePath") or ledger.get("worktreeWorkspaceId"):
        return _err("WORKTREE_ALREADY_RECORDED",
                    f"ledger já grava worktree {ledger.get('worktreePath')} (workspace "
                    f"{ledger.get('worktreeWorkspaceId')}) — remova antes de criar outro")
    label = str(args.get("label") or "").strip() or f"mission:{mission_id}"
    info, err = mc.worktree_create(branch=branch, path=args.get("path"),
                                   base=args.get("base"), label=label, cwd=ledger.get("cwd"))
    if err or info is None:
        return _err("HERDR_WORKTREE_FAILED", err or "sem detalhe do worktree create")
    ledger["worktreePath"] = info.get("path")
    ledger["worktreeBranch"] = info.get("branch") or branch
    ledger["worktreeWorkspaceId"] = info.get("workspace_id") or info.get("open_workspace_id")
    ledger["updatedAt"] = mc._now()
    mc.save_ledger(ledger)
    mc.append_event(mission_id, ledger.get("paneId"), "worktree_added",
                    detail=str(ledger["worktreePath"]))
    return _j({"ok": True, "missionId": mission_id, "worktree": info})


def handle_mission_worktree_remove(args: Dict[str, Any], **_kw) -> str:
    mission_id = str(args.get("missionId") or "").strip()
    if not mission_id:
        return _err("INVALID_MISSION_ID", "missionId é obrigatório")
    if e := mc.validate_mission_id(mission_id):
        return _err("INVALID_MISSION_ID", e)
    ledger = mc.load_ledger(mission_id)
    if ledger is None:
        return _err("MISSION_NOT_FOUND", f"nenhum ledger para {mission_id}")
    if not ledger.get("worktreeWorkspaceId") and not ledger.get("worktreePath"):
        return _err("WORKTREE_NOT_RECORDED",
                    "nenhum worktree gravado no ledger — nada a remover (nunca remove às cegas)")
    force = str(args.get("force") or "").strip().lower() in ("1", "true", "yes")
    err = mc.worktree_remove(workspace=str(ledger.get("worktreeWorkspaceId") or ""), force=force)
    if err:
        return _err("HERDR_WORKTREE_FAILED", err)
    removed = {"path": ledger.pop("worktreePath", None),
               "branch": ledger.pop("worktreeBranch", None),
               "workspaceId": ledger.pop("worktreeWorkspaceId", None)}
    ledger["updatedAt"] = mc._now()
    mc.save_ledger(ledger)
    mc.append_event(mission_id, ledger.get("paneId"), "worktree_removed",
                    detail=str(removed.get("path")))
    return _j({"ok": True, "missionId": mission_id, "removed": removed, "force": force})


def _spool_deliver_verify_red(ledger: Dict[str, Any], pane_id: str, msg: str) -> Optional[str]:
    """DELIVER-VERIFY-01: evento deliver_verify_red no spool do bus (fire-and-forget).
    SUPERVISOR-VERIFY-01: também passa pelo emit_bus_event (mesmo canal do
    operator_channel_red) — o watcher do supervisor consome o bus, não o arquivo."""
    line = json.dumps({
        "ts": mc._now(), "event": "deliver_verify_red", "kind": "deliver_verify_red",
        "session_id": None, "cwd": ledger.get("cwd"), "pane": pane_id or None,
        "tab": ledger.get("tabId"), "msg": msg, "source": "hermes-gateway",
    }, ensure_ascii=False)
    err: Optional[str] = None
    try:
        with open("/opt/mission-events/spool.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        err = str(e)[:400]
    try:
        vg.emit_bus_event("deliver_verify_red",
                          str(ledger.get("missionId") or ""), msg)
    except Exception as e:
        err = err or str(e)[:400]
    return err


def handle_mission_verify(args: Dict[str, Any], **_kw) -> str:
    """DELIVER-VERIFY-01: wrapper determinístico do runner /opt/deliver-verify/verify.py
    (zero LLM) — o supervisor (hoje Hermes, amanhã Qwen/TRINITY) chama como tool.
    ENG-MCP-TOOLS-FIX-02: resolução por paneId/fragment (mesma semântica do close),
    filtro checks[] (subconjunto marcado partial:true — nunca "pass" com provas
    parciais), timeoutMs (default 150000 = teto do runner, RD-PERF-VERIFY-01; clamp 1s..teto),
    contexto honesto (ledgerStatus + agentStatus) e warning NO_MANIFEST quando o cwd
    da missão não tem verify.json (não deixa a bateria inferida parecer prova)."""
    manifest = str(args.get("manifest") or "").strip()
    ledger, rerr = _resolve_ledger_by(args)
    if rerr is not None:
        return rerr
    mission_id = str((ledger or {}).get("missionId") or "")
    pane_id = str(args.get("paneId") or (ledger or {}).get("paneId") or "").strip()
    timeout_ms = args.get("timeoutMs")
    try:
        # RD-PERF-VERIFY-01: teto do runner 150s (era 35s; provas legítimas de ~99s
        # estouravam) — default e clamp pela mesma constante (teto duro).
        timeout_s = max(1.0, min(float(DV_CLOSE_TIMEOUT_S),
                                 float(timeout_ms) / 1000.0)) if timeout_ms \
            else float(DV_CLOSE_TIMEOUT_S)
    except (TypeError, ValueError):
        return _err("INVALID_INPUT", "timeoutMs deve ser número (ms; default 150000)")
    cmd = ["python3", "/opt/deliver-verify/verify.py", "--mission", mission_id,
           "--ledger-dir", str(mc.STATE_DIR)]
    if manifest:
        cmd += ["--manifest", manifest]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return _err("VERIFY_RUN_FAILED",
                    "runner estourou timeout %.0fs — runner_error, retryable" % timeout_s)
    except Exception as e:
        return _err("VERIFY_RUN_FAILED", str(e)[:400])
    out = (proc.stdout or b"")[:8192].decode("utf-8", "replace")
    try:
        report = json.loads(out)
    except Exception:
        return _err("VERIFY_BAD_OUTPUT", ((proc.stderr or out) or "sem saída")[:400])

    # ENG-MCP-TOOLS-FIX-02 (checks[]): roda o runner completo, devolve subconjunto
    # marcado partial:true — provas parciais NUNCA valem "pass" da missão inteira.
    requested = args.get("checks")
    warnings: List[str] = []
    if isinstance(requested, list) and requested:
        want = {str(c) for c in requested}
        all_checks = report.get("checks") or []
        subset = [c for c in all_checks if str(c.get("id")) in want]
        missing = sorted(want - {str(c.get("id")) for c in subset})
        if missing:
            warnings.append("checks não encontrados no runner: %s" % ", ".join(missing))
        report["checks"] = subset
        report["partial"] = True
        report["verdict"] = "partial"
        report["ok"] = bool(subset) and all(bool(c.get("ok")) for c in subset)
    # NO_MANIFEST honesto: source inferred (bateria) sem verify.json no cwd do ledger
    # não é prova — warning + lista dos caminhos varridos.
    if report.get("source", "manifest") != "manifest" and ledger.get("cwd"):
        cw = str(ledger["cwd"])
        # mesmos dirs legítimos do runner (resolve_manifest + _extra_search_dirs):
        # cwd + extraDirs do ledger + parent do cwd. /opt/mission-events entra só
        # via extraDirs — nunca hardcoded (verify.json alheio no dir global não é prova).
        scanned = [cw]
        for d in (ledger.get("extraDirs") or []):
            if d and os.path.isdir(d):
                scanned.append(str(d))
        parent = os.path.dirname(os.path.normpath(cw))
        if parent and parent != cw and os.path.isdir(parent):
            scanned.append(parent)
        scanned = sorted(set(scanned))
        has_any = any(os.path.isfile(os.path.join(p, "verify.json"))
                      or os.path.isfile(os.path.join(p, "verify-%s.json" % mission_id))
                      for p in scanned)
        if not has_any:
            report["source"] = report.get("source") or "inferred"
            warnings.append("NO_MANIFEST: nenhum verify.json em %s — veredito vem de "
                            "bateria inferida, não de prova declarada; para manifesto "
                            "tipado use engineering.mission.verify_author" % ", ".join(scanned))
    ledger_status = mc.load_ledger(mission_id)
    report["ledgerStatus"] = (ledger_status or {}).get("status")
    astat, _aerr = _pane_agent_status(pane_id) if pane_id else (None, None)
    report["agentStatus"] = astat
    if warnings:
        report["warnings"] = warnings
    report["missionId"] = mission_id
    return _j(report)


def handle_mission_verify_author(args: Dict[str, Any], **_kw) -> str:
    """VERIFY-MANIFEST-01: GERA verify.json a partir de prova REAL (relatório > prompt >
    fallback do runner), cada item com _provenance. Fluxo seguro: diff sempre na resposta
    (calculado antes de gravar); verify.json existente só com force; dryRun não grava;
    após gravar roda mission_verify no manifesto novo (manifesto errado = checks vermelhos)."""
    mission_id = str(args.get("missionId") or "").strip()
    if not mission_id:
        return _err("INVALID_MISSION_ID", "missionId é obrigatório")
    if e := mc.validate_mission_id(mission_id):
        return _err("INVALID_MISSION_ID", e)
    ledger = mc.load_ledger(mission_id) or {}
    cwd = str(args.get("cwd") or ledger.get("cwd") or "").strip()
    if not cwd:
        return _err("NO_LEDGER", "missão sem ledger/cwd — passe cwd explícito")
    try:
        prop = va.author(mission_id, cwd, ledger.get("promptFile"))
    except va.AuthorError as e:
        return _err(e.code, e.detail)
    path = os.path.join(cwd, "verify.json")
    new = va.render(prop["manifest"])
    old = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            old = f.read()
    out = {"ok": True, "missionId": mission_id, "manifestPath": path,
           "report": prop["report"], "prompt": prop["prompt"],
           "provenance": prop["provenance"], "skipped": prop["skipped"],
           "diff": va.diff(old, new, path), "written": False}
    if old is not None and not _flag(args, "force"):
        out.update(ok=False, error="VERIFY_JSON_EXISTS",
                   detail="verify.json já existe em %s — não sobrescrevo sem force=true "
                          "(diff do proposto em 'diff')" % cwd)
        return _j(out)
    if _flag(args, "dryRun"):
        return _j(out)
    # PROOF-LINT-03 (A): author por execução — cada prova cmd roda 1x ANTES de gravar
    # (expect_exit/timeout/evidence_tail medidos, nunca de memória); diff recalculado.
    reh = va.rehearse(prop["manifest"], va.run_rehearsal)
    new = va.render(reh["manifest"])
    note = str(args.get("note") or "").strip()
    out.update(diff=va.diff(old, new, path), rehearsals=reh["rehearsals"])
    if reh["nonzero"]:
        if not (_flag(args, "force") and note):
            out.update(ok=False, error="REHEARSAL_EXIT_NONZERO",
                       detail="prova(s) cmd %s saíram com exit real ≠ 0 no rehearsal — não gravo "
                              "sem force=true + note (motivo)" % reh["nonzero"])
            return _j(out)
        for i in reh["nonzero"]:
            reh["manifest"]["cmd"][i]["rehearsal_note"] = note
        new = va.render(reh["manifest"])
        out["diff"] = va.diff(old, new, path)
    try:
        tmp = path + ".tmp-author"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, path)
    except Exception as e:
        return _err("WRITE_FAILED", str(e)[:400])
    out["written"] = True
    mc.append_event(mission_id, ledger.get("paneId"), "verify_manifest_authored",
                    "%s %s" % (path, json.dumps(prop["provenance"], sort_keys=True)))
    try:
        out["verify"] = json.loads(handle_mission_verify(
            {"missionId": mission_id, "manifest": path,
             "timeoutMs": 1000 * _dv_close_timeout(cwd, mission_id, ledger.get("extraDirs"))}))
    except Exception as e:
        out["verify"] = {"ok": False, "error": "VERIFY_BAD_OUTPUT", "detail": str(e)[:400]}
    return _j(out)



# ---------------------------------------------------------------- registration

def handle_mission_report_ack(args: Dict[str, Any], **_kw) -> str:
    """GUARD-SUPERVISOR-READONLY-01 (RELATÓRIO-INTEGRA, ordem do operator 04/10):
    o supervisor registra que o RELATORIO-<missionId>.md foi colado NA ÍNTEGRA
    no chat (leitura mission_read + conteúdo literal, não resumo/caminho).
    Grava evento tipado relatorio_integra_delivered no events.jsonl + spool;
    idempotente. Sem o ack, todo close da missão emite relatorio_integra_missing.
    SEC-OPERATOR-IDENTITY-01: report_ack é AÇÃO DE CONSEQUÊNCIA (muta o
    events.jsonl) — chamador supervisor exige token de ordem verificado
    (OPERATOR_ORDER_UNVERIFIED sem token; daemon/direct/worker não-supervisor
    passa — compat do fluxo registrado)."""
    mission_id = str(args.get("missionId") or "").strip()
    if e := mc.validate_mission_id(mission_id):
        return _err("INVALID_MISSION_ID", e)
    ledger = mc.load_ledger(mission_id)
    if ledger is None:
        return _err("MISSION_NOT_FOUND", "nenhum ledger para %s" % mission_id)
    # RD-GUARD-CLOSE-STATE-01 (04/10): o guard passa a ver o ledger — isenção
    # de fluxo registrado (chatDeliverable.delivered: true OU registro prévio
    # da colagem); sem entrega registrada, recusa tipada mantida.
    _gref = sg.assert_action_allowed("report_ack", args, ledger=ledger,
                                     spool_path=_MISSION_SPOOL)
    if _gref:
        return _err(_gref["code"], _gref["detail"])
    pane_id = str(args.get("paneId") or "").strip() or None
    out = sg.register_integra_ack(mission_id, pane_id=pane_id, spool_path=_MISSION_SPOOL)
    return _j(out)


def handle_mission_approval_request(args: Dict[str, Any], **_kw) -> str:
    """GUARDIAN-MOBILE-01: declara pedido de aprovação de consequência (intent
    tipado: missão, ação, alvo, custo/risco DECLARADO) e pede o card ao gateway
    Telegram (inline keyboard APROVAR/CANCELAR). Toque = ordem: APROVAR injeta
    operatorOrder verificado no intent + ledger (identidade via
    SEC-OPERATOR-IDENTITY-01); CANCELAR registra cancelamento tipado; sem toque
    no TTL (30 min) permanece pendente — NUNCA executa por default. Sem gateway
    Telegram ativo → canal "inactive" com razão honesta; aprovação continua
    disponível via supervisor (fallback nunca silencioso). Criar o pedido NUNCA
    concede (anti-self-approve)."""
    return _j(ac.create_approval(args))


def handle_mission_approval_status(args: Dict[str, Any], **_kw) -> str:
    """GUARDIAN-MOBILE-01: leitura tipada do estado do approval card (por
    approvalId ou missão mais recente) — pending/approved/cancelled, ordem
    injetada, entrega do card, nota honesta de TTL vencido. Sem mutação."""
    return _j(ac.approval_status(args))


def handle_findings_register(args: Dict[str, Any], **_kw) -> str:
    """FINDINGS-01: append de 1 finding no registry (catálogo como dado,
    custo-zero). Schema tipado {id, ts, origem, severidade, componente, texto,
    status:open}; id determinístico FIND-<8hex>; texto repetido em aberto =
    no-op idempotente. Registry segue o bus do processo (env > _MISSION_SPOOL)."""
    return _j(fd.register(
        str(args.get("texto") or ""),
        str(args.get("origem") or args.get("missionId") or "desconhecida"),
        severidade=str(args.get("severidade") or "P2"),
        componente=(args.get("componente") or None),
        registry=_findings_registry()))


def handle_findings_resolve(args: Dict[str, Any], **_kw) -> str:
    """FINDINGS-01: resolve 1 finding (open → resolved) no close da missão que o
    tratou — finding só sai por missão fechada (resolvedBy = missionId)."""
    return _j(fd.resolve(str(args.get("findingId") or ""),
                         str(args.get("missionId") or ""),
                         registry=_findings_registry()))


def handle_findings_digest(args: Dict[str, Any], **_kw) -> str:
    """FINDINGS-01: painel findings-open / findings-velhos (>3d) /
    findings-viraram-missão (resolved com resolvedBy). action=digest (default)
    só lê; action=aging roda o envelhecimento idempotente (>3d prio 2; >7d P1 +
    evento no bus 1x por hash) — o mesmo ciclo do timer systemd diário."""
    action = str(args.get("action") or "digest").strip().lower()
    if action == "aging":
        return _j(fd.aging_scan(registry=_findings_registry(),
                                bus=_MISSION_SPOOL))
    return _j(fd.digest(registry=_findings_registry()))


def handle_mission_debt(args: Dict[str, Any], **_kw) -> str:
    """RD-DEBT-01 (DEBT-SWEEP-01): consulta e manutenção mecânica do registry de
    dívidas herdadas (/root/.hermes/mission-state/debts.jsonl). Zero LLM.
    Ações:
      list (default) — painel do operator: abertas/queued/gate-operator com idade,
                       prioridade, fontes; filtros status/component/minAgeDays.
      aging          — envelhecimento idempotente: >3 dias prio 2, >7 dias P1 +
                       finding debt_aging no bus (uma vez por dívida).
      cited          — ordem do operator citando a dívida (texto) → P1 mecânico
                       via registry lookup (token DEBT-<8hex> ou texto normalizado).
    A captura/promoção/fecho NÃO passam aqui — vivem no passo debt_sweep do
    mission_close (fail-open). Mutação idempotente e atômica; nunca levanta."""
    action = str(args.get("action") or "list").strip().lower()
    try:
        if action == "list":
            _min_age = args.get("minAgeDays")
            try:
                _min_age = float(_min_age) if _min_age is not None else None
            except (TypeError, ValueError):
                return _err("BAD_REQUEST", "minAgeDays deve ser número")
            res = mdb.list_debts(status=args.get("status"),
                                 component=args.get("component"),
                                 min_age_days=_min_age)
            return _j(res)
        if action == "aging":
            return _j(mdb.aging_scan())
        if action == "cited":
            text = str(args.get("text") or "").strip()
            if not text:
                return _err("BAD_REQUEST",
                            "action=cited exige text (fala do operator citando a dívida)")
            return _j(mdb.cite(text))
        return _err("BAD_REQUEST",
                    "action desconhecida: %s (use list|aging|cited)" % action)
    except Exception as e:
        return _j({"ok": False, "error": str(e)[:200]})  # fail-open, nunca crash


def _handle_mission_obey(args: Dict[str, Any], **_kw) -> str:
    """RD-OBEY-02 (item 5): superfície do score de obediência do supervisor.
    action=score (default, read-only) — % closes com chatIntegra, % ordens
    cumpridas, violações por ordem (hoje/7d) + estado do ack/stale. action=stale
    — comparação determinística de hash. action=ack — re-ack explícito.
    Zero LLM; fail-open (nunca levanta)."""
    action = str(args.get("action") or "score").strip().lower()
    try:
        if action == "score":
            return _j(obr.score())
        if action == "stale":
            return _j(obr.check_stale(spool_path=_MISSION_SPOOL))
        if action == "ack":
            return _j(obr.sup_ack(spool_path=_MISSION_SPOOL, force=True))
        return _err("BAD_REQUEST",
                    "action desconhecida: %s (use score|stale|ack)" % action)
    except Exception as e:
        return _j({"ok": False, "error": str(e)[:200]})  # fail-open, nunca crash


def _schema(name: str, desc: str, props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}


# ---- RD-DESP-FAST-01 (09/10/2026): tool mission_launch — despacho determinístico
# pelo script despachar_missao.py (sem LLM, ~1 s de validação + despacho systemd-run).
_LAUNCH_SCRIPT = '/opt/mission-events/scripts/despachar_missao.py'
_LAUNCH_AUDIT = '/opt/mission-events/launch-audit.jsonl'
_RE_CONTRATO = re.compile(r'^/opt/mission-events/missao-[A-Za-z0-9._-]+\.md$')
_RE_WT = re.compile(r'^/home/worker/wt-[A-Za-z0-9._-]+$')
_RE_SETENV = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=[A-Za-z0-9._:/,@+-]*$')


def handle_mission_launch(args: Dict[str, Any], **_kw) -> str:
    contrato = str(args.get("contrato") or "").strip()
    worktree = str(args.get("worktree") or "").strip()
    if not (_RE_CONTRATO.match(contrato) and os.path.isfile(contrato)):
        return _err("CONTRATO_INVALIDO", contrato)
    if not (_RE_WT.match(worktree) and os.path.isdir(worktree)
            and os.path.exists(os.path.join(worktree, ".git"))):
        return _err("WORKTREE_INVALIDO", worktree)

    dry_run = bool(args.get("dryRun"))
    operator_order = str(args.get("operatorOrder") or "").strip()
    if not dry_run and not operator_order:
        return _err("OPERATOR_ORDER_REQUIRED",
                    "sem dryRun, mission_launch exige operatorOrder do operator")

    cmd = ["python3", _LAUNCH_SCRIPT, contrato, worktree]
    for flag, name, cast in (("--budget", "budget", float), ("--turns", "turns", int),
                             ("--retry", "retry", int), ("--seed", "seed", int)):
        if name in args and args.get(name) is not None:
            try:
                cmd += [flag, str(cast(args[name]))]
            except (TypeError, ValueError):
                return _err("BAD_ARG:" + name, str(args.get(name)))
    for kv in (args.get("setenv") or []):
        kv = str(kv).strip()
        if not _RE_SETENV.match(kv):
            return _err("BAD_ARG:setenv", kv[:80])
        cmd += ["--setenv", kv]
    if dry_run:
        cmd.append("--dry-run")
    if args.get("semBaseline"):
        cmd.append("--sem-baseline")

    try:
        proc = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return _err("SCRIPT_EXEC_FAILED", str(e)[:200])
    lines = [l for l in (proc.stdout or "").splitlines() if l.strip()]
    if not lines:
        return _err("SCRIPT_SEM_JSON", (proc.stderr or "")[:200])
    try:
        result = json.loads(lines[-1])
    except Exception:
        return _err("SCRIPT_SEM_JSON", (proc.stderr or "")[:200])

    # trilha de auditoria (best-effort, nunca derruba o retorno)
    try:
        os.makedirs(os.path.dirname(_LAUNCH_AUDIT), exist_ok=True)
        with open(_LAUNCH_AUDIT, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({
                "ts": mc._now(), "tool": "mission_launch", "contrato": contrato,
                "worktree": worktree, "dryRun": dry_run,
                "operatorOrder": operator_order[:200], "ok": bool(result.get("ok")),
                "id": result.get("id"), "unit": result.get("unit")},
                ensure_ascii=False) + "\n")
    except Exception:
        pass
    result["via"] = "mission_launch"
    return _j(result)


def register(ctx):
    global _ctx
    _ctx = ctx
    # GUARD-SUPERVISOR-READONLY-01: register(ctx) roda SÓ no processo do gateway
    # hermes (loader de plugins) — marca o canal deste processo como canal do
    # supervisor para a guarda determinística (contexto de execução, não payload).
    sg.mark_gateway_booted()
    from mission_ops_skill_delete_guard import guard_skill_manage_delete  # MOPS-SKILL-DELETE-GUARD-01
    ctx.register_hook("pre_tool_call", guard_skill_manage_delete)  # MOPS-SKILL-DELETE-GUARD-01
    # GB-JAULA-02: jaula real do operator — bloqueia em pre_tool_call (ver ordens_jaula.py)
    import logging as _logging
    try:
        from ordens_jaula import jaula_pre_tool_call
        ctx.register_hook("pre_tool_call", jaula_pre_tool_call)
    except Exception as _e:
        _logging.getLogger("mission-ops").error("jaula não registrada: %s", _e)
    register_tool = ctx.register_tool
    toolset = "mission-ops"

    # ---- SUP-OBEY-01 (boot): OBRIGACOES.md — fonte única das ordens permanentes do
    # operator ao supervisor — carregado no boot do plugin e injetado no contexto do
    # supervisor via bus (evento obrigacoes_boot com o bloco INTEGRAL, sem cap —
    # differ de _spool_gpu_event que corta em 400). Fail-open: arquivo ausente nunca
    # derruba o registro das tools.
    try:
        _boot = ob.boot_context()
        if _boot:
            os.makedirs(os.path.dirname(_MISSION_SPOOL), exist_ok=True)
            with open(_MISSION_SPOOL, "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"ts": mc._now(), "event": "finding",
                                     "kind": "obrigacoes_boot",
                                     "mission_id": "supervisor", "detail": _boot,
                                     "source": "mission-ops:obedience"},
                                    ensure_ascii=False) + "\n")
    except Exception:
        pass  # guard de obediência é best-effort no boot

    # ---- RD-OBEY-02 (SUP-ACK no boot): registry das ordens numeradas (O1, O2, …)
    # parseado + hash de versão (`obligationsHash`) — ack gravado no bus
    # (`sup_ack {orders, hash}`) e no state (obey-ack.json). Watchdog compara o
    # hash: ordem nova desde o último ack = finding `obligation_stale` até novo
    # ack (novo boot re-acka). Fail-open: ack é best-effort.
    try:
        obr.sup_ack(spool_path=_MISSION_SPOOL)
    except Exception:
        pass  # ack de obediência é best-effort no boot

    # ---- RD-OBEY-02: superfície do score de obediência (read-only, dado pronto
    # para o painel do operator).
    register_tool(
        "mission_obey", toolset,
        _schema("mission_obey",
                "RD-OBEY-02: obediência do supervisor por MECANISMO (zero LLM). "
                "action=score (default, read-only): % closes com relatório entregável "
                "ao chat (chatIntegra), % ordens cumpridas e violações por ordem "
                "(O1: n, …) por janela (hoje/7d) + estado do sup_ack/obligation_stale "
                "+ obligationsHash. action=stale: compara o hash do OBRIGACOES.md com "
                "o último sup_ack (finding obligation_stale até novo ack). action=ack: "
                "re-ack explícito (boot já acka; use após mudança de ordens sem restart). "
                "Violations viram dívida tipada `obedience` P1 com intent automático na "
                "fila (mission_debt component=obedience lista).",
                {"action": {"type": "string", "enum": ["score", "stale", "ack"]}},
                []),
        _handle_mission_obey)

    register_tool(
        "mission_dispatch", toolset,
        _schema("mission_dispatch",
                "Cria ABA PRÓPRIA no herdr (tab create + rename MISSION:<id>), abre claude no cwd "
                "escolhido e entrega o prompt com retry (deliver_prompt: send-text + enter + "
                "verificação de aceitação). Grava ledger. Idempotente: missão ativa -> no_op; "
                "status prompt_failed -> re-tenta a entrega no pane existente. Split do "
                "sourcePaneId só como fallback (tab create falho).",
                {"missionId": {"type": "string"},
                 "promptFile": {"type": "string", "description": "caminho absoluto do prompt em arquivo"},
                 "cwd": {"type": "string", "description": "diretório de trabalho do claude (default: pasta do promptFile; passe o projeto com config quando exigido)"},
                 "paneTitle": {"type": "string"},
                 "direction": {"type": "string", "description": "só usado no fallback de split: right|down"},
                 "sourcePaneId": {"type": "string", "description": "deprecated — só para fallback"},
                 "engine": {"type": "string", "description": "gpu = GPU elástica: gpu-up antes do pane (fail-open), claude apontado na ponte Qwen 8102, gpu-down no mission_close (garfo anti-thrash)", "enum": ["gpu"]},
                 "consequence": {"type": "boolean", "description": "escopo de infra de consequência (systemd/produção/deploy). true = mission_close EXIGE verify.json (sem ele reabre com verify_required); false = desliga a heurística. Omitido: `consequence: true|false` no prompt, senão heurística regex (só warning)"},
                 "spawnedBy": {"type": "string", "description": "emissor: operator | supervisor:hermes (default no gateway) | <missionId> do worker despachante. Pane do chamador = pane de missão viva vence a declaração. Worker só despacha com `allow_chain_dispatch: true` no prompt dele e até mission.chain_depth_max (config.yaml, default 1) — senão recusa CHAIN_DISPATCH_NOT_ALLOWED/CHAIN_DEPTH_EXCEEDED. ORCH-CHAIN-CWD-01: com chainBasis=payload (consume do orquestrador), spawnedBy do payload vence SEMPRE — ambiente (pane) nunca decide; declaração vazia recusa CHAIN_PARENT_UNKNOWN"},
                 "chainBasis": {"type": "string", "description": "auto (default, legado: pane vence) | payload (consume: pai da cadeia EXCLUSIVAMENTE do spawnedBy declarado — ambiente nunca decide)", "enum": ["auto", "payload"]}},
                ["missionId", "promptFile"]),
        handle_mission_dispatch)

    # ---- RD-DESP-FAST-01: despacho rápido pelo chat via script determinístico
    register_tool(
        "mission_launch", toolset,
        _schema("mission_launch",
                "Despacha missão do harness em ~1 s (sem LLM): contrato "
                "/opt/mission-events/missao-*.md + worktree /home/worker/wt-*; exige "
                "operatorOrder (dryRun dispensa). Roda despachar_missao.py (root): "
                "valida stops, baseline em paralelo, systemd-run --collect, espelho "
                "herdr, ledger. Retorno: JSON {ok, id, unit, seed, tab, run_dir, ...}.",
                {"contrato": {"type": "string", "description": "/opt/mission-events/missao-<id>.md"},
                 "worktree": {"type": "string", "description": "/home/worker/wt-<id> (com .git)"},
                 "budget": {"type": "number"},
                 "turns": {"type": "integer"},
                 "retry": {"type": "integer"},
                 "seed": {"type": "integer"},
                 "setenv": {"type": "array", "items": {"type": "string"},
                            "description": "K=V (sem espaços/;)"},
                 "dryRun": {"type": "boolean", "description": "dispensa operatorOrder"},
                 "semBaseline": {"type": "boolean"},
                 "operatorOrder": {"type": "string", "description": "ordem do operator (obrigatória sem dryRun)"}},
                ["contrato", "worktree"]),
        handle_mission_launch)

    register_tool(
        "mission_batch", toolset,
        _schema("mission_batch",
                "MISSION-BATCH-01: despacha 2-6 missões numa chamada só (zero LLM entre elas), "
                "SEQUENCIAL (herdr single-writer) via mission_dispatch por item. Tolera falha "
                "individual (segue a lista). Anti-fantasma: ledger dispatching/failed/interrupted "
                "com pane morto vira cancelled (reason automática) e é re-despachado no lote. "
                "Retorno: {despachadas, falhas, fantasmasLimpos, tempoTotalS, tempoPorMissao, "
                "itens[{missionId, result: ok|erro|fantasma-limpo, ...}]}.",
                {"manifest": {"type": "string", "description": "caminho do manifesto .json/.yaml (lista de {missionId, promptFile, cwd, consequence?} ou {missions: [...]}) — ou o próprio texto JSON/YAML"},
                 "missions": {"type": "array", "items": {"type": "object"},
                              "description": "alternativa inline ao manifest: lista de {missionId, promptFile, cwd, consequence?, engine?, paneTitle?, spawnedBy?}"}},
                []),
        handle_mission_batch)

    register_tool(
        "mission_snapshot", toolset,
        _schema("mission_snapshot",
                "SNAPSHOT-FAST-01: estado VERDADEIRO da missão em 1 chamada (zero LLM, ~1 tab list "
                "+ 1 pane list): ledger + pane REAL (existe? agent/agent_status? cwd? label) + "
                "verdict OK|PANEID_OBSOLETO|FANTASMA|INTERROMPIDA (+ DESPACHANDO/DESCONHECIDO) + "
                "remédio. AUTO-CORREÇÃO só no ledger: pane inexistente + aba MISSION:<id> viva -> "
                "re-sincroniza paneId/tabId; sem aba -> cancela o fantasma. Nunca escreve em pane "
                "nem fecha aba. Retorno: {missions[], fixed[], ghosts[], summary{fixed,ghosts,ok}}. "
                "Use para 'verifique a missão X' no lugar de status+read+pane get.",
                {"missionId": {"type": "string", "description": "id exato (não achou = sugere parecidas)"},
                 "fragment": {"type": "string", "description": "trecho do id, tolerante a typo (substring ou difflib >= 0.8), ex. 'watchhdog'"}},
                []),
        handle_mission_snapshot)

    register_tool(
        "mission_watch", toolset,
        _schema("mission_watch",
                "Watchdog orientado a evento (herdr pane wait-output — nunca polling). Detecta: "
                "Interrupted, API Error 400, palette aberta, 'Relatório final'/FINGERPRINT, pane "
                "virou shell, ready_regex_error (claude parou em tela de erro/trust), pane_closed/"
                "tab_closed (missão encerrada de fora). Cada evento atualiza ledger + events.jsonl "
                "e aplica receita quando segura (interrupted/palette).",
                {"missionId": {"type": "string"},
                 "all": {"type": "string", "description": "true = todas as missões ativas"},
                 "timeoutMs": {"type": "integer", "description": "single: tempo de espera do evento (default 60000, max 600000)"},
                 "perPaneTimeoutMs": {"type": "integer", "description": "all: timeout por pane (default 10000)"}},
                []),
        handle_mission_watch)

    register_tool(
        "mission_recover", toolset,
        _schema("mission_recover",
                "Receitas DETERMINÍSTICAS (zero LLM): interrupted (Esc+continue+Enter), palette (Esc), "
                "transcript400 (sessão nova enxuta — nunca retomar a envenenada), shell_fallback "
                "(claude --resume do ledger ou nova sessão), autocompact (só marca), ready_regex_error "
                "(relança claude no cwd correto e re-entrega o prompt; cwd do arg prevalece sobre o "
                "ledger). Desconhecido -> needs_supervisor.",
                {"paneId": {"type": "string"},
                 "pattern": {"type": "string"},
                 "missionId": {"type": "string"},
                 "cwd": {"type": "string", "description": "ready_regex_error: cwd com config do projeto (prevalece sobre o ledger)"},
                 "operatorOrder": {"type": "string", "description": "GUARD-SUPERVISOR-READONLY-01: referência explícita da ordem do operator — exigida quando o chamador é supervisor e o ledger não está marcado needs_recovery (isenção do watcher)"}},
                ["paneId", "pattern"]),
        handle_mission_recover)

    register_tool(
        "mission_status", toolset,
        _schema("mission_status",
                "Estado da missão em 1 chamada (resposta a 'onde estávamos', sobrevive a restart do "
                "chat): {missionId, paneId, tabId, status, lastEventAt, resumeSessionId, cwd}. "
                "Sem missionId = todas, em modo COMPACTO por default: 1 linha por missão ativa "
                "(id | status | último evento + idade | pendência) + resumo das encerradas "
                "(contagem + últimas 5). full=true (ou verbose=true): ledger completo. compact=true: formato do "
                "watchdog (só não-closed + contadores). Com missionId: registro completo.",
                {"missionId": {"type": "string"},
                 "full": {"type": "boolean", "description": "ledger completo de todas as missões"},
                 "verbose": {"type": "boolean", "description": "alias de full=true"},
                 "compact": {"type": "boolean", "description": "formato watchdog: só não-closed + contadores (opt-in)"}}, []),
        lambda args, **kw: handle_mission_status(args, _view_default="chat", **kw))

    register_tool(
        "mission_read", toolset,
        _schema("mission_read",
                "pane read com tail/bytes (substitui o herdr manual de verificação). Resolve pane "
                "via missionId ou paneId direto. lines clamp 1..2000; source: visible|recent|"
                "recent-unwrapped|detection; maxBytes corta a CAUDA (mantém o fim) e marca truncated.",
                {"missionId": {"type": "string"},
                 "paneId": {"type": "string"},
                 "lines": {"type": "integer"},
                 "source": {"type": "string"},
                 "maxBytes": {"type": "integer"}},
                []),
        handle_mission_read)

    register_tool(
        "mission_nudge", toolset,
        _schema("mission_nudge",
                "MISSION-NUDGE-01: intervenção do SUPERVISOR — nudge atômico CHECK->SEND->VERIFY. "
                "CHECK: lê o pane e recusa em working ATIVO sem force (não interrompe turno em "
                "curso) e recusa 2º nudge <60s sem force (dedupe). SEND: send-text+enter com "
                "sender declarado (default supervisor:hermes, logado no audit de pane-writes). "
                "VERIFY: espera verifySeconds (default 30) e re-lê o pane — engatou working ? "
                "nudged : engage_failed com o texto do pane, SEM reenvio. Nunca fecha missão, "
                "nunca envia em pane de missão sem ledger. Nunca substitui o watchdog (decisão "
                "de curso do supervisor, não patologia).",
                {"missionId": {"type": "string"},
                 "message": {"type": "string"},
                 "sender": {"type": "string", "description": "identidade do emissor no audit"},
                 "force": {"type": "boolean", "description": "bypassa recusa busy/dedupe"},
                 "verifySeconds": {"type": "integer"},
                 "operatorOrder": {"type": "string", "description": "GUARD-SUPERVISOR-READONLY-01: referência explícita da ordem do operator — SEMPRE exigida quando o chamador é supervisor (nudge nunca é passo de automação registrada)"}},
                ["missionId", "message"]),
        handle_mission_nudge)

    register_tool(
        "mission_list", toolset,
        _schema("mission_list",
                "Superfície completa do herdr + ledgers numa resposta só: tab list + pane list + "
                "todas as missões registradas com liveness (pane vivo? agent_status? label da aba?). "
                "Falhas parciais do herdr viram warnings sem derrubar a resposta. Default COMPACTO: "
                "1 linha por missão ativa (id | status | último evento + idade | pane viva/MORTA/? "
                "| pendência) + resumo das encerradas (contagem + últimas 5). full=true (ou verbose=true): resposta "
                "completa (tabs/panes/todas as missões). compact=true: formato do watchdog.",
                {"full": {"type": "boolean", "description": "resposta completa (todas as missões + totais herdr)"},
                 "verbose": {"type": "boolean", "description": "alias de full=true"},
                 "compact": {"type": "boolean", "description": "formato watchdog: só não-closed + contadores (opt-in)"}}, []),
        lambda args, **kw: handle_mission_list(args, _view_default="chat", **kw))

    register_tool(
        "mission_close",
        toolset,
        _schema("mission_close",
                "Encerramento limpo da missão: DELIVER-VERIFY (se o cwd da missão tem verify.json, "
                "roda o runner determinístico; VERDE grava badge verified_e2e, VERMELHO reabre a "
                "missão com evento deliver_verify_red no bus) -> /exit no claude (confirmado) -> "
                "tab close -> worktree cleanup (só se gravado no ledger) -> ledger status closed. "
                "GUARDA DE CONSEQUÊNCIA: missão com consequence declarada e sem verify.json é "
                "reaberta (verify_required); consequência só heurística fecha com evento "
                "closed_unverified_consequence + warning. GUARD CLOSE-COMMIT-01: se o cwd do "
                "ledger é repo git com entrega não-commitada (deploy paths / novos do componente "
                "/ RELATORIO), bloqueia o badge verified_e2e, grava closeWarning acionável e faz "
                "auto-nudge ao worker — nunca auto-commita. Resolve por missionId ou paneId.",
                {"missionId": {"type": "string"},
                 "paneId": {"type": "string"},
                 "acceptUnverified": {"type": "string", "description": "motivo auditável para fechar missão de consequência declarada SEM verify.json (vira closed_unverified_consequence)"},
                 "force": {"type": "string", "description": "passa --force no worktree remove"},
                 "resolveFindings": {"type": "string", "description": "FINDINGS-01: id(s) FIND-<8hex> (um ou CSV) que ESTA missão tratou — o close resolve os findings no registry (findings_resolve; fail-open, step findings_register)"},
                 "operatorOrder": {"type": "string", "description": "GUARD-SUPERVISOR-READONLY-01: referência explícita da ordem do operator (missionId do contrato SHIP vigente ou token de ordem) — exigida quando o chamador é supervisor fora de fluxo registrado (ledger awaiting_close/verify verde/dryRun)"}},
                []),
        handle_mission_close)

    register_tool(
        "mission_verify", toolset,
        _schema("mission_verify",
                "SUPERVISOR-VERIFY-01/DELIVER-VERIFY-01: verificação determinística (zero LLM) da "
                "entrega — roda /opt/deliver-verify/verify.py (manifesto verify.json do cwd da "
                "missão ou bateria inferida por tipo de entrega). Somente leitura fora do "
                "relatório. Retorno: JSON {missionId, source, verdict, checks[]}.",
                {"missionId": {"type": "string"},
                 "manifest": {"type": "string",
                              "description": "verify.json alternativo (default: cwd da missão)"}},
                ["missionId"]),
        handle_mission_verify)

    register_tool(
        "mission_verify_author", toolset,
        _schema("mission_verify_author",
                "VERIFY-MANIFEST-01: GERA o verify.json da missão a partir de prova REAL — "
                "relatório no cwd (RELATORIO-<id>.md/relatorio-<id>.md: comandos read-only, "
                "arquivos e units citados que existem) > aceite do prompt missao-<id>.md > "
                "fallback do runner. Cada item leva _provenance (report|prompt|inferred) e "
                "_source; nunca inventa spec. Sem relatório: recusa (NO_REPORT). verify.json "
                "existente: recusa sem force (VERIFY_JSON_EXISTS). Resposta traz o diff do "
                "proposto; após gravar roda mission_verify no manifesto novo.",
                {"missionId": {"type": "string"},
                 "force": {"type": "boolean", "description": "sobrescreve verify.json existente"},
                 "dryRun": {"type": "boolean", "description": "só mostra diff/proposto, não grava"},
                 "cwd": {"type": "string", "description": "cwd alternativo (default: cwd do ledger)"}},
                ["missionId"]),
        handle_mission_verify_author)

    register_tool(
        "mission_worktree_add", toolset,
        _schema("mission_worktree_add",
                "herdr worktree create ligado ao ciclo da missão (branch obrigatório; grava "
                "worktreePath/Branch/WorkspaceId no ledger). Recusa se o ledger já grava outro "
                "worktree.",
                {"missionId": {"type": "string"},
                 "branch": {"type": "string"},
                 "path": {"type": "string"},
                 "base": {"type": "string"},
                 "label": {"type": "string"}},
                ["missionId", "branch"]),
        handle_mission_worktree_add)

    register_tool(
        "mission_worktree_remove", toolset,
        _schema("mission_worktree_remove",
                "herdr worktree remove APENAS do worktree gravado no ledger (nunca remove às "
                "cegas). force=true passa --force.",
                {"missionId": {"type": "string"},
                 "force": {"type": "string"}},
                ["missionId"]),
        handle_mission_worktree_remove)

    register_tool(
        "mission_report_ack", toolset,
        _schema("mission_report_ack",
                "GUARD-SUPERVISOR-READONLY-01 (RELATÓRIO-INTEGRA, ordem do operator): registra "
                "que o RELATORIO-<missionId>.md foi colado NA ÍNTEGRA no chat do supervisor "
                "(leitura mission_read + conteúdo literal; nunca só resumo ou caminho). Grava "
                "evento tipado relatorio_integra_delivered no events.jsonl + spool; idempotente. "
                "Sem o ack, o close emite relatorio_integra_missing até a colagem ser registrada. "
                "SEC-OPERATOR-IDENTITY-01: ação de CONSEQUÊNCIA — chamador supervisor exige "
                "token de ordem verificado em operatorOrder (recusa OPERATOR_ORDER_UNVERIFIED).",
                {"missionId": {"type": "string"},
                 "paneId": {"type": "string", "description": "opcional — pane de origem do registro"},
                 "operatorOrder": {"type": "string", "description": "SEC-OPERATOR-IDENTITY-01: token de ordem do operator — exigido quando o chamador é supervisor (report_ack muta o events.jsonl)"}},
                ["missionId"]),
        handle_mission_report_ack)

    # ---- GUARDIAN-MOBILE-01: approval cards no Telegram (toque = ordem) ----
    try:
        # Fábrica nativa do telegram (PTB): handlers com prefixo exclusivo
        # gmob01: (CallbackQueryHandler pattern + textos APROVAR/CANCELAR) —
        # callbacks de outros componentes seguem para o handler do core.
        # Gateway sem a API/PTB → no-op honesto (canal inactive no card).
        ctx.register_platform_handler("telegram", ac.telegram_handler_factory)
    except AttributeError:
        pass  # ctx antigo sem register_platform_handler — fallback honesto via supervisor
    except Exception:
        pass  # registro de handler é best-effort; aprovação via supervisor segue valendo

    register_tool(
        "mission_approval_request", toolset,
        _schema("mission_approval_request",
                "GUARDIAN-MOBILE-01: declara pedido de aprovação de consequência (resumo tipado: "
                "missão, ação, alvo, custo/risco DECLARADO) e pede o CARD ao gateway Telegram — "
                "mensagem com inline keyboard [APROVAR] [CANCELAR]. Toque = ordem: APROVAR injeta "
                "operatorOrder verificado no intent + ledger (identidade pela SEC-OPERATOR-IDENTITY-01: "
                "token de ordem ou chat_id allowlistado, resolvido server-side); CANCELAR registra "
                "cancelamento tipado com evidência; sem toque no TTL (30 min, config) permanece "
                "pendente — NUNCA executa por default (fail-closed). Sem gateway Telegram ativo o card "
                "marca canal inactive e a aprovação segue disponível via supervisor (fallback honesto). "
                "Use quando o guard recusar a mutação de consequência (OPERATOR_ORDER_UNVERIFIED / "
                "SUPERVISOR_ACTION_NEEDS_ORDER) e o operator estiver fora da VPS. Idempotente: já há "
                "pedido pendente da mesma missão+ação → devolve o existente e re-tenta o envio.",
                {"missionId": {"type": "string"},
                 "action": {"type": "string", "description": "ação pendente de aprovação (ex.: close, recover, dispatch-chain, comando tier-3)"},
                 "target": {"type": "string", "description": "alvo declarado da mutação (recurso/serviço/repo)"},
                 "costRisk": {"type": "string", "description": "custo/risco declarado — vai literal no card"},
                 "ttlMin": {"type": "string", "description": "TTL do card em minutos (default 30)"}},
                ["missionId", "action", "target"]),
        handle_mission_approval_request)

    register_tool(
        "mission_approval_status", toolset,
        _schema("mission_approval_status",
                "GUARDIAN-MOBILE-01: estado do approval card (por approvalId ou missão mais recente) — "
                "pending/approved/cancelled, ordem injetada (orderRef/basis/chatHash16), entrega do card, "
                "nota honesta de TTL vencido. O supervisor consulta após o toque para decidir executar "
                "a ação pendente (o guard aceita a base approval-card dentro da janela de validade).",
                {"missionId": {"type": "string"},
                 "approvalId": {"type": "string"}},
                []),
        handle_mission_approval_status)

    register_tool(
        "mission_debt", toolset,
        _schema("mission_debt",
                "RD-DEBT-01 (DEBT-SWEEP-01): ciclo de vida das dívidas herdadas — "
                "registry /root/.hermes/mission-state/debts.jsonl (zero LLM). "
                "action=list (default): painel do operator (abertas/queued/gate-operator "
                "com idade/prioridade/fontes; filtros status/component/minAgeDays). "
                "action=aging: envelhecimento idempotente (>3d prio 2; >7d P1 + finding "
                "debt_aging no bus, uma vez por dívida). action=cited: ordem do operator "
                "citando a dívida → P1 mecânico via registry lookup. Captura/promoção "
                "(intent dispatch_mission na fila ou gate-operator) e fecho (só por "
                "ledger PASS) rodam no passo debt_sweep do mission_close.",
                {"action": {"type": "string", "enum": ["list", "aging", "cited"]},
                 "status": {"type": "string", "description": "filtro list: open|queued|closed|gate-operator"},
                 "component": {"type": "string", "description": "filtro list por componente (substring)"},
                 "minAgeDays": {"type": "number", "description": "filtro list: idade mínima em dias"},
                 "text": {"type": "string", "description": "cited: fala do operator citando a dívida"}},
                []),
        handle_mission_debt)

    # ---- FINDINGS-01: tool de findings — registro, aging e digest (catálogo
    # como dado, custo-zero; registry findings.jsonl ao lado do bus do processo).
    register_tool(
        "findings_register", toolset,
        _schema("findings_register",
                "FINDINGS-01: append de 1 finding no registry findings.jsonl "
                "{id: FIND-<8hex>, ts, origem(missão), severidade(P1/P2/P3), "
                "componente, texto, status: open} — catálogo como dado, custo-zero. "
                "Idem determinístico do texto; texto repetido em aberto = no-op "
                "(idempotente). O mission_close também registra fontes "
                "determinísticas do fecho (fail-open, step findings_register).",
                {"texto": {"type": "string", "description": "o finding em 1 linha"},
                 "origem": {"type": "string", "description": "missão/fonte do finding (default missionId do chamador)"},
                 "severidade": {"type": "string", "enum": ["P1", "P2", "P3"], "description": "default P2"},
                 "componente": {"type": "string", "description": "componente afetado (ex. mission-ops)"}},
                ["texto"]),
        handle_findings_register)

    register_tool(
        "findings_resolve", toolset,
        _schema("findings_resolve",
                "FINDINGS-01: resolve 1 finding (open → resolved, resolvedBy = "
                "missionId) — use no close da missão que tratou o finding (ou "
                "declare resolveFindings no mission_close). Id inexistente = erro "
                "tipado; já resolvido por outra missão = recusa.",
                {"findingId": {"type": "string", "description": "id FIND-<8hex>"},
                 "missionId": {"type": "string", "description": "missão que tratou (resolvedBy)"}},
                ["findingId", "missionId"]),
        handle_findings_resolve)

    register_tool(
        "findings_digest", toolset,
        _schema("findings_digest",
                "FINDINGS-01: painel do catálogo — findings-open / findings-velhos "
                "(>3d) / findings-viraram-missão (resolved com resolvedBy). "
                "action=digest (default, leitura) | action=aging: envelhecimento "
                "idempotente (>3d prio 2; >7d P1 + evento findings_aging no bus 1x "
                "por hash) — mesmo ciclo do timer systemd diário (24h) e do hook do "
                "close. Digest semanal (domingo 08:00 BRT) roda no timer systemd.",
                {"action": {"type": "string", "enum": ["digest", "aging"]}},
                []),
        handle_findings_digest)
#!/usr/bin/env python3
"""GB-SALA-AO-VIVO-01: ponte espelho→office — workers reais na sala.

Daemon leve que varre os dirs de espelho (/tmp/ag-*, /tmp/mec-*) e injeta na
office viva, via mecanismo de eventos externo já suportado (event_inbox.publish
→ $HERMES_HOME/pixel-office/inbox, drenado pelo event_store em cada /state):

- session_start (platform="hermes") no primeiro sighting de cada *.espelho.json;
- tool_start derivado da ÚLTIMA linha relevante do sessao.log com o MESMO
  filtro do streamer do espelho (fala / patch / prova OK / FAIL);
- session_end quando o json ganhar veredito OU for renomeado para
  *.espelho.pousado.json (GB-SALA-PISO-02: pousado SAI do piso — a office
  remove o agente via session_end, mecanismo nativo do state_model).
- GB-SALA-GHOST-01: varredura retroativa de fantasmas — a cada varredura (e
-  portanto no start), toda sessão "started" da ponte cujo json corrente não
-  esteja running (ausente/.pousado.json/ilegível) recebe o session_end da v3
-  1x (idempotente em memoria+disco). Fantasma legado da ponte antiga sai.
- pausa GB-SALA-PISO-02: agente RUNNING que fica ~90s (PONTE_PAUSE_INTERVAL)
  sem linha nova no sessao.log recebe session_idle (evento válido do protocolo
  da office — mesmo que _post_llm_call emite; a sala mostra o agente parado).
  Quando o log mexe de novo, tool_start volta o agente a trabalhar ("mesa").

Idempotente: quem já entrou, atividade já vista e quem já encerrou não são
re-injetados (estado persistido em PONTE_STATE_FILE).

Env:
  ESPELHO_DIRS        globs separados por vírgula (default "/tmp/ag-*,/tmp/mec-*")
  HERMES_HOME         home da office (default ~/.hermes); dir de eventos = <home>/pixel-office
  AGENT_OFFICE_PORT   apenas informativo (a injeção é pelo inbox, não por HTTP)
  PONTE_STATE_FILE    estado de idempotência (default /tmp/ponte_office.estado.json)
  PONTE_SCAN_INTERVAL intervalo do loop em segundos (default 5)
  PONTE_PAUSE_INTERVAL  segundos SEM linha nova antes da pausa (default 90)

Uso: python3 ponte_office.py [--once]   (--once para prova hermética)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = os.path.dirname(os.path.abspath(__file__))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from event_inbox import publish  # noqa: E402  (mecanismo externo da office)

DEFAULT_DIRS = "/tmp/ag-*,/tmp/mec-*"
PLATFORM = "hermes"

# MESMO filtro do streamer (scripts/espelho.sh espelho__filtro), sem cores.
RE_VEREDITO = re.compile(r"VEREDITO (PASS|FAIL)")
RE_PATCH = re.compile(r"\| (Write|Edit|Patch) \||patch|git (add|commit)|\.diff")
RE_PROVA_OK = re.compile(r"RESUMO: 0 falhas|\bOK: |prova.*[Oo][Kk]|[Oo][Kk].*prova")
RE_FAIL = re.compile(r"RESUMO: [1-9][0-9]* falha|FAIL|FALHA|ERRO")
RE_FALA = re.compile(r"Hermes[>:]|\[.{1,20}BRT\] IN")
RE_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")
# GB-OFFICE-VIDA-01: linha real do trail "[12/10 13:41 BRT] turno 5 | Edit |
# 0ms | $0.00 | ERRO | arquivo" — extrai ferramenta, turno e custo.
RE_TRAIL = re.compile(r"\|\s*(\w[\w -]*?)\s*\|")
RE_CUSTO = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")
RE_TURNO = re.compile(r"turno\s+(\d+)")

# GB-STREAM-PTBR-01: dicionário compartilhado das labels inglesas do display
# da CLI -> PT-BR (mesma tabela de _espelho_parse.py / harness-s2 e app.js /
# guardian-app). Termos técnicos ficam intactos; só o TEXTO exibido muda.
PTBR_LABELS = [
    (re.compile(r"preparing terminal…?"), "abrindo terminal…"),
    (re.compile(r"preparing patch…?"), "escrevendo patch…"),
    (re.compile(r"preparing read_file…?"), "lendo arquivo…"),
    (re.compile(r"preparing write_file…?"), "escrevendo arquivo…"),
    (re.compile(r"preparing search_files…?"), "buscando arquivos…"),
    (re.compile(r"preparing execute_code…?"), "executando código…"),
    (re.compile(r"preparing skill_view…?"), "abrindo skill…"),
    (re.compile(r"preparing a patch is read-only"), "escrevendo patch…"),
    (re.compile(r"preparing (\S+)…?"), r"preparando \1…"),
    (re.compile(r"(?<![|\w])\$ (?=\S)"), "executando comando: "),
]


def traduz_ptbr(line: str) -> str:
    """Traduz as labels inglesas do stream para PT-BR."""
    out = line
    for pat, repl in PTBR_LABELS:
        out = pat.sub(repl, out)
    return out


def _relevant(line: str):
    """Classifica a última linha relevante do sessao.log (filtro do streamer)."""
    line = RE_ANSI.sub("", line)  # GB-OFFICE-VIDA-01: ANSI não quebra regex
    if "preparing terminal" in line or re.search(r"\$ true .*0\.0s", line):
        return None
    if RE_VEREDITO.search(line):
        return None  # veredito vem do .espelho.json, não do log
    # GB-OFFICE-VIDA-01: trail real "turno N | Tool | ... | $X | STATUS | alvo"
    m = RE_TRAIL.search(line)
    if m:
        tool = m.group(1).strip().lower()
        if tool in ("write", "edit", "patch"):
            return ("patch", "write_file", "typing")
        if tool == "bash":
            return ("bash", "terminal", "running")
        if tool in ("read", "read_file", "search", "search_files"):
            return ("read", "read_file", "working")
        if tool in ("message", "fala"):
            return ("fala", "message", "working")
    if RE_PATCH.search(line):
        return ("patch", "write_file", "typing")
    if RE_PROVA_OK.search(line):
        return ("prova_ok", "terminal", "running")
    if RE_FAIL.search(line):
        return ("fail", "terminal", "running")
    if RE_FALA.search(line):
        return ("fala", "message", "working")
    return None


def _dados_linha(line: str) -> dict:
    """GB-OFFICE-VIDA-01: dados reais do trail (custo, turno) da linha."""
    dados: dict = {}
    m = RE_CUSTO.search(line)
    if m:
        try:
            dados["custo_usd"] = float(m.group(1))
        except ValueError:
            pass
    m = RE_TURNO.search(line)
    if m:
        try:
            dados["turno"] = int(m.group(1))
        except ValueError:
            pass
    return dados


def _dados_linha(line: str) -> dict:
    """GB-OFFICE-VIDA-01: dados reais do trail (custo, turno) da linha."""
    dados: dict = {}
    m = RE_CUSTO.search(line)
    if m:
        try:
            dados["custo_usd"] = float(m.group(1))
        except ValueError:
            pass
    m = RE_TURNO.search(line)
    if m:
        try:
            dados["turno"] = int(m.group(1))
        except ValueError:
            pass
    return dados


def ultima_atividade(log_path: str):
    """Última linha relevante do sessao.log → (assinatura, tool, activity) | None."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            linhas = fh.readlines()
    except OSError:
        return None
    for line in reversed(linhas):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        kind = _relevant(line)
        if kind is not None:
            sig, tool, activity = kind
            return (f"{sig}:{line}", tool, activity)
    return None


def espelho_dirs() -> list[str]:
    pats = [p.strip() for p in os.environ.get(
        "ESPELHO_DIRS", DEFAULT_DIRS).split(",") if p.strip()]
    dirs: set[str] = set()
    for pat in pats:
        for d in glob.glob(pat):
            if os.path.isdir(d):
                dirs.add(d)
    return sorted(dirs)


def office_dir() -> str:
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    d = os.path.join(home, "pixel-office")
    os.makedirs(os.path.join(d, "inbox"), exist_ok=True)
    return d


def pause_interval() -> float:
    try:
        v = float(os.environ.get("PONTE_PAUSE_INTERVAL", "90") or 90)
    except ValueError:
        v = 90.0
    return max(v, 1.0)


def load_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            st = json.load(fh)
        if isinstance(st, dict):
            st.setdefault("last_change_ts", {})
            st.setdefault("reend_emit", {})  # GB-SALA-PISO-03
            return st
    except (OSError, ValueError):
        pass
    return {"started": [], "ended": [], "activity_sig": {}, "last_change_ts": {},
            "reend_emit": {}}


def save_state(path: str, st: dict) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(st, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def office_agentes(timeout: float = 2.0):
    """GB-SALA-PISO-03: snapshot id→status dos agentes na office VIVA.

    Consulta o /state da office (AGENT_OFFICE_PORT, default 8113). Retorna
    dict vazio se a office não responder (fail-open: a ponte nunca derruba
    ninguém — sem snapshot, não há re-encerramento nesta varredura).
    """
    port = os.environ.get("AGENT_OFFICE_PORT", "8113")
    try:
        import urllib.request
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/state", timeout=timeout) as r:
            st = json.loads(r.read().decode())
        return {str(a.get("id") or ""): str(a.get("status") or "")
                for a in st.get("agents", []) if isinstance(a, dict)}
    except Exception:
        return {}


def inject(event: dict) -> bool:
    try:
        event.setdefault("ts", time.time())
        event.setdefault("pid", os.getpid())
        publish(Path(office_dir()), event)
        return True
    except Exception as exc:  # fail-open: ponte nunca derruba ninguém
        print(f"ponte: falha ao injetar {event.get('event')}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def espelho_json(mid: str, dirs=None):
    """Json corrente (NÃO pousado) da sessão em qualquer dir de espelho.

    GB-SALA-PISO-03: `dirs` permite reusar a lista de dirs da varredura —
    chamar espelho_dirs() por sessão listava /tmp inteiro (~470k entradas)
    dezenas de vezes por varredura (~45s de CPU cada). Retorna
    (caminho, dict|None). None/None = nenhum .espelho.json presente.
    """
    for d in dirs if dirs is not None else espelho_dirs():
        p = os.path.join(d, f"{mid}.espelho.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    mir = json.load(fh)
            except (OSError, ValueError):
                return p, None
            return p, (mir if isinstance(mir, dict) else None)
    return None, None


def scan_once(st: dict, now: float | None = None) -> int:
    """Uma varredura; retorna nº de eventos injetados.

    `now` permite relógio simulado (provas herméticas); None = wall clock.
    """
    if now is None:
        now = time.time()
    n = 0
    dirs_cache = espelho_dirs()  # 1 listagem por varredura (não por sessão)
    for d in dirs_cache:
        # GB-POUSO-EXPIRA-01: o espelho.sh rename o json para
        # <ID>.espelho.pousado.json no pouso — a ponte precisa ver os DOIS nomes,
        # senão o session_end nunca sai e a sala guarda fantasma "trabalhando".
        # GB-SALA-PISO-02: o json pousado REMOVE o agente da sala.
        for ef in sorted(glob.glob(os.path.join(d, "*.espelho.json"))
                         + glob.glob(os.path.join(d, "*.espelho.pousado.json"))):
            try:
                with open(ef, "r", encoding="utf-8") as fh:
                    mir = json.load(fh)
            except (OSError, ValueError):
                continue
            if not isinstance(mir, dict):
                continue
            mid = str(mir.get("id") or "").strip()
            if not mid:
                continue
            pousado = ef.endswith(".espelho.pousado.json")
            if mid in st["ended"]:
                continue
            if mid not in st["started"]:
                if inject({"event": "session_start", "session_id": mid,
                           "platform": PLATFORM, "title": mid}):
                    st["started"].append(mid)
                    st["last_change_ts"][mid] = now
                    n += 1
            if mid in st["ended"]:
                continue
            act = ultima_atividade(os.path.join(d, "sessao.log"))
            if act is not None:
                sig, tool, activity = act
                if st["activity_sig"].get(mid) != sig:
                    # Log mexeu de novo: agente volta à mesa (trabalhando) e
                    # o relógio de pausa reinicia.
                    if inject({"event": "tool_start", "session_id": mid,
                                               "call_id": f"ponte-{mid}",
                                               "tool_name": tool, "activity": activity,
                                               # GB-STREAM-PTBR-01: preview em PT-BR na sala.
                                               "preview": traduz_ptbr(sig.split(":", 1)[1])[:60],
                                               # GB-OFFICE-VIDA-01: dados reais do trail.
                                               **_dados_linha(sig.split(":", 1)[1])}):
                        st["activity_sig"][mid] = sig
                        st["last_change_ts"][mid] = now
                        n += 1
            elif st["activity_sig"].get(mid) is None and not pousado:
                # Nenhuma atividade ainda: relógio de pausa parte da entrada.
                st["last_change_ts"].setdefault(mid, now)
            if pousado or mir.get("status") == "done" or mir.get("veredito"):
                verdict = str(mir.get("veredito") or mir.get("status") or "done")
                if inject({"event": "session_end", "session_id": mid,
                           "veredito": verdict,
                           # GB-OFFICE-VIDA-01: totais do json pousado.
                           "custo_usd": mir.get("custo_usd") or mir.get("custo_total"),
                           "turno": mir.get("turno")}):
                    st["ended"].append(mid)
                    n += 1
            elif (mid in st["started"]
                  and now - float(st["last_change_ts"].get(mid, now)) >= pause_interval()):
                # GB-SALA-PISO-02: ~90s sem linha nova → 1 evento de pausa
                # (session_idle, tipo válido do protocolo da office — o mesmo
                # que _post_llm_call publica; a sala mostra o agente parado).
                if inject({"event": "session_idle", "session_id": mid,
                           "platform": PLATFORM}):
                    st["last_change_ts"][mid] = now
                    n += 1

    # GB-SALA-GHOST-01: varredura retroativa de fantasmas. Agentes injetados
    # pela ponte antiga (ou em rodadas anteriores) podem não ter mais json
    # running — o loop acima só observa a transição json→pousado e os deixa
    # na sala para sempre. Aqui: toda sessão "started" da ponte cujo json
    # corrente NÃO esteja running (ausente, ilegível ou pousado) é fantasma
    # → o MESMO evento de fim da v3 (session_end), 1x, idempotente (marcado
    # em memoria + disco via st["ended"]/save_state). Fail-open: estado
    # ilegível → skip silencioso.
    if not isinstance(st.get("started"), list):
        return n
    # GB-SALA-PISO-03: fantasma ressuscitado. (snapshot da office buscado
    # UMA vez por varredura — o /state é caro: drena inbox + sqlite)
    snapshot = None
    for mid in list(st["started"]):
        path, mir = espelho_json(mid, dirs_cache)
        vivo = bool(path) and isinstance(mir, dict) and mir.get("status") == "running"
        if mid in st.get("ended", []):
            if vivo:
                # Ressurreição: o json voltou a running → o agente re-entra
                # na sala na mesma varredura (session_start de novo). O
                # marcador de re-encerramento é zerado: o CICLO recomeça.
                st["ended"].remove(mid)
                st["activity_sig"].pop(mid, None)
                st.setdefault("reend_emit", {}).pop(mid, None)
                if inject({"event": "session_start", "session_id": mid,
                           "platform": PLATFORM, "title": mid}):
                    st["last_change_ts"][mid] = now
                    n += 1
                continue  # (re)encerrado: nada mais a fazer nesta varredura
            # GB-SALA-PISO-03: fantasma ressuscitado. A ressurreição pode ter
            # re-adicionado o agente na office (session_start) e depois o json
            # encerrou de novo (done/pousado) — mas o session_end original já
            # foi marcado em st["ended"] e o ramo fazia `continue` ANTES de
            # re-emitir: o agente ficava na sala para sempre ("idle"). Cura:
            # se o agente AINDA CONSTA ATIVO no /state da office (status !=
            # gone), re-emitir o session_end 1x POR CICLO de ressurreição
            # (marcador st["reend_emit"]; a nova ressurreição o zera).
            # Fail-open: sem snapshot da office → skip silencioso.
            if snapshot is None:
                snapshot = office_agentes()
            status = snapshot.get(mid)
            if status and status != "gone" \
                    and mid not in st.get("reend_emit", {}):
                if inject({"event": "session_end", "session_id": mid,
                           "veredito": "fantasma-ressuscitado"}):
                    st["reend_emit"][mid] = now
                    st["last_change_ts"][mid] = now
                    print(f"ponte: ressuscitado re-encerrado {mid}", flush=True)
                    n += 1
            continue
        if vivo:
            continue
        if inject({"event": "session_end", "session_id": mid,
                   "veredito": "fantasma"}):
            st["ended"].append(mid)
            print(f"ponte: fantasma removido {mid}", flush=True)
            n += 1
    return n


def main() -> None:
    once = "--once" in sys.argv[1:]
    interval = float(os.environ.get("PONTE_SCAN_INTERVAL", "5") or 5)
    state_file = os.environ.get("PONTE_STATE_FILE", "/tmp/ponte_office.estado.json")
    st = load_state(state_file)
    port = os.environ.get("AGENT_OFFICE_PORT", "8113")
    while True:
        n = scan_once(st)
        save_state(state_file, st)
        print(f"ponte: porta={port} eventos={n}", flush=True)
        if once:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
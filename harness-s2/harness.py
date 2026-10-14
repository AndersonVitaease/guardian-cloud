#!/usr/bin/env python3
"""HARNESS-SPRINT2-01 — harness v2: runner generalizado de missões (evolução do spike).

CLI: harness.py --contract <path.md> --cwd <dir-base> --budget 3.0 --max-turns 60

Evolução sobre o spike (dívidas fechadas):
  (a) stop-conditions parametrizáveis declaradas no contrato (bloco ```harness-stop);
  (b) janela com compactação: contrato SEMPRE no topo + summary rolante dos
      resultados antigos (não só últimos N crus);
  (c) retry/backoff próprio em erro de API: 3 tentativas, backoff 2^n, depois
      FAIL honesto — nunca martelada;
  (d) cwd isolado por run (subdir novo com timestamp+seed sob --cwd);
  (e) budget com abort e custo acumulado no fim.

Trilha estruturada: harness-trail.jsonl por run (ts, turno, tool, latência_ms,
custo_usd, bytes de resultado, stop-condition tickada) — legível pelo supervisor.
"""
import argparse
import contextlib
import json
import os
import re
import statistics
import subprocess
import threading
import sys
import time
import urllib.request

from bridge_sse import BridgeSseError, call_bridge_stream

BRIDGE = os.environ.get("HARNESS_BRIDGE", "http://127.0.0.1:8103/v1/messages")
MODEL = os.environ.get("HARNESS_MODEL", "z-ai/glm-5.3-flash")
HARNESS_STREAM = os.environ.get("HARNESS_STREAM", "1") != "0"   # 0 → POST antigo
# ADVISOR-MIDRUN-01: advisor nativo dentro do loop — quando o worker estagna
# (turnos sem stop-condition nova verde), o harness chama um advisor (mesma
# bridge, modelo barato) que lê o contexto e injeta um hint na janela.
# HARNESS_ADVISOR=0 desliga TUDO (paridade exata do comportamento anterior).
HARNESS_ADVISOR = os.environ.get("HARNESS_ADVISOR", "1") != "0"
ADVISOR_STALL_TRIGGER = 4     # turnos sem progresso para disparar o advisor
ADVISOR_MAX_CALLS = 2         # teto de chamadas de advisor por run (custo)
ADVISOR_MODEL = os.environ.get("HARNESS_ADVISOR_MODEL", "z-ai/glm-5.3-flash")
ADVISOR_TRUNC = 1500          # truncamento de cada troca no prompt do advisor
ADVISOR_SYSTEM = ("Você é advisor de um worker LLM emperrado. Receba as últimas "
                  "trocas e as stop-conditions pendentes e devolva UM hint curto "
                  "e acionável (1-3 frases) para destravar o próximo passo.")


def advisor_prompt(win, state, conds):
    """Prompt curto do advisor: últimas 3 trocas truncadas + pendências."""
    trocas = []
    for ex in win.exchanges[-3:]:
        a = " ".join(b.get("text", "") for b in ex["assistant"] if b.get("type") == "text")
        for r in ex["user"]:
            if r.get("type") == "tool_result":
                c = r.get("content", "")
                c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                trocas.append(f"tool_result: {trunc(c, ADVISOR_TRUNC)}")
            elif r.get("type") == "text":
                trocas.append(f"user: {trunc(r.get('text', ''), ADVISOR_TRUNC)}")
        if a:
            trocas.append(f"assistant: {trunc(a, ADVISOR_TRUNC)}")
    pend = [f"{k}: {conds[int(k.split(':')[0])].get('path') or conds[int(k.split(':')[0])].get('cmd') or conds[int(k.split(':')[0])].get('marker')}"
            for k, v in state.items() if not v]
    return (ADVISOR_SYSTEM + "\n\nÚLTIMAS TROCAS:\n" + "\n".join(trocas)
            + "\n\nSTOP-CONDITIONS PENDENTES:\n" + "\n".join(pend or ["(nenhuma listada)"]))


def call_advisor(bridge_fn, ledger, win, state, conds, model=ADVISOR_MODEL):
    """1 chamada do advisor pela MESMA bridge (custo no MESMO ledger).

    Retorna o texto do hint ou None em caso de falha (nunca derruba a run)."""
    try:
        d, usd, dt, retries = bridge_fn(
            [{"role": "user", "content": advisor_prompt(win, state, conds)}],
            ADVISOR_SYSTEM, ledger, model=model)
        txt = " ".join(b.get("text", "") for b in d.get("content", [])
                       if b.get("type") == "text").strip()
        return txt or None
    except Exception as e:  # noqa: BLE001 — advisor falho é só aviso honesto
        return None

PRICE_TABLE = "/opt/mission-events/orchestrator-price-table.json"
MAX_TOOL_CHARS = 4000          # resultado cru truncado dentro da janela
RAW_WINDOW = 12                # últimos N resultados crus; anteriores viram summary
                               # (5.1: janela 6 era pequena demais — loop re-lia o
                               # mesmo arquivo em fatias 3-4x e não escrevia)
MAX_SUMMARY_LINES = 60         # teto do sumário rolante
RETRY_ATTEMPTS = 3             # política: 3 tentativas, backoff 2^n, depois FAIL

TOOLS = [
    {"name": "Bash", "description": "Executa comando shell no cwd da run. Use para rodar testes.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "Write", "description": "Escreve arquivo (utf-8), caminho relativo ao cwd da run.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "Read", "description": "Lê arquivo (caminho relativo ao cwd da run).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "Edit", "description": "Substitui old_string por new_string (1ª ocorrência) em arquivo.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["path", "old_string", "new_string"]}},
]


# ---------------------------------------------------------------- stop-conditions

REPORTER_PREFIX_CLASS = r"[#ℹ✖✔✗*]?"   # símbolos de reporter conhecidos (opcionais)


def marker_regex(marker):
    """Regex tolerante a formato de reporter (sprint 6, entrega 1).

    - espaços do marker viram ``\\s+``;
    - palavras SEM dígitos (exceto a última) são OPCIONAIS — o reporter pode
      trocá-las por símbolo (``✖``) ou omitir (``fail 0`` casa
      ``# fail 0``, ``ℹ fail 0`` e ``✖ 0``);
    - palavras COM dígitos são SEMPRE OBRIGATÓRIAS (``70 passed`` NÃO casa
      ``66 passed`` — número é quantidade, não formato de reporter);
    - prefixo de reporter (``#``, ``ℹ``, ``✖``...) é sempre opcional;
    - ``^`` no início do marker declarado vira âncora de linha (escape
      automático — nunca um literal ``^``), com semântica multiline.
    """
    m = marker.strip()
    anchored = m.startswith("^")
    if anchored:
        m = m[1:]
    words = m.split()
    tail = re.escape(words[-1]) if words else ""
    head = ""
    if len(words) > 1:
        parts = []
        for w in words[:-1]:
            if any(ch.isdigit() for ch in w):
                parts.append(re.escape(w))            # quantidade: obrigatória
            else:
                parts.append(r"(?:" + re.escape(w) + r")?")  # palavra: opcional
        head = r"\s+".join(parts) + r"\s*"
    pat = REPORTER_PREFIX_CLASS + r"\s*" + head + tail
    if anchored:
        pat = r"(?m)^" + pat
    return re.compile(pat)


def parse_stop_conditions(contract_text):
    """Extrai bloco ```harness-stop ... ``` do contrato.

    Linhas aceitas:
      file <caminho>            — arquivo-prova deve existir (não vazio)
      cmd <shell>               — comando-verificador deve sair com exit 0
      marker <TEXTO> <caminho>  — TEXTO deve aparecer no arquivo (regex flexível);
                                  TEXTO é EXATAMENTE 1 token: marker multi-token
                                  (ex.: "latencia_marker /path") é condição
                                  impossível (marker=1ª palavra, path=resto) e
                                  vira ERRO EXPLÍCITO — use cmd grep para texto
                                  com espaço
      cmdout <TEXTO> :: <shell> — sprint 6: roda <shell>, exige exit 0 E casa
                                  TEXTO contra a SAÍDA BRUTA com regex flexível
                                  (tolerante a reporter #, ℹ, ✖; ^ vira âncora)
    Sem bloco = sem stop-condition declarada (só budget/turnos).
    """
    m = re.search(r"```harness-stop\n(.*?)```", contract_text, re.S)
    conds = []
    if not m:
        return conds
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if parts[0] == "file" and len(parts) == 2:
            conds.append({"kind": "file", "path": parts[1].strip()})
        elif parts[0] == "cmd" and len(parts) == 2:
            conds.append({"kind": "cmd", "cmd": parts[1].strip()})
        elif parts[0] == "cmdout" and len(parts) == 2:
            sub = parts[1].split("::", 1)
            if len(sub) == 2:
                conds.append({"kind": "cmdout", "marker": sub[0].strip(),
                              "cmd": sub[1].strip()})
        elif parts[0] == "marker" and len(parts) == 2:
            sub = parts[1].strip().split(None, 1)
            if len(sub) == 2:
                path = sub[1].strip()
                # Dívida real (2 FAILs, US$ 0,04): "marker <TEXTO COM ESPAÇO>
                # <path>" era aceito como marker=1ª-palavra + path=resto —
                # condição impossível (o path com espaço nunca é arquivo real).
                # Recusa explícita quando o "path" tem espaço e não existe como
                # arquivo; marker de 1 token com path válido segue igual.
                if (" " in path or "\t" in path) and not os.path.exists(path):
                    # marker multi-token: condição impossível, recusa explícita.
                    raise ValueError(
                        f"marker multi-token: '{parts[1].strip()}' — "
                        "marker é 1 token; use cmd grep")
                conds.append({"kind": "marker", "marker": sub[0], "path": path})
    return conds


def check_stop_conditions(conds, cwd):
    """Retorna (todas_cumpridas, {id_cond: bool}) — cada condição avaliada no cwd."""
    state = {}
    for i, c in enumerate(conds):
        key = f"{i}:{c['kind']}"
        try:
            if c["kind"] == "file":
                p = os.path.join(cwd, c["path"])
                state[key] = os.path.isfile(p) and os.path.getsize(p) > 0
            elif c["kind"] == "cmd":
                r = subprocess.run(c["cmd"], shell=True, cwd=cwd,
                                   capture_output=True, text=True, timeout=120)
                state[key] = r.returncode == 0
            elif c["kind"] == "cmdout":
                # sprint 6: exit 0 E marker casa a saída bruta (regex flexível)
                r = subprocess.run(c["cmd"], shell=True, cwd=cwd,
                                   capture_output=True, text=True, timeout=120)
                state[key] = r.returncode == 0 and bool(
                    marker_regex(c["marker"]).search(r.stdout or ""))
            elif c["kind"] == "marker":
                p = os.path.join(cwd, c["path"])
                state[key] = os.path.isfile(p) and bool(marker_regex(
                    c["marker"]).search(open(p, encoding="utf-8",
                                             errors="replace").read()))
        except Exception:
            state[key] = False
    return all(state.values()) if conds else False, state


# ---------------------------------------------------------------- ledger (custo)

class Ledger:
    def __init__(self, price_table=PRICE_TABLE):
        self.prices = json.load(open(price_table))["models"]
        self.in_tok = self.out_tok = self.cache_tok = 0
        self.cost = 0.0
        self.calls = []
        # BATCH-PARALELO-01: lock p/ uso concorrente (threads somando no mesmo
        # ledger). Fora de threads o comportamento é idêntico (paridade).
        self._lock = threading.Lock()

    def price(self, model):
        base = model.replace("-0731", "")
        return self.prices.get(base) or self.prices.get(model) or {"in": 0, "out": 0, "cache_read": 0}

    def add(self, model, usage):
        u = usage or {}
        i, o, c = u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0) or 0
        p = self.price(model)
        c_usd = (i * p["in"] + o * p["out"] + c * p["cache_read"]) / 1e6
        lock = getattr(self, "_lock", None)
        ctx = lock if lock is not None else contextlib.nullcontext()
        with ctx:
            self.in_tok += i; self.out_tok += o; self.cache_tok += c; self.cost += c_usd
            self.calls.append({"model": model, "in": i, "out": o, "cache": c, "usd": round(c_usd, 8)})
        return c_usd

    def summary(self):
        return {"calls": len(self.calls), "in": self.in_tok, "out": self.out_tok,
                "cache": self.cache_tok, "usd": round(self.cost, 6)}


# ---------------------------------------------------------------- bridge + retry

def call_bridge_once(messages, system, model):
    # CACHE-LOOP-01: system block com cache_control ephemeral — o system é
    # idêntico em toda a run (contrato no topo), então o bridge pode cacheá-lo.
    body = {"model": model, "max_tokens": 4096,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": TOOLS, "messages": messages}
    req = urllib.request.Request(BRIDGE, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    if d.get("type") == "error" or "content" not in d:
        raise RuntimeError(f"resposta de erro do bridge: {str(d)[:300]}")
    return d, time.time() - t0


def call_bridge(messages, system, ledger, model=MODEL, attempts=RETRY_ATTEMPTS, sleep=time.sleep):
    """Retry/backoff próprio: 3 tentativas, backoff 2^n (1s, 2s, 4s). Depois: FAIL honesto."""
    last_err = None
    for attempt in range(attempts):
        try:
            d, dt = call_bridge_once(messages, system, model)
            usd = ledger.add(d.get("model", model), d.get("usage"))
            return d, usd, dt, attempt
        except Exception as e:  # noqa: BLE001 — qualquer falha de rede/API entra no backoff
            last_err = f"{type(e).__name__}: {e}"
            if attempt < attempts - 1:
                sleep(2 ** attempt)
    raise BridgeError(last_err)


class BridgeError(RuntimeError):
    pass


# ---------------------------------------------------------------- janela com compactação

def trunc(s, n=MAX_TOOL_CHARS):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n…[+{len(s)-n} chars truncados]"


def _short(v, n=80):
    v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    v = " ".join(v.split())
    return v if len(v) <= n else v[:n] + "…"


class Window:
    """Janela de contexto com compactação.

    - contrato SEMPRE no topo (vai no system, reenviado em toda chamada);
    - só as últimas `raw_window` trocas (assistant + tool_results) ficam cruas,
      com pares tool_use/tool_result íntegros;
    - trocas mais antigas viram 1 linha cada no SUMÁRIO rolante, injetado na
      1ª mensagem user; o sumário tem teto (`max_summary`) — o excedente vira
      uma linha de contagem, então o tamanho da janela é limitado.
    """

    def __init__(self, raw_window=RAW_WINDOW, max_summary=MAX_SUMMARY_LINES,
                 max_tool_chars=MAX_TOOL_CHARS):
        self.raw_window = raw_window
        self.max_summary = max_summary
        self.max_tool_chars = max_tool_chars
        self.summary_lines = []
        self.dropped = 0
        self.exchanges = []    # [{turn, assistant: [blocks], user: [blocks], digest: [str]}]

    @staticmethod
    def digest(turn, assistant, results):
        lines = []
        txt = " ".join(b.get("text", "") for b in assistant if b.get("type") == "text").strip()
        if txt:
            lines.append(f"t{turn} assistente: {_short(txt, 120)}")
        for r in results:
            head = (r["content"] or "").strip().splitlines()
            lines.append(f"t{turn} {r['tool']}({_short(r.get('input', {}), 60)}) → "
                         f"{'ERRO' if r['is_error'] else 'ok'} ({len(r['content'] or '')}B): "
                         f"{_short(head[0] if head else '', 100)}")
        return lines

    def add(self, turn, assistant, results=None, nudge=None):
        """Registra uma troca. results = [{id, tool, input, content, is_error}];
        sem results (turno sem tool_use) a resposta user é o texto `nudge`."""
        results = results or []
        if results:
            user = [{"type": "tool_result", "tool_use_id": r["id"],
                     "content": trunc(r["content"], self.max_tool_chars),
                     "is_error": r["is_error"]} for r in results]
        else:
            user = [{"type": "text", "text": nudge or "Continue."}]
        self.exchanges.append({"turn": turn, "assistant": assistant, "user": user,
                               "digest": self.digest(turn, assistant, results)})
        while len(self.exchanges) > self.raw_window:
            self.summary_lines.extend(self.exchanges.pop(0)["digest"])
        if len(self.summary_lines) > self.max_summary:
            excess = len(self.summary_lines) - self.max_summary
            self.dropped += excess
            self.summary_lines = self.summary_lines[excess:]

    def messages(self, kickoff):
        first = kickoff
        if self.summary_lines:
            first += "\n\nSUMÁRIO de passos antigos (compactado"
            first += f"; {self.dropped} linhas mais antigas omitidas" if self.dropped else ""
            first += "):\n" + "\n".join(self.summary_lines)
        msgs = [{"role": "user", "content": first}]
        for ex in self.exchanges:
            msgs.append({"role": "assistant", "content": ex["assistant"]})
            msgs.append({"role": "user", "content": ex["user"]})
        return msgs


# ---------------------------------------------------------------- execução de tools

def _resolve(cwd, path):
    """Caminho de Read/Write/Edit confinado ao cwd da run (isolamento)."""
    root = os.path.realpath(cwd)
    p = os.path.realpath(os.path.join(root, path))
    if p != root and not p.startswith(root + os.sep):
        raise PermissionError(f"caminho fora do cwd da run: {path}")
    return p


def run_tool(name, inp, cwd, timeout=120):
    try:
        if name == "Bash":
            r = subprocess.run(inp["command"], shell=True, cwd=cwd,
                               capture_output=True, text=True, timeout=timeout)
            out = (r.stdout + ("\n[stderr] " + r.stderr if r.stderr.strip() else "")).strip()
            return f"exit={r.returncode}\n{out}"
        if name == "Write":
            p = _resolve(cwd, inp["path"])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(inp["content"])
            return f"OK wrote {inp['path']} ({len(inp['content'])} bytes)"
        if name == "Read":
            with open(_resolve(cwd, inp["path"]), encoding="utf-8", errors="replace") as f:
                return f.read()
        if name == "Edit":
            p = _resolve(cwd, inp["path"])
            with open(p, encoding="utf-8") as f:
                s = f.read()
            if inp["old_string"] not in s:
                return "ERRO: old_string não encontrado"
            with open(p, "w", encoding="utf-8") as f:
                f.write(s.replace(inp["old_string"], inp["new_string"], 1))
            return f"OK edited {inp['path']}"
        return f"ERRO: tool desconhecida {name}"
    except Exception as e:  # noqa: BLE001 — erro vira tool_result, não derruba o loop
        return f"ERRO: {type(e).__name__}: {e}"


# ---------------------------------------------------------------- run isolada

def make_run_dir(base_cwd, seed):
    """cwd isolado por run: <base>/run-<ts>-seed<seed>-<pid>, criado NOVO e vazio
    (exist_ok=False) — mata a dívida dos artefatos copiados entre runs."""
    os.makedirs(base_cwd, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for n in range(100):
        d = os.path.join(base_cwd, f"run-{stamp}-seed{seed}-{os.getpid()}" + (f"-{n}" if n else ""))
        try:
            os.makedirs(d, exist_ok=False)
            return d
        except FileExistsError:
            continue
    raise RuntimeError("não consegui criar cwd isolado novo")


def pctl(values, p):
    """Percentil nearest-rank (p em 0..100)."""
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def trail_input(name, inp):
    """Input da tool resumido p/ a trilha (Write: só path + tamanho, nunca o conteúdo)."""
    if name == "Write":
        return {"path": inp.get("path"), "content_bytes": len(inp.get("content", ""))}
    return _short(inp, 200)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_brt():
    """Timestamp humano para o pane — SEMPRE hora de Brasília (UTC-3)."""
    return time.strftime("%d/%m %H:%M:%S BRT", time.localtime())


def _trunc(txt, n=60):
    txt = " ".join(str(txt).split())
    return txt if len(txt) <= n else txt[: n - 1] + "…"


def _pane_line(rec, prefix=None) -> str:
    """1 evento do trail → 1 linha legível PTBR para o pane (não JSON cru).

    É o que o supervisor vê no herdr: horário BRT, custo, latência e veredito
    — sem quebrar linha, sem json.dumps.

    BATCH-PARALELO-01: prefix (ex. "[s3]") entra na 1ª coluna; None = paridade.
    """
    ts = _now_brt()
    tool = rec.get("tool", "?")
    turn = rec.get("turno", "-")
    pre = f"{prefix} " if prefix else ""
    if tool == "_inicio":
        conds = rec.get("stop_conditions_declaradas") or []
        return (f"{pre}[{ts}] INÍCIO seed={rec.get('seed')} modelo={rec.get('model')} "
                f"budget=${rec.get('budget_usd')} turnos_max={rec.get('max_turns')} "
                f"stop_conditions={len(conds)}")
    if tool == "llm":
        if "erro" in rec:
            return (f"{pre}[{ts}] turno {turn} | llm | ERRO: {_trunc(rec['erro'])} "
                    f"| tentativas={rec.get('tentativas')}")
        return (f"{pre}[{ts}] turno {turn} | llm | {rec.get('latencia_ms')}ms "
                f"| ${rec.get('custo_usd', 0):.6f} | cum ${rec.get('cum_usd', 0):.6f} "
                f"| stop={rec.get('stop_reason')} retries={rec.get('retries')} "
                f"| janela={rec.get('msgs_janela')}")
    if tool == "_stop_check":
        state = rec.get("stop_state") or {}
        ok = sum(1 for v in state.values() if v)
        pend = [k for k, v in state.items() if not v]
        base = f"[{ts}] turno {turn} | stop-conditions {ok}/{len(state or {})} cumpridas"
        if rec.get("todas"):
            return pre + base + " — TODAS, encerrando"
        return pre + base + (f" | pendentes: {','.join(pend)}" if pend else "")
    if tool == "_resumo":
        c = rec.get("custo") or {}
        lat = rec.get("latencia_ms") or {}
        return (f"{pre}[{ts}] VEREDITO {rec.get('veredito')} | motivo={rec.get('motivo')} "
                f"| {rec.get('turnos')} turno(s) | ${c.get('usd', 0):.6f} de "
                f"${rec.get('budget_usd')} | lat p50 {lat.get('p50')}ms "
                f"| stop-conditions {rec.get('stop_conditions_cumpridas')} "
                f"| trail {rec.get('trail')}")
    # tools do worker (Bash, Read, ...) e qualquer evento novo
    err = rec.get("is_error")
    status = "ERRO" if err else "ok"
    inp = rec.get("input")
    if isinstance(inp, dict):  # ex.: {"command": "grep ..."} → só o comando
        inp = inp.get("command") or inp.get("path") or " ".join(
            f"{k}={v}" for k, v in inp.items())
    elif isinstance(inp, str) and inp.lstrip().startswith("{"):
        # trail_input serializa como JSON (e TRUNCA com "…", o que quebra o
        # json.loads) — extrai o comando/path direto, com ou sem JSON válido.
        m = re.search(r'"(?:command|path)"\s*:\s*"(.*)', inp)
        inp = m.group(1).rstrip('"}') if m else inp
    extra = f" | {_trunc(inp)}" if inp else ""
    return (f"{pre}[{ts}] turno {turn} | {tool} | {rec.get('latencia_ms', 0)}ms "
            f"| ${rec.get('custo_usd', 0):.2f} | {status}{extra}")


def bloco_checkpoint():
    """CHECKPOINT-WIRE-01: env HARNESS_CHECKPOINT_FROM aponta o run_dir da janela
    anterior (com CHECKPOINT.json) -> texto de retomada para injeção no kickoff.
    Sem env / sem arquivo / qualquer falha -> None (comportamento default intacto)."""
    src = os.environ.get("HARNESS_CHECKPOINT_FROM")
    if not src:
        return None
    cp = os.path.join(src, "CHECKPOINT.json")
    if not os.path.isfile(cp):
        return None
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
        from checkpoint import retomar_prompt  # lazy
        return "## CHECKPOINT DA JANELA ANTERIOR\n\n" + retomar_prompt(cp)
    except Exception as e:  # noqa: BLE001 — checkpoint nunca derruba a run
        print(f"[checkpoint] injeção ignorada: {e}", file=sys.stderr)
        return None


KICKOFF = "Comece agora. Itere até cumprir todas as stop-conditions; então escreva o relatório e PARE."


def run_mission(contract_path, base_cwd, budget_usd, max_turns, seed=0, model=MODEL,
                ledger=None, bridge_fn=None, log=sys.stderr, max_stalls=5,
                raw_window=RAW_WINDOW, stop_flag=None, pane_prefix=None,
                max_tool_chars=MAX_TOOL_CHARS, max_summary=MAX_SUMMARY_LINES,
                contract_prefix=""):
    """Executa 1 run isolada. Retorna dict de resumo (veredito, custo, latências...)."""
    contract = open(contract_path, encoding="utf-8").read().replace("{{SEED}}", str(seed))
    bridge_fn = bridge_fn or call_bridge  # late binding: permite mock de harness.call_bridge
    conds = parse_stop_conditions(contract)
    run_dir = make_run_dir(os.path.abspath(base_cwd), seed)
    ledger = ledger or Ledger()
    trail_path = os.path.join(run_dir, "harness-trail.jsonl")
    trail = open(trail_path, "a", encoding="utf-8")
    pane_path = os.path.join(run_dir, "harness-pane.log")
    pane = open(pane_path, "a", encoding="utf-8")

    def emit(rec):
        trail.write(json.dumps({"ts": _now(), **rec}, ensure_ascii=False) + "\n")
        trail.flush()
        pane.write(_pane_line(rec, prefix=pane_prefix) + "\n")
        pane.flush()

    _cp_sec = bloco_checkpoint() or ""
    if _cp_sec:
        _cp_sec = _cp_sec + "\n\n"
    system = (f"Você é o worker do harness v2. Execute o contrato abaixo EXATAMENTE.\n"
              f"cwd da run (isolado, criado vazio agora): {run_dir}\n"
              f"seed desta run: {seed}\n"
              f"Todos os caminhos de arquivo são relativos a esse cwd; crie tudo do zero aqui "
              f"(não copie artefatos de outras runs).\n"
              f"As stop-conditions estão no bloco harness-stop do contrato — trabalhe até todas "
              f"serem cumpridas (o harness verifica sozinho a cada turno).\n"
              f"Se algo recusar (permissão, user, cwd), registre verbatim e feche FAIL — sem contorno.\n"
              f"PT-BR.\n\n{contract_prefix}{_cp_sec}# CONTRATO\n{contract}")
    win = Window(raw_window=raw_window, max_tool_chars=max_tool_chars,
                 max_summary=max_summary)
    verdict, reason = "FAIL", "max_turns"
    turn_lat, n_retries, stalls = [], 0, 0
    ticked = set()
    state = {}
    # ADVISOR-MIDRUN-01: contador de estagnação reutiliza `ticked` (stop-conditions
    # novas verdes) — sem duplicar estado. Teto de 2 chamadas por run.
    turnos_sem_progresso = 0
    advisor_calls = 0
    emit({"turno": 0, "tool": "_inicio", "run_dir": run_dir, "seed": seed, "model": model,
          "budget_usd": budget_usd, "max_turns": max_turns, "raw_window": raw_window,
          "stop_conditions_declaradas": conds})

    def tick(turn, tool):
        nonlocal state
        done, state = check_stop_conditions(conds, run_dir)
        new = [k for k, v in state.items() if v and k not in ticked]
        ticked.update(new)
        return done, new

    for turn in range(1, max_turns + 1):
        if stop_flag is not None and stop_flag.is_set():
            verdict, reason = "FAIL", "budget_excedido"
            break
        if ledger.cost >= budget_usd:
            verdict, reason = "FAIL", "budget_excedido"
            break
        msgs = win.messages(KICKOFF)
        # BATCH-PARALELO-01: checagem FINAL imediatamente antes da chamada LLM
        # (janela estreita entre o pré-check e a chamada — outra thread pode ter
        # setado o stop_flag ou estourado o custo TOTAL nesse intervalo; o lock
        # do ledger compartilhado garante atomicidade da checagem agregada).
        if stop_flag is not None and stop_flag.is_set():
            verdict, reason = "FAIL", "budget_excedido"
            break
        with ledger._lock:
            estourado = ledger.cost >= budget_usd
        if estourado:
            verdict, reason = "FAIL", "budget_excedido"
            break
        # BATCH-PARALELO-01: janela final — re-checa stop_flag DEPOIS da
        # checagem de custo e ANTES da chamada LLM (outra thread pode ter
        # sinalizado abort exatamente nesse intervalo).
        if stop_flag is not None and stop_flag.is_set():
            verdict, reason = "FAIL", "budget_excedido"
            break
        try:
            if stop_flag is not None and stop_flag.is_set():
                verdict, reason = "FAIL", "budget_excedido"
                break
            # STREAM-ALWAYS-01 (08/10): stream deixa de ser exclusivo do --pane —
            # é o caminho default em TODOS os modos. Gate duplo: HARNESS_STREAM
            # (off local) e BRIDGE_STREAM (gate da bridge; systemd cache.conf).
            _bridge_stream_on = os.environ.get("BRIDGE_STREAM", "1") != "0"
            # bridge_fn custom (mock de teste / injeção) NUNCA entra no stream:
            # stream chamaria call_bridge_stream real e mascararia o mock.
            if HARNESS_STREAM and _bridge_stream_on and bridge_fn is call_bridge:
                if stop_flag is not None and stop_flag.is_set():
                    verdict, reason = "FAIL", "budget_excedido"
                    break
                def _on_token(text, _pane=pane):
                    _pane.write(f"[tok] {text[:80]}\n")
                    _pane.flush()
                try:
                    d, usd, dt, retries = call_bridge_stream(
                        msgs, system, model, ledger, on_token=_on_token,
                        tools=TOOLS)
                except BridgeSseError as e:
                    # degradação honesta: bridge recusou stream → POST antigo
                    emit({"turno": turn, "tool": "_stream", "erro": str(e)[:200],
                          "degradou_para": "POST"})
                    if stop_flag is not None and stop_flag.is_set():
                        verdict, reason = "FAIL", "budget_excedido"
                        break
                    d, usd, dt, retries = bridge_fn(msgs, system, ledger, model=model)
            else:
                if stop_flag is not None and stop_flag.is_set():
                    verdict, reason = "FAIL", "budget_excedido"
                    break
                d, usd, dt, retries = bridge_fn(msgs, system, ledger, model=model)
            n_retries += retries
        except BridgeError as e:
            verdict, reason = "FAIL", f"bridge_error:{e}"
            emit({"turno": turn, "tool": "llm", "erro": str(e), "tentativas": RETRY_ATTEMPTS})
            break
        lat_ms = round(dt * 1000)
        turn_lat.append(lat_ms)
        uses = [b for b in d.get("content", []) if b.get("type") == "tool_use"]
        emit({"turno": turn, "tool": "llm", "latencia_ms": lat_ms, "custo_usd": round(usd, 8),
              "bytes": len(json.dumps(d.get("content", []), ensure_ascii=False)),
              "stop_reason": d.get("stop_reason"), "retries": retries,
              "msgs_janela": len(msgs), "resumo_linhas": len(win.summary_lines),
              "cum_usd": round(ledger.cost, 6)})

        if ledger.cost >= budget_usd:
            verdict, reason = "FAIL", "budget_excedido"
            break

        results = []
        for b in uses:
            t0 = time.time()
            out = run_tool(b["name"], b.get("input", {}), run_dir)
            err = out.startswith("ERRO")
            results.append({"id": b.get("id"), "tool": b["name"], "input": b.get("input", {}),
                            "content": out, "is_error": err})
            emit({"turno": turn, "tool": b["name"], "input": trail_input(b["name"], b.get("input", {})),
                  "latencia_ms": round((time.time() - t0) * 1000),
                  "custo_usd": 0.0, "bytes": len(out), "is_error": err})

        done, new = tick(turn, "check")
        emit({"turno": turn, "tool": "_stop_check", "stop_tick": new, "stop_state": state,
              "todas": done})
        if done:
            verdict, reason = "PASS", "stop_condition"
            break

        # ADVISOR-MIDRUN-01: estagnação = turnos desde a última stop-condition
        # nova verde. No gatilho, advisor injeta hint na janela (máx 2x/run).
        if new:
            turnos_sem_progresso = 0
        else:
            turnos_sem_progresso += 1
        if (HARNESS_ADVISOR and turnos_sem_progresso >= ADVISOR_STALL_TRIGGER
                and advisor_calls < ADVISOR_MAX_CALLS):
            advisor_calls += 1
            hint = call_advisor(bridge_fn, ledger, win, state, conds)
            if hint is None:
                # advisor falho (bridge error) = aviso honesto, run segue
                emit({"turno": turn, "tool": "_advisor", "erro": "advisor_falhou",
                      "aviso": "advisor indisponível; run segue sem hint"})
                pane.write(f"advisor | FALHA | aviso honesto no trail\n"); pane.flush()
            else:
                win.add(turn, [{"type": "text", "text": "(advisor)"}],
                        nudge=f"HINT DO ADVISOR (turno {turn}): {hint}")
                emit({"turno": turn, "tool": "_advisor", "kind": "advisor",
                      "hint": hint[:200], "custo_usd": round(ledger.cost, 6)})
                pane.write(f"advisor | hint injetado | ${ledger.cost:.6f}\n"); pane.flush()

        if uses:
            stalls = 0
            win.add(turn, d["content"], results)
        else:
            stalls += 1
            if stalls >= max_stalls:
                verdict, reason = "FAIL", "parou_sem_stop_condition"
                break
            pend = [k for k, v in state.items() if not v]
            win.add(turn, d.get("content") or [{"type": "text", "text": "(vazio)"}],
                    nudge=f"Stop-conditions ainda pendentes: {pend}. Continue usando as tools.")
    trail.close()
    pane.close()

    summary = {"veredito": verdict, "motivo": reason, "run_dir": run_dir, "seed": seed,
               "model": model, "turnos": len(turn_lat), "retries": n_retries,
               "custo": ledger.summary(), "budget_usd": budget_usd,
               "custo_por_turno_usd": round(ledger.cost / len(turn_lat), 8) if turn_lat else 0.0,
               "latencia_ms": {"p50": pctl(turn_lat, 50), "p99": pctl(turn_lat, 99),
                               "max": max(turn_lat) if turn_lat else 0},
               "stop_conditions": [{**c, "ok": state.get(f"{i}:{c['kind']}", False)}
                                   for i, c in enumerate(conds)],
               "stop_conditions_cumpridas": f"{sum(1 for v in state.values() if v)}/{len(conds)}",
               "trail": trail_path, "ts": _now()}
    with open(trail_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), "turno": len(turn_lat), "tool": "_resumo", **summary},
                           ensure_ascii=False) + "\n")
    with open(pane_path, "a", encoding="utf-8") as f:
        f.write(_pane_line({"tool": "_resumo", **summary}, prefix=pane_prefix) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=log)
    return summary


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="harness v2 — runner generalizado de missões")
    ap.add_argument("--contract", required=True, help="contrato .md com bloco ```harness-stop```")
    ap.add_argument("--cwd", required=True, help="dir-base; cada run cria subdir isolado novo")
    ap.add_argument("--budget", type=float, default=3.0, help="teto USD desta run (abort)")
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0, help="seed variável por execução ({{SEED}} no contrato)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--raw-window", type=int, default=RAW_WINDOW,
                    help="trocas cruas na janela; mais antigas viram sumário")
    ap.add_argument("--out", default=None, help="resumo JSON (default: <run_dir>/run-summary.json)")
    args = ap.parse_args(argv)

    s = run_mission(args.contract, args.cwd, args.budget, args.max_turns,
                    seed=args.seed, model=args.model, raw_window=args.raw_window)
    out_path = args.out or os.path.join(s["run_dir"], "run-summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    return 0 if s["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

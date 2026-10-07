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
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request

BRIDGE = os.environ.get("HARNESS_BRIDGE", "http://127.0.0.1:8103/v1/messages")
MODEL = os.environ.get("HARNESS_MODEL", "z-ai/glm-5.3-flash")
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
      marker <TEXTO> <caminho>  — TEXTO deve aparecer no arquivo (regex flexível)
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
                conds.append({"kind": "marker", "marker": sub[0], "path": sub[1].strip()})
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

    def price(self, model):
        base = model.replace("-0731", "")
        return self.prices.get(base) or self.prices.get(model) or {"in": 0, "out": 0, "cache_read": 0}

    def add(self, model, usage):
        u = usage or {}
        i, o, c = u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0) or 0
        p = self.price(model)
        c_usd = (i * p["in"] + o * p["out"] + c * p["cache_read"]) / 1e6
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

    def __init__(self, raw_window=RAW_WINDOW, max_summary=MAX_SUMMARY_LINES):
        self.raw_window = raw_window
        self.max_summary = max_summary
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
                     "content": trunc(r["content"]), "is_error": r["is_error"]} for r in results]
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


KICKOFF = "Comece agora. Itere até cumprir todas as stop-conditions; então escreva o relatório e PARE."


def run_mission(contract_path, base_cwd, budget_usd, max_turns, seed=0, model=MODEL,
                ledger=None, bridge_fn=call_bridge, log=sys.stderr, max_stalls=5,
                raw_window=RAW_WINDOW):
    """Executa 1 run isolada. Retorna dict de resumo (veredito, custo, latências...)."""
    contract = open(contract_path, encoding="utf-8").read().replace("{{SEED}}", str(seed))
    conds = parse_stop_conditions(contract)
    run_dir = make_run_dir(os.path.abspath(base_cwd), seed)
    ledger = ledger or Ledger()
    trail_path = os.path.join(run_dir, "harness-trail.jsonl")
    trail = open(trail_path, "a", encoding="utf-8")

    def emit(rec):
        trail.write(json.dumps({"ts": _now(), **rec}, ensure_ascii=False) + "\n")
        trail.flush()

    system = (f"Você é o worker do harness v2. Execute o contrato abaixo EXATAMENTE.\n"
              f"cwd da run (isolado, criado vazio agora): {run_dir}\n"
              f"seed desta run: {seed}\n"
              f"Todos os caminhos de arquivo são relativos a esse cwd; crie tudo do zero aqui "
              f"(não copie artefatos de outras runs).\n"
              f"As stop-conditions estão no bloco harness-stop do contrato — trabalhe até todas "
              f"serem cumpridas (o harness verifica sozinho a cada turno).\n"
              f"Se algo recusar (permissão, user, cwd), registre verbatim e feche FAIL — sem contorno.\n"
              f"PT-BR.\n\n# CONTRATO\n{contract}")
    win = Window(raw_window=raw_window)
    verdict, reason = "FAIL", "max_turns"
    turn_lat, n_retries, stalls = [], 0, 0
    ticked = set()
    state = {}
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
        if ledger.cost >= budget_usd:
            verdict, reason = "FAIL", "budget_excedido"
            break
        msgs = win.messages(KICKOFF)
        try:
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

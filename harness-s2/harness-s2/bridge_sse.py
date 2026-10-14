#!/usr/bin/env python3
"""BRIDGE-SSE-01 — chamada ao bridge com stream SSE por token.

Mesmo contrato de ``harness.call_bridge`` (retorna ``d, usd, dt, retries``),
mas consome ``POST /v1/messages`` com ``"stream": true``:

- eventos ``content_block_delta`` com delta de texto → callback ``on_token(text)``
  em tempo real;
- eventos de erro no meio do stream contam como falha e entram no mesmo
  retry/backoff (3 tentativas, backoff 2^n);
- ``on_token=None`` → só consome, sem callback;
- contabilidade de tokens pelo ``usage`` do ``message_delta`` final.

O leitor de eventos é injetável (``reader``) para testes com stream FABRICADO —
nunca chama o bridge real nos testes.
"""
import json
import time
import urllib.request

RETRY_ATTEMPTS = 3


class BridgeSseError(RuntimeError):
    pass


def _parse_sse(lines):
    """Iterador de linhas SSE → eventos (event, data_dict)."""
    event, data = None, []
    for raw in lines:
        chunk = raw.decode() if isinstance(raw, bytes) else raw
      # um "chunk" pode conter várias linhas (leitor de socket/file)
        for line in chunk.splitlines():
            if line == "":
                if data:
                    payload = "\n".join(data)
                    try:
                        obj = json.loads(payload)
                    except ValueError:
                        obj = {"raw": payload}
                    yield event or obj.get("type"), obj
                event, data = None, []
            elif line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:"):].strip())


def _default_reader(body):
    """Leitor real: POST no bridge com stream=true, itera linhas da resposta."""
    from harness import BRIDGE, TOOLS
    payload = {"model": body["model"], "max_tokens": body["max_tokens"],
               "system": body["system"], "tools": TOOLS,
               "messages": body["messages"], "stream": True}
    req = urllib.request.Request(BRIDGE, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json"},
                                 method="POST")
    resp = urllib.request.urlopen(req, timeout=300)
    return resp


def _assemble(events, on_token):
    """Consome eventos SSE; monta o dict final no formato não-stream.

    Levanta BridgeSseError em evento de erro (meio do stream ou evento isolado).
    """
    blocks = []          # blocos de conteúdo reconstruídos
    cur = None           # índice do bloco em construção
    usage = {}
    model = None
    stop_reason = None
    for ev, obj in events:
        etype = obj.get("type", ev)
        if etype == "error" or obj.get("type") == "error" or ev == "error":
            raise BridgeSseError(f"erro no stream: {json.dumps(obj, ensure_ascii=False)[:300]}")
        if etype == "message_start":
            model = (obj.get("message") or {}).get("model") or model
            u = (obj.get("message") or {}).get("usage") or {}
            usage.update({k: v for k, v in u.items() if v})
        elif etype == "content_block_start":
            cb = obj.get("content_block") or {}
            cur = obj.get("index", len(blocks))
            while len(blocks) <= cur:
                blocks.append(None)
            blocks[cur] = {"type": cb.get("type"), "text": "", "id": cb.get("id"),
                           "name": cb.get("name"), "input": ""}
        elif etype == "content_block_delta":
            delta = obj.get("delta") or {}
            idx = obj.get("index", cur if cur is not None else 0)
            while len(blocks) <= idx:
                blocks.append({"type": "text", "text": ""})
            if blocks[idx] is None:
                blocks[idx] = {"type": "text", "text": ""}
            if delta.get("type") == "text_delta":
                blocks[idx]["text"] += delta.get("text", "")
                if on_token:
                    on_token(delta.get("text", ""))
            elif delta.get("type") == "input_json_delta":
                blocks[idx]["input"] += delta.get("partial_json", "")
        elif etype == "message_delta":
            delta = obj.get("delta") or {}
            stop_reason = delta.get("stop_reason", stop_reason)
            u = obj.get("usage") or {}
            usage.update({k: v for k, v in u.items() if v})
        elif etype == "message_stop":
            break
    content = []
    for b in blocks:
        b = b or {"type": "text", "text": ""}
        if b["type"] == "tool_use":
            raw = b.get("input") or ""
            try:
                inp = json.loads(raw) if raw else {}
            except ValueError:
                inp = {}
            content.append({"type": "tool_use", "id": b.get("id"),
                            "name": b.get("name"), "input": inp})
        else:
            content.append({"type": "text", "text": b.get("text", "")})
    return {"type": "message", "model": model, "content": content,
            "stop_reason": stop_reason, "usage": usage}


def call_bridge_stream(messages, system, model, ledger, on_token=None,
                       attempts=RETRY_ATTEMPTS, sleep=time.sleep, reader=None,
                       tools=None):
    """POST no bridge com stream=true; mesmo contrato de call_bridge.

    reader(body_dict) → iterável de linhas SSE (bytes ou str). Default: HTTP real.
    tools: lista de tools (como call_bridge_once) — sem ela o modelo não toola.
    """
    body = {"model": model, "max_tokens": 4096,
            "system": [{"type": "text", "text": system,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": messages}
    if tools:
        body["tools"] = tools
    last_err = None
    for attempt in range(attempts):
        try:
            # t0 ANTES de abrir/consumir o reader: no caminho HTTP real,
            # cobre o envio do request até o fim do assemble — dt reflete o
            # tempo de parede REAL da geração (não ~0 como antes).
            t0 = time.time()
            src = reader(body) if reader else _default_reader(body)
            d = _assemble(_parse_sse(src), on_token)
            dt = time.time() - t0
            if d.get("type") == "error" or not d.get("content"):
                raise BridgeSseError(f"resposta de erro do bridge: {json.dumps(d, ensure_ascii=False)[:300]}")
            usd = ledger.add(d.get("model") or model, d.get("usage"))
            return d, usd, dt, attempt
        except Exception as e:  # noqa: BLE001 — falha de rede/erro no stream entra no backoff
            last_err = f"{type(e).__name__}: {e}"
            if attempt < attempts - 1:
                sleep(2 ** attempt)
    raise BridgeSseError(last_err)

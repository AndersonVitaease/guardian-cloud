#!/usr/bin/env python3
"""Probe E2E de latência real do stream SSE do bridge.

Mede (a) tempo até o 1º evento SSE e (b) tempo total até o fim do stream,
gravando o resultado em latencia-e2e.jsonl (1 linha por rodada) no cwd.
"""
import json
import sys
import time
import urllib.request

BRIDGE = "http://127.0.0.1:8103/v1/messages"
PROMPT = "Conte de 1 a 50, um por linha."
ARQUIVO = "latencia-e2e.jsonl"


def latencia_stream(model="z-ai/glm-5.3-flash", timeout=60, _post=None, _out=None):
    """Faz 1 POST real ao bridge e mede latência do stream.

    _post e _out são pontos de injeção para testes (reader fabricado).
    Retorna dict com primeiro_evento, total, eventos; exit 1 em falha.
    """
    payload = json.dumps({
        "model": model,
        "max_tokens": 300,
        "stream": True,
        "messages": [{"role": "user", "content": PROMPT}],
    }).encode("utf-8")

    t0 = time.monotonic()
    try:
        if _post is not None:
            resp = _post(payload)
        else:
            req = urllib.request.Request(
                BRIDGE, data=payload,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=timeout)
    except Exception as exc:
        print(f"ERRO: bridge recusou ou timeout: {exc}")
        sys.exit(1)

    primeiro_evento = None
    eventos = 0
    try:
        for linha in resp:
            linha = linha.decode("utf-8", "replace").strip()
            if not linha:
                continue
            if primeiro_evento is None:
                primeiro_evento = time.monotonic() - t0
            eventos += 1
    except Exception as exc:
        print(f"ERRO: falha lendo stream: {exc}")
        sys.exit(1)
    total = time.monotonic() - t0

    if primeiro_evento is None or eventos == 0:
        print("ERRO: stream vazio (nenhum evento recebido)")
        sys.exit(1)

    print(f"primeiro_evento={primeiro_evento:.2f}s | total={total:.2f}s | eventos={eventos}")
    registro = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "primeiro_evento": round(primeiro_evento, 3),
        "total": round(total, 3),
        "eventos": eventos,
    }
    out_path = _out if _out is not None else ARQUIVO
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


if __name__ == "__main__":
    latencia_stream()

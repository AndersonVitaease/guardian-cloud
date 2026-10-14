#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jev-ask.py — andar 2 do orquestrador (ORQ-JEV-01): classifica pedido em
linguagem natural numa acao consultiva via modelo barato (harness.call_bridge).
Saida: UMA palavra (secretaria|status|fila|none). Fail-closed: qualquer erro -> none.
Uso: python3 jev-ask.py "<pedido>"
"""
import json, os, sys

acoes = {"secretaria", "status", "fila", "none"}


class _LedgerNull:
    def add(self, *a, **k):
        return 0.0
SYSTEM = ("Roteador Jev do orquestrador. O operador fez um pedido em linguagem natural "
          "para o sistema de missões. Responda APENAS com UMA palavra, sem pontuação: "
          "secretaria (pergunta/consulta/estado geral), status (estado de uma missão "
          "específica por id), fila (fila do orquestrador), none (não é consulta "
          "ou pede despacho/decisão).")

def main():
    pedido = sys.argv[1] if len(sys.argv) > 1 else ""
    if not pedido.strip():
        print("none"); return 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do repo (harness.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import harness
        msgs = [{"role": "user", "content": pedido[:2000]}]
        resp, usd, dt, retries = harness.call_bridge(msgs, SYSTEM, _LedgerNull(), model=None)
        d = resp if isinstance(resp, dict) else None
        if d is not None:
            txt = ""
            for c in d.get("content", []):
                if isinstance(c, dict) and c.get("type") == "text":
                    txt += c.get("text", "")
            texto = txt.strip().lower()
        else:
            texto = str(resp).strip().lower()
        token = texto.split()[0] if texto.split() else "none"
        token = token.strip(".,;:!?")
        print(token if token in acoes else "none")
        if os.environ.get("JEV_LOG"):
            with open(os.environ["JEV_LOG"], "a") as f:
                f.write(json.dumps({"token": token, "usd": usd, "dt": dt}) + "\n")
    except Exception:
        print("none")  # fail-closed
    return 0

if __name__ == "__main__":
    sys.exit(main())

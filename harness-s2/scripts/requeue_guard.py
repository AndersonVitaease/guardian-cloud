#!/usr/bin/python3
"""Guard de dedupe para requeue do orquestrador (requeue-guard-01)."""
import argparse
import json
import sys


def ja_na_fila(fila_path, intent_id):
    """True se alguma linha do jsonl tem esse `id`. Nunca levanta."""
    try:
        with open(fila_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("id") == intent_id:
                    return True
    except OSError:
        return False
    return False


def decidir_requeue(fila_path, intent):
    """Decide se o intent pode ser re-enfileirado."""
    intent_id = intent.get("id")
    if intent_id is not None and ja_na_fila(fila_path, intent_id):
        return {"requeue": False, "motivo": "intent-%s já na fila" % intent_id}
    return {"requeue": True, "motivo": "id ausente na fila"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guard de dedupe de requeue")
    parser.add_argument("--fila", required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args(argv)
    try:
        presente = ja_na_fila(args.fila, args.id)
    except Exception:
        print(json.dumps({"erro": "file error"}))
        return 1
    requeue = not presente
    print(json.dumps({"ja_na_fila": presente, "requeue": requeue}))
    return 0 if requeue else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        print(json.dumps({"erro": "file error"}))
        sys.exit(1)
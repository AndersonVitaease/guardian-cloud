#!/usr/bin/env bash
# verify_tools.sh — recalcula sha256 de cada .sh e do tools.json contra o
# MANIFEST.sha256 instalado e devolve JSON {ok, mismatches[]} (exit 0 sempre).
set -u
python3 - /opt/mission-events/tools-bash <<'PY'
import json, os, sys
base = sys.argv[1]
manifest = os.path.join(base, "MANIFEST.sha256")
mismatches, missing_manifest = [], False
expected = {}
if os.path.isfile(manifest):
    try:
        with open(manifest, encoding="utf-8") as f:
            for l in f:
                h, _, name = l.strip().partition("  ")
                if h and name:
                    expected[name] = h
    except Exception:
        missing_manifest = True
else:
    missing_manifest = True
files = sorted(fn for fn in os.listdir(base) if fn.endswith(".sh") or fn == "tools.json")
for fn in files:
    if fn == "verify_tools.sh" or fn == "_lib.sh":
        continue
    p = os.path.join(base, fn)
    if not os.path.isfile(p):
        continue
    import hashlib
    with open(p, "rb") as fh:
        h = hashlib.sha256(fh.read()).hexdigest()
    if fn not in expected:
        mismatches.append(fn)
    elif expected[fn] != h:
        mismatches.append(fn)
if missing_manifest:
    print(json.dumps({"ok": False, "mismatches": sorted(set(mismatches) | {"MANIFEST_MISSING"})}, separators=(",", ":")))
else:
    print(json.dumps({"ok": not mismatches, "mismatches": mismatches}, separators=(",", ":")))
PY
exit 0

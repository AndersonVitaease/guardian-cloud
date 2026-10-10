#!/usr/bin/env bash
# verify_tools.sh — recalcula sha256 de cada .sh e do tools.json contra o
# MANIFEST.sha256 instalado e devolve JSON {ok, mismatches[]} (exit 0 sempre).
set -u
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEN=0
[ "${1:-}" = "--gen" ] && GEN=1
python3 - "$BASE" "$GEN" <<'PY'
import hashlib, json, os, sys
base, gen = sys.argv[1], sys.argv[2] == "1"
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
    with open(p, "rb") as fh:
        h = hashlib.sha256(fh.read()).hexdigest()
    if gen:
        expected[fn] = h
        continue
    if fn not in expected:
        mismatches.append(fn)
    elif expected[fn] != h:
        mismatches.append(fn)
if gen:
    with open(manifest, "w", encoding="utf-8") as f:
        for fn in sorted(expected):
            f.write(expected[fn] + "  " + fn + "\n")
    print(json.dumps({"ok": True, "mismatches": [], "generated": True}, separators=(",", ":")))
elif missing_manifest:
    print(json.dumps({"ok": False, "mismatches": sorted(set(mismatches) | {"MANIFEST_MISSING"})}, separators=(",", ":")))
else:
    print(json.dumps({"ok": not mismatches, "mismatches": mismatches}, separators=(",", ":")))
PY
exit 0

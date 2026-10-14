#!/usr/bin/env bash
# avisos-pane.sh — garante a aba AVISOS do herdr rodando tail -F do avisos.jsonl.
# Resolve TAB-ID e PANE-ID reais (labels nao servem para pane run).
set -u
HERDR="${HERDR_BIN:-herdr}"
F="${AVISOS_FILE:-/opt/mission-events/avisos.jsonl}"
touch "$F" 2>/dev/null || true

ATAB="$("$HERDR" tab list 2>/dev/null | python3 -c '
import json, sys
for t in json.load(sys.stdin).get("result", {}).get("tabs", []):
    if t.get("label") == "AVISOS":
        print(t["tab_id"]); break
' 2>/dev/null | head -1)"
[ -n "$ATAB" ] || { "$HERDR" tab create --label "AVISOS" >/dev/null 2>&1 || exit 0; ATAB="$("$HERDR" tab list 2>/dev/null | python3 -c '
import json, sys
for t in json.load(sys.stdin).get("result", {}).get("tabs", []):
    if t.get("label") == "AVISOS":
        print(t["tab_id"]); break
' 2>/dev/null | head -1)"; }
[ -n "$ATAB" ] || exit 0

APANE="$("$HERDR" pane list 2>/dev/null | python3 -c '
import json, sys
for p in json.load(sys.stdin).get("result", {}).get("panes", []):
    if p.get("tab_id") == sys.argv[1]:
        print(p["pane_id"]); break
' "$ATAB" 2>/dev/null | head -1)"
[ -n "$APANE" ] || exit 0

"$HERDR" pane run "$APANE" "tail -n 50 -F $F" >/dev/null 2>&1 || true
exit 0
# MISSÃO GB-PLUGIN-SANIDADE-01 — diag do plugin mission-ops com fixtures

Entrega: scripts/plugin_diag.py (PLUGIN_DIR=<dir>; checa __init__.py compila, handle_mission_dispatch presente, delega ao despachar_missao, não é stub <500 linhas) — provado contra fixture bom e fixture coxo.

```harness-stop
cmd cd /home/worker/harness-s2 && test -x scripts/plugin_diag.py
cmd cd /home/worker/harness-s2 && python3 scripts/plugin_diag.py 2>&1 | grep -q '"ok": false'
```

# MISSÃO DESP-FECHO-ROBUSTO-01 (P1, Fila=sim)
Fonte: ROADMAP.md linha 402 (FIND-060c4856). Write now, no exploring.
Worktree /home/worker/wt-DESP-FECHO-ROBUSTO-01 (branch desp-fecho-robusto-01). Write ONLY here.

## Bug (known)
/home/worker/harness-s2/scripts/despachar_missao.py:147 puts ` ; ` between 3 commands inside one `--property=ExecStopPost=...` value. systemd does not split commands inside a property value → ledger fechar, tab_reap, vigia_chat never run on stop.

## Deliverables (worktree only; placeholder {id} = mission id)
1. NEW scripts/fechar_missao.sh: arg `{id}`; set +e; steps independent, 2 retries each, typed FAIL lines to /tmp/fechar_missao-{id}.log; ALWAYS exit 0; idempotent. Steps: (a) /usr/bin/python3 /home/worker/harness-s2/scripts/ledger_missao.py fechar {id} --resumo /tmp/resumo-{id}.json; (b) /usr/bin/bash /opt/mission-events/tools-bash/tab_reap.sh --apply; (c) /home/worker/harness-s2/scripts/vigia_chat.sh {id} --send.
2. EDIT scripts/despachar_missao.py L147: single `--property=ExecStopPost=-+/bin/bash /home/worker/harness-s2/scripts/fechar_missao.sh %s` (mid). Anchor old_string: `ExecStopPost=-+/usr/bin/python3` (unique).
3. NEW scripts/reconciliar_resumos.py (stdlib): each /tmp/resumo-*.json gives `{id}`; if its ledger entry is still dispatched/running → run `bash /home/worker/harness-s2/scripts/fechar_missao.sh {id}`; print JSON {checked, refechados, erros}. Plus drop-in systemd/mission-watcher-fecho.conf in worktree (supervisor applies; never edit /etc).
4. NEW scripts/prova-fecho-robusto-01.sh: fake /tmp/resumo-PROVA-FECHO.json; run fechar_missao.sh PROVA-FECHO twice; assert exit 0 both + log present.

## Report
RELATORIO-DESP-FECHO-ROBUSTO-01.md in worktree root: files, symbols, stop outputs, debt (live systemd test of broken ExecStopPost unit = supervisor-applied; list exact commands). Commit early, subject has DESP-FECHO-ROBUSTO-01, git add only mission files.

## Stops
```harness-stop
cmd cd /home/worker/wt-DESP-FECHO-ROBUSTO-01 && bash -n scripts/fechar_missao.sh && grep -q "exit 0" scripts/fechar_missao.sh
cmd cd /home/worker/wt-DESP-FECHO-ROBUSTO-01 && python3 -m py_compile scripts/reconciliar_resumos.py scripts/despachar_missao.py
cmd cd /home/worker/wt-DESP-FECHO-ROBUSTO-01 && grep -q "fechar_missao.sh" scripts/despachar_missao.py && ! grep -q "ExecStopPost=-+/usr/bin/python3" scripts/despachar_missao.py
cmd cd /home/worker/wt-DESP-FECHO-ROBUSTO-01 && bash scripts/prova-fecho-robusto-01.sh && test -f /tmp/fechar_missao-PROVA-FECHO.log
cmd cd /home/worker/wt-DESP-FECHO-ROBUSTO-01 && test -f RELATORIO-DESP-FECHO-ROBUSTO-01.md
```
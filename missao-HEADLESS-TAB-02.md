---
class: mecanica
component: harness-s2
---
# MISSÃO HEADLESS-TAB-02 — aba RUN herdr com conteúdo ao vivo + label único

Fonte: ROADMAP.md linha 457 (prio 1). Fecha também DESP-TAB-LABEL-01.

## Contexto verificado (11/10 ~16:00 BRT)
- `/opt/mission-events/orchestrator-consumer.py` `ensure_run_tab` L1061-1138: cria aba com label `"RUN:%s#%s"` (L1067) via `herdr tab create --cwd ... --label ... --no-focus` (L1092-1094) e NÃO monta conteúdo: pane nasce no prompt shell vazio.
- Call site L1587-1591: `ensure_run_tab(mission_id, run_dir ou cwd, seed=dispatch_result["seed"])` — o `run_dir` LITERAL do run JÁ existe nesse momento (vem de `dispatch_via_harness` L638-700, que roda `despachar_missao.py`).
- Dedupe do consumer (startswith `RUN:<id>#`, L1080) não casa com o label do spawn `RUN:<id>#s<seed>` (mission_run.py `pane_title` L46-47 e mount-espelho.sh) → 2 abas por missão.
- `fechar_missao.sh` L23 roda `/opt/mission-events/tools-bash/tab_reap.sh --apply`; tab_reap L59 extrai missionId do trecho entre `:` e `#`. Aba órfã pós-pouso (w9:t49): provar o reap nas DUAS formas de label.

## Entregas (TUDO no worktree; NUNCA escreva em /opt)
1. `staging/orchestrator-consumer.py` = `cp` do `/opt/mission-events/orchestrator-consumer.py` atual + PATCH:
   a. label único = `"RUN:%s#s%s" % (mission_id, seed)` (formato `#s<seed>`, igual a mission_run.py e mount-espelho.sh);
   b. após o create com pane_id extraído: montar conteúdo AO VIVO — `herdr pane run <pane_id> "<cmd>"` onde `<cmd>` = `until test -f <trail>; do sleep 1; done; tail -n +1 -F <trail>` e `<trail>` é caminho LITERAL da `harness-trail.jsonl` do run (se `<run_dir>/harness-trail.jsonl` não existir de cara, derive do padrão real de mission_run.py — leia `pane_mount` L64-77 e `last_trail_line` L110-122 para o layout exato). Fail-open ABSOLUTO: qualquer falha nessa montagem loga `TAB_CREATE_FAILED` e NUNCA bloqueia o dispatch;
   c. sem run_dir no dispatch_result: fail-open igual (usa cwd ou pula a montagem, logando).
2. `patches/orchestrator-consumer.diff` = `diff -u` cópia ORIGINAL vs patched (aplicável pelo supervisor — instruções exatas de patch/restart no RELATORIO).
3. `staging/tab_reap.sh` = cópia do tab_reap.sh de /opt (leitura); PROVE no teste que ela reap abas mortas nas duas formas de label (RUN:ID#sSEED e RUN:ID#SEED). Se quebrar para alguma forma, gere também `patches/tab_reap.diff`.
4. `prova-HEADLESS-TAB-02.py` — hermética, stdlib, <60s, sem rede e sem herdr real:
   - fake `herdr` em PATH (script bash que grava cada chamada em JSONL e responde JSON com tab_id/pane_id — espelhe o formato que o consumer parseia: `data.tab.tab_id` / `data.pane.pane_id`);
   - importa o consumer PATCHED (staging) e chama `ensure_run_tab` com run_dir fake + trilha fake em `tempfile.mkdtemp()` (unit falsa simulada: trilha com 3 linhas JSON);
   - assegura: (i) `herdr tab create` chamado com label `RUN:<ID>#s<seed>`; (ii) chamada `herdr pane run` contém `tail -n +1 -F` + caminho literal da trilha; (iii) executar o comando do tail num bash real e assert que as 3 linhas da trilha fake aparecem na saída (conteúdo ao vivo);
   - assegura label ÚNICO: fake `herdr tab list` devolve a aba recém-criada e a 2ª chamada de `ensure_run_tab` NÃO cria segunda aba (dedupe); nenhuma tab com `#<seed>` sem `s` é criada;
   - fecho fake: roda `staging/tab_reap.sh --apply` com fake herdr + active-json fake listando o run como morto → a aba é fechada (`tab close` chamado 1x) e as vivas ficam;
   - imprime marker `PROVA-HEADLESS-TAB-02-OK` e grava tudo em `prova-HEADLESS-TAB-02.out`.
5. `RELATORIO-HEADLESS-TAB-02.md`: diffs, instruções de aplicação supervisor-side (comando patch exato + restart do consumer systemd), saída integral da prova, horários BRT.
6. Commit único com `HEADLESS-TAB-02` no subject.

## Regras
- Zero exploração: o mapa acima basta. Leia apenas trechos com `code_slice.sh ARQUIVO INI FIM` se estritamente necessário.
- NÃO baixe nada da internet; se faltar algo, STOP-AND-REPORT.
- `git add` só dos arquivos da missão. Não use `git reset/checkout/stash/clean`.
- Prova não depende de herdr real nem de /opt gravável; fixture em mktemp (nunca /tmp fixo).

## MAPA
- /opt/mission-events/orchestrator-consumer.py : ensure_run_tab : L1061 (label L1067, dedupe L1080, create L1092, rename L1120, ledger L1127)
- /opt/mission-events/orchestrator-consumer.py : call site L1587-1591 (dispatch_result com run_dir + seed)
- /opt/mission-events/orchestrator-consumer.py : dispatch_via_harness L638-700 (fonte do run_dir literal)
- /home/worker/harness-s2/mission_run.py : pane_title L46-47 (já `#s<seed>` — referência do formato), pane_mount L64-77 (padrão do tail: `until ls ...; tail -n +1 -F`)
- /home/worker/harness-s2/scripts/fechar_missao.sh L23 (chamada do tab_reap)
- /opt/mission-events/tools-bash/tab_reap.sh L59 (match de label) — prova de referência: /opt/mission-events/tools-bash/test_tab_reap.sh (padrão de fake herdr com HERDR_BIN)

```harness-stop
cmd cd /home/worker/wt-HEADLESS-TAB-02 && /usr/bin/python3 prova-HEADLESS-TAB-02.py
cmd cd /home/worker/wt-HEADLESS-TAB-02 && grep -q -F PROVA-HEADLESS-TAB-02-OK prova-HEADLESS-TAB-02.out
cmd cd /home/worker/wt-HEADLESS-TAB-02 && grep -q pane_id patches/orchestrator-consumer.diff
cmd cd /home/worker/wt-HEADLESS-TAB-02 && grep -q "#s" patches/orchestrator-consumer.diff
cmd cd /home/worker/wt-HEADLESS-TAB-02 && test $(stat -c%s RELATORIO-HEADLESS-TAB-02.md) -gt 500
cmd cd /home/worker/wt-HEADLESS-TAB-02 && git log --oneline | grep -q HEADLESS-TAB-02
```

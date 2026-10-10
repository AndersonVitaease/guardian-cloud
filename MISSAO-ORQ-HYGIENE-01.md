# MISSÃO ORQ-HYGIENE-01 — tool bash orq_hygiene.sh: varredura de higiene do orquestrador (0 LLM)

Fonte: ROADMAP.md linha 374.

operatorOrder: limpeza dos 3 pontos de higiene autorizada pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Padrão de forma EXATO: /opt/mission-events/tools-bash/runs_status.sh (L1-8 shebang/env, `source "$(dirname ...)/_lib.sh"`, tb_audit L30, tb_join L58, tb_fail L64, emit no fim, exit 0 SEMPRE, JSON 1 linha).
- Contexto medido ao vivo (10/10, supervisor): watcher zumbi PID 84132 era `bash -lic ... while pgrep -f "mission_run.py.*SHIP..." ; do sleep 20` — pgrep casava o PRÓPRIO cmdline do pai → loop eterno; morto pelo supervisor. Daemons orqd: `orqd-live` pid 2424807 (`--db /var/lib/orqd-live/orqd.db --sock /run/orqd-live/orqd.sock --workspace w8 --queue /opt/mission-events/orchestrator-queue.js*`) e antigo `orqd` pid 3772362 (`--db /var/lib/orqd/orqd.db --queue /opt/mission-events/orchestrator-queue.jsonl`). Consumidor legado orchestrator-consumer.py (PID 1113573) NÃO EXISTE mais. Lixo untracked na árvore base: `.orqd-wtest`, `.wt-rd-ag01/` e um RELATORIO de id ORQD-SENTINEL — agente de fecho operou FORA de worktree próprio.

## OBJETIVO
Tool `orq_hygiene.sh` (determinística, 0 LLM) que varre e reporta 3 classes de sujeira; leitura de /proc e ps permitida (nada de escrita fora do run dir):
1. WATCHERS_ZUMBI: processos `bash -lic` cujo cmdline contém `pgrep -f` cujo padrão casa o PRÓPRIO cmdline (self-match) → pid, user, trecho do padrão.
2. ORQD_DUPLICADO: processos `orqd.daemon` agrupados por `--workspace` → se >1 por workspace, alerta com pid/db/queue de cada um.
3. FECHO_FORA_WORKTREE: git repos em /home/worker/* com arquivos untracked cujo nome casa `.orqd-*`, `.wt-rd-*`, `RELATORIO-RD-ORQD-*` → repo, arquivos (até 10), sugestão "mover p/ worktree próprio".
Uso: `orq_hygiene.sh` (default: tudo) ou `--only watchers|orqd|worktree`. `--fix`: SOMENTE itens de propriedade do usuário que roda (worker não pode matar root; para root apenas RELATA com `dica`). Saída: JSON 1 linha {ok, tool, watchers:[], orqd:[], worktree:[], fix_aplicado:[], modo}.

## TAREFA
1. Ler runs_status.sh e _lib.sh; escrever `orq_hygiene.sh` na raiz do worktree seguindo o padrão (tb_audit/tb_fail/tb_emit, exit 0 sempre).
2. Escrever `test_orq_hygiene.sh` com fixtures: (a) cmdline fake de watcher self-match (string embutida) → deve REPORTAR em watchers; (b) dois processos orqd fake mesmo workspace → alerta ORQD_DUPLICADO; (c) fixture de repo fake com arquivo `.orqd-wtest` → reporta em worktree. Testes rodam a lógica de DETECÇÃO via função isolada (o script deve aceitar `--proc-dump <arquivo>` com linhas "pid user cmdline" para teste hermético sem depender de /proc real).
3. Commit `ORQ-HYGIENE-01: orq_hygiene.sh + test_orq_hygiene.sh` e `ORQ-HYGIENE-01: relatorio` (RELATORIO-ORQ-HYGIENE-01.md, 2 linhas: o que fez + prova).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-ORQ-HYGIENE-01 && git log -1 --format=%s | grep -q -F "ORQ-HYGIENE-01: orq_hygiene.sh"
cmd cd /home/worker/wt-ORQ-HYGIENE-01 && bash -n orq_hygiene.sh
cmd cd /home/worker/wt-ORQ-HYGIENE-01 && bash test_orq_hygiene.sh
cmd cd /home/worker/wt-ORQ-HYGIENE-01 && git ls-files --error-unmatch orq_hygiene.sh && git -C /home/worker/wt-ORQ-HYGIENE-01 diff --quiet HEAD -- orq_hygiene.sh
cmd cd /home/worker/wt-ORQ-HYGIENE-01 && git ls-files --error-unmatch RELATORIO-ORQ-HYGIENE-01.md
```

PROIBIDO: git reset/checkout/stash/clean; escrita em /opt; matar processos (a varredura é só leitura); tocar routing/bridge.

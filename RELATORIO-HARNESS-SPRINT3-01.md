# RELATÓRIO HARNESS-SPRINT3-01 — missão REAL pelo harness v2 (glm-5.3-flash)

## O que o LOOP fez (glm via bridge :8103)
- Contrato: `/home/worker/harness-s2/canary/contrato-sprint3-real.md` (schema sprint 2: file/cmd/marker), alvo = worktree `/tmp/eng-mcp-wt-harness-sprint3-01/eng-mcp`.
- Tarefa: pinar `python3` solto → `/usr/bin/python3` apenas nos `verify-*.json`.
- Run 1 (seed 3, 60 turnos): fez o pin e escreveu o relatório, mas o marker `Veredito: PASS` não casou com o contrato (`marker PASS`) → 2/3 stop conditions. Falha de especificação do contrato (minha), não do loop.
- Correção: marker do contrato alinhado a `PASS`.
- Run 2 (seed 4, 60 turnos): **3/3 stop conditions** — pin aplicado (0 `python3` solto restante em verify-*.json), JSONs válidos, `RELATORIO-sprint3-loop.md` com `Veredito: PASS` + `PARE`. Trilha: `run-20261007-121437-seed4-1043487/harness-trail.jsonl` (removida do commit; logs de run ficam fora do repo).

## O que EU (worker CLI) fiz
- Suporte: portei os fixes ORCH-SELFHEAL-01 do main para o worktree (lock/WT_ROOT herméticos) — commit 7c6c391e.
- Preparação: escrevi o contrato do loop; resetei os verify-*.json antes da run 2 (o pin já tinha sido feito por mim no commit 14a091a6 — o loop refez a mesma higiene de forma independente e o estado final é idêntico).
- Fechamento: validei o resultado do loop (0 python3 solto, JSON-OK), commitei o relatório do loop (5ee0a115), rodei a suíte completa.

## Prova
- Suíte do worktree (`npm test` com ORCH_DAEMON_LOCK_DIR/GIT_CHECKOUT_WT_ROOT): **2009 pass / 6 fail / 6 skipped**; as 6 falhas são idênticas por nome ao baseline do main (T7/T18/T19 distribution spy, git.merge scope/AUTO_FF/local-merge) — pré-existentes, sem regressão.
- Branch `harness-sprint3-pypin` com 3 commits (7c6c391e, 14a091a6, 5ee0a115). Sem push, sem merge, conforme contrato.
- pytest do harness (`tests/`): 30/30 verde (nenhuma capacidade nova foi exigida pelo contrato).

## Dívidas
- 6 falhas baseline do main (fora do escopo desta sprint).
- Run 1 consumiu parte do budget por falha de especificação do marker (lição: validar o marker contra o texto que o loop realmente escreve).

PASS
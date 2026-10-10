# MISSÃO WT-SPIN-01 — tool bash wt_spin.sh: spin-up de worktree de missão (0 LLM)

Fonte: ROADMAP.md linha 376.

operatorOrder: spin de worktree como tool autorizado pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Padrão de forma EXATO: /opt/mission-events/tools-bash/runs_status.sh (L1-8, source _lib.sh, tb_audit L30, tb_fail L64, exit 0 SEMPRE, JSON 1 linha).
- Boilerplate medido ao vivo (todo despacho de hoje repetiu): `git -C /home/worker/harness-s2 worktree add -b rd-<id-slug> /home/worker/wt-<ID> rd-segue-01` + `chown -R worker:worker` + prova de commit como worker (`sudo -u worker git -C ... commit --allow-empty -m t` + desfazer) + `sudo -u worker` em tudo. Erro comum que a tool evita: contrato com STOP_PATH_INEXISTENTE (worktree criado depois do lint).

## OBJETIVO
Tool `wt_spin.sh <ID> [base]` — default base `rd-segue-01`, repo `/home/worker/harness-s2` (env WT_SPIN_REPO para teste). Passos:
1. Branch `rd-<slug-do-ID>`: slug = ID minúsculo. Worktree `/home/worker/wt-<ID>`. Se branch/worktree já existe: NAO_CRIADO tipado com campo `dica` (nunca destrói).
2. `chown -R worker:worker <wt>`; prova de commit como worker (`sudo -u worker git -C <wt> commit --allow-empty -m "wt-spin-probe <ID>"` e `git reset --hard HEAD~1` como worker para desfazer — É A ÚNICA exceção de reset, prova de permissão). `--no-probe` pula a prova.
3. Saída JSON: {ok, tool, id, worktree, branch, base, probe:"ok|pulada", ms}. tb_audit com o resultado.
4. Roda como root (faz chown); nada em /opt; nunca apaga branch/worktree existente.

## TAREFA
1. Ler runs_status.sh; escrever `wt_spin.sh` na raiz do worktree.
2. Teste hermético `test_wt_spin.sh`: repo fake via `git init --bare` + clone scratch (env WT_SPIN_REPO aponta pro fake, WT_SPIN_WT_ROOT para scratch), usuário não-worker simulado cobrindo: criação feliz; segunda chamada → NAO_CRIADO; `--no-probe`; branch com slug certo. Fixtures dentro do teste.
3. Commit `WT-SPIN-01: wt_spin.sh + test_wt_spin.sh` e `WT-SPIN-01: relatorio` (RELATORIO-WT-SPIN-01.md, 2 linhas).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-WT-SPIN-01 && git log -1 --format=%s | grep -q -F "WT-SPIN-01: wt_spin.sh"
cmd cd /home/worker/wt-WT-SPIN-01 && bash -n wt_spin.sh
cmd cd /home/worker/wt-WT-SPIN-01 && bash test_wt_spin.sh
cmd cd /home/worker/wt-WT-SPIN-01 && git ls-files --error-unmatch wt_spin.sh && git -C /home/worker/wt-WT-SPIN-01 diff --quiet HEAD -- wt_spin.sh
cmd cd /home/worker/wt-WT-SPIN-01 && git ls-files --error-unmatch RELATORIO-WT-SPIN-01.md
```

PROIBIDO: git reset/checkout/stash/clean fora da prova de commit; escrita em /opt; apagar branch/worktree pré-existente.

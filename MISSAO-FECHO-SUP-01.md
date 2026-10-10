# MISSÃO FECHO-SUP-01 — tool bash missao_fechar.sh: fecho de missão do supervisor em 1 comando (0 LLM)

Fonte: ROADMAP.md linha 375.

operatorOrder: fecho de missão como tool autorizado pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Padrão de forma EXATO: /opt/mission-events/tools-bash/runs_status.sh (L1-8, source _lib.sh, tb_audit L30, tb_join L58, tb_fail L64, exit 0 SEMPRE, JSON 1 linha). Padrão de flags DRY-RUN/--apply e erro tipado com dica: /opt/mission-events/tools-bash/tab_reap.sh (instalada hoje; ler também).
- Fluxo medido ao vivo pelo supervisor (10/10, 3 fechos manuais): (1) ler `/root/.hermes/mission-state-mirror/<ID>.json` OU fallback glob `/home/worker/wt-*/runs/<ID>` (padrão do run_close.sh L33-60) → worktree; (2) `git -C <wt> branch --show-current` → branch; (3) veredito do `resumo.json`/`autoretry-summary.json` no runs dir deve ser PASS (senão NAO_PASS); (4) merge `--no-ff` na base; (5) suíte pytest; (6) fechar aba `RUN:<ID>#*`.

## OBJETIVO
Tool `missao_fechar.sh <ID|worktree>` — DRY-RUN por padrão, `--apply` executa. Passos:
1. Resolve branch+worktree (ledger cwd ou caminho direto; erros tipados RUN_DIR_NAO_ENCONTRADO, NAO_PASS com veredito no campo `dica`).
2. DRY-RUN: JSON {ok, tool, id, branch, base:"rd-segue-01", arquivos: N commits da branch, acao:"merge+suite+close_tab", modo:"dry-run"} — NADA executa.
3. `--apply`: (a) `git merge --no-ff <branch>` na base; conflito → `merge --abort` + CONFLITO tipado (estado intacto); (b) `/usr/bin/python3 -m pytest tests/ -q` no repo base → vermelho: `git reset --hard ORIG_HEAD` + SUITE_VERMELHA tipado (rollback provado no JSON com campo rollback:"feito"); (c) fechar aba(s) via `herdr tab close <id>` para cada aba cujo label comece com `RUN:<ID>#` (herdr inacessível: tab_closed:"inacessivel_fora_operador", NÃO é erro — o resto do fecho conta); (d) JSON final {ok, merged_as, suite:"verde", tab_closed, backup_ref:ORIG_HEAD, modo}.
4. tb_audit a cada passo com o resultado. Escrita em repo é permitida APENAS no --apply e apenas merge/reset do próprio fluxo.

## TAREFA
1. Ler runs_status.sh e tab_reap.sh; escrever `missao_fechar.sh` na raiz do worktree.
2. Teste hermético `test_missao_fechar.sh`: usar repositório git FAKE em scratch do worktree (git init + 2 branches + commits fake, resumo.json fake com veredito PASS e outro com FAIL) exercitando: DRY-RUN não altera nada; --apply com PASS faz merge + detecta suíte fake (passe um comando de suíte fake via env TEST_SUITE_CMD para o teste não rodar pytest real); FAIL de veredito → NAO_PASS sem executar merge. Fixtures dentro do teste (sem depender de /home/worker real).
3. Commit `FECHO-SUP-01: missao_fechar.sh + test_missao_fechar.sh` e `FECHO-SUP-01: relatorio` (RELATORIO-FECHO-SUP-01.md, 2 linhas).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-FECHO-SUP-01 && git log -1 --format=%s | grep -q -F "FECHO-SUP-01: missao_fechar.sh"
cmd cd /home/worker/wt-FECHO-SUP-01 && bash -n missao_fechar.sh
cmd cd /home/worker/wt-FECHO-SUP-01 && bash test_missao_fechar.sh
cmd cd /home/worker/wt-FECHO-SUP-01 && git ls-files --error-unmatch missao_fechar.sh && git -C /home/worker/wt-FECHO-SUP-01 diff --quiet HEAD -- missao_fechar.sh
cmd cd /home/worker/wt-FECHO-SUP-01 && git ls-files --error-unmatch RELATORIO-FECHO-SUP-01.md
```

PROIBIDO: git reset/checkout/stash/clean fora do rollback do próprio fluxo; escrita em /opt; rodar pytest real da base dentro do teste (usar TEST_SUITE_CMD).

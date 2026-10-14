# MISSÃO RD-WORKTREE-CLEAN-01 — tool worktree_clean (remove worktrees encerrados com arquivamento de runs/ e prova de commit preservada; dry-run default)

## CONTEXTO MEDIDO (confiado, não investigue de novo)
- Hoje a limpeza de worktrees foi feita à mão por agente (3,5 min) sem padrão; há ~35 worktrees acumulados sob /home/worker (wt-*), muitos de missões já terminais.
- Estado de missão termina no ledger `<state_dir>/<missionId>.json`: `status` terminal = closed/failed/cancelled (constante `TERMINAIS` em scripts/ledger_missao.py).
- `git -C /home/worker/harness-s2 worktree list --porcelain` lista os worktrees (o principal `/home/worker/harness-s2` e `.wt-rd-*` internos NUNCA são candidatos).
- Estilo de tool: JSON 1 linha, exit 0 sempre, falha tipada, `untrusted:true`/`notice`; wrapper AUTÔNOMO (emit/fail inline, sem source de _lib.sh — padrão entrega_verify.sh). Env de caminho NUNCA default vazio.

## MAPA
- tools-bash/worktree_clean.sh — ARQUIVO NOVO (Write inteiro; wrapper autônomo com python3 inline).
- tests/test_worktree_clean.py — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest), fixtures em tmpdir (repo git de teste criado no próprio teste + ledgers fake).

## COMPORTAMENTO EXIGIDO
1. `worktree_clean.sh [--apply]`: candidatos = worktrees de `git -C <REPO> worktree list --porcelain` sob `/home/worker/wt-*` cujo ledger tem `status` terminal OU não tem ledger E não tem unit `harness-*` ativa (consulta `systemctl list-units 'harness-*' --no-legend` via env `WORKTREE_CLEAN_UNITS_CMD` sobrescrevível p/ fake; se systemctl falhar → `ok:false,error:"SYSTEMCTL_FAILED"`, zero remoção). Repo por env `WORKTREE_CLEAN_REPO`, default `/home/worker/harness-s2`; state_dir com a MESMA resolução de `tb_state_dir` em tools-bash/_lib.sh:16 (env `MISSION_STATE_DIR` vence; fallbacks iguais aos das outras tools).
2. Sem `--apply` (dry-run default): só PLANO — `dry_run:true`, `itens:[{worktree,branch,ledger_status,runs_mb}]`, NENHUMA mutação.
3. Com `--apply`, para cada candidato, nesta ordem e ALL-OR-NOTHING por item (erro → pula o item e reporta, sem deixar estado pela metade):
   a. arquivo o runs/ do worktree (se existir e não vazio) em `/home/worker/arquivo-runs/<ID>-<ts>.tar.gz` (mkdir -p; cria se faltar);
   b. grava a prova de commit no mesmo diretório: `MANIFESTO-<ID>.md` com `git -C <wt> log -1 --format=%H %s` e `git -C <wt> status --porcelain` (resumo);
   c. SÓ ENTÃO `git -C <REPO> worktree remove <wt>` (recuse se git status sujo além de runs//__pycache__: `STATUS_SUJO`, não remove).
4. Nunca remover: o repo principal, worktrees fora de /home/worker/wt-*, ou candidato sem arquivamento concluído. Saída final com `removidos`, `arquivados`, `pulos` e motivo.
5. Rodar como worker (os worktrees e o repo são do worker); o código não usa sudo.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva `tests/test_worktree_clean.py` (Write inteiro): repo git de teste em tmpdir com 2 worktrees; cobre dry-run não muta; candidato com ledger terminal detectado; worktree com ledger em voo NÃO é candidato (caso negativo obrigatório); --apply arquiva runs/ (assert no tar + manifesto com %H) e depois remove; status sujo → STATUS_SUJO e worktree intacto; systemctl fake quebrado → SYSTEMCTL_FAILED.
2. `python3 -m pytest tests/test_worktree_clean.py -q` VERMELHO no baseline. Commit do aceite vermelho com o ID no assunto (git add só do teste).
3. Implemente `tools-bash/worktree_clean.sh` (Write inteiro); verifique chamando da RAIZ do worktree.
4. Testes verdes + `bash -n tools-bash/worktree_clean.sh`.
5. Commit do código (assunto com o ID) e `RELATORIO-RD-WORKTREE-CLEAN-01.md` na raiz (2 linhas, citando quantos candidatos o smoke real achou).

## REGRAS
- Provas python sempre como worker (você já é worker). Sem sleep, sem sudo direto, sem escrever fora do worktree. Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh; sem ';' nos stops.
- `git add` só dos arquivos da missão. Sem `git reset/checkout/stash/clean`.

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd bash -n tools-bash/worktree_clean.sh
cmd python3 -m pytest tests/test_worktree_clean.py -q
cmd bash tools-bash/worktree_clean.sh | grep -q -F '"tool":"worktree_clean"'
cmd git log --format=%s | grep -q -F RD-WORKTREE-CLEAN-01
cmd grep -q -F RD-WORKTREE-CLEAN-01 RELATORIO-RD-WORKTREE-CLEAN-01.md
```
O stop 3 é o smoke E2E REAL (dry-run, somente leitura, dados reais): rode antes no baseline e anote no relatório a lista de candidatos achados.

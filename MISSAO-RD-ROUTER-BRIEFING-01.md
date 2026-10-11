# MISSÃO RD-ROUTER-BRIEFING-01 — tool ledger_reap (lista/fecha ledgers fantasma sem unit ativa; dry-run default)

operatorOrder: despacho autorizado pelo operador 10/10 no chat ("sim" em resposta à proposta RD-ROUTER-BRIEFING-01).
## CONTEXTO MEDIDO (confiado, não investigue de novo)
- Dor: o briefing do router conta ledger "em voo" fantasma como em voo (12 em voo falso às 17:05 de 09/10, real 1). Ledger fica em `<state_dir>/<missionId>.json`; `status` não terminal (veja `TERMINAIS` em scripts/ledger_missao.py) = contado como em voo.
- Ledgers reais podem ter grafias divergentes: `veredito` vs `verdict` (lição 10/10) — ao ler campos de outro módulo use `get(a) or get(b)`.
- Unit de missão despachada se chama `harness-<ID>-s<seed>`; o estado vivo das units é o que decide se há run ativa (runs_status.sh usa `systemctl show`).
- Estilo de tool: JSON de 1 linha, exit 0 sempre, falha tipada, `untrusted:true` e `notice`; wrapper AUTÔNOMO (reimplementa emit/fail inline, NÃO faz source de _lib.sh — padrão de tools-bash/entrega_verify.sh).

## MAPA
- tools-bash/ledger_reap.sh — ARQUIVO NOVO (Write inteiro; wrapper autônomo com python3 inline).
- tests/test_ledger_reap.py — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest), fixtures em tmpdir (ledgers fake + fake de consulta de units).

## COMPORTAMENTO EXIGIDO
1. `ledger_reap.sh [--apply] [N=50]`: varre o state_dir com a MESMA resolução de `tb_state_dir` em tools-bash/_lib.sh:16 (env `MISSION_STATE_DIR` vence; fallbacks iguais aos das outras tools; NUNCA default vazio).
2. Candidato fantasma = ledger com `status` fora de TERMINAIS (não closed/failed/cancelled) cuja unit `harness-<missionId>-s*` NÃO está ativa (consulta `systemctl list-units 'harness-*' --all --no-legend`; via env `LEDGER_REAP_UNITS_CMD` sobrescrevível para fake nos testes — NUNCA default vazio).
3. Fail-safe: se a consulta de units falhar/indisponível → JSON `ok:false,error:"SYSTEMCTL_FAILED"` e NUNCA fechar nada.
4. Sem `--apply` (dry-run default): só LISTA — JSON com `dry_run:true` e `itens:[{missionId,status,custo_usd,idade}]`, NENHUMA mutação.
5. Com `--apply`: para cada item fecha via `python3 <LEDGER_REAP_LEDGER_SCRIPT> fechar <ID> --resumo /tmp/resumo-<ID>.json` quando o resumo existir; default do env `LEDGER_REAP_LEDGER_SCRIPT` = `/home/worker/harness-s2/scripts/ledger_missao.py` (NUNCA vazio); sem resumo, grava `status:"failed"` + `motivo:"fantasma_sem_unit"` direto no ledger (gravação atômica). Resultado por item em `resultados`; qualquer erro por item não aborta o lote.
6. Rodar como root em produção (supervisor); o código não usa sudo.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva `tests/test_ledger_reap.py` (Write inteiro): cobre dry-run não muta; fantasma detectado (status não terminal + unit inativa); unit ativa NÃO é candidato (caso negativo obrigatório); systemctl fake quebrado → SYSTEMCTL_FAILED e zero fechamento; --apply fecha via comando fake (assert no fake) e grava motivo; JSON 1 linha com untrusted/notice e exit 0.
2. `python3 -m pytest tests/test_ledger_reap.py -q` VERMELHO no baseline. Commit do aceite vermelho com o ID no assunto (git add só do teste).
3. Implemente `tools-bash/ledger_reap.sh` (Write inteiro). Verifique chamando da RAIZ do worktree (caminhos relativos por dirname do próprio script).
4. Testes verdes + `bash -n tools-bash/ledger_reap.sh`.
5. Commit do código (assunto com o ID) e `RELATORIO-RD-ROUTER-BRIEFING-01.md` na raiz (2 linhas, citando o resultado do smoke real).

## REGRAS
- Provas python sempre como worker (você já é worker). Sem sleep, sem sudo direto, sem escrever fora do worktree. Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh; sem ';' nos stops.
- `git add` só dos arquivos da missão. Sem `git reset/checkout/stash/clean`.

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd cd /home/worker/wt-RD-ROUTER-BRIEFING-01 && bash -n tools-bash/ledger_reap.sh
cmd cd /home/worker/wt-RD-ROUTER-BRIEFING-01 && python3 -m pytest tests/test_ledger_reap.py -q
cmd cd /home/worker/wt-RD-ROUTER-BRIEFING-01 && MISSION_STATE_DIR=/opt/mission-events/mission-state-mirror bash tools-bash/ledger_reap.sh | grep -q -F '"tool":"ledger_reap"'
cmd cd /home/worker/wt-RD-ROUTER-BRIEFING-01 && git log --format=%s | grep -q -F RD-ROUTER-BRIEFING-01
cmd cd /home/worker/wt-RD-ROUTER-BRIEFING-01 && grep -q -F RD-ROUTER-BRIEFING-01 RELATORIO-RD-ROUTER-BRIEFING-01.md
```
O stop 3 é o smoke E2E REAL (dry-run, dados reais do espelho, somente leitura): rode antes no baseline, confira que a lista sai plausível (anote contagem no relatório).

# MISSÃO CICLO-STATUS-01 — tool ciclo_status.sh (quadro único de verdade do ciclo de missões; default quadro humano, --json 1 linha)

Fonte: relatório CONCILIACAO-CICLO-11-10.md (autorização operator 11/10 ~11:40 BRT). Write now, no exploring.
Worktree /home/worker/wt-CICLO-STATUS-01 (branch ciclo-status-01). Write ONLY here.
Referência de estilo: copie o cabeçalho/forma das tools /opt/mission-events/tools-bash/runs_status.sh e queue_peek.sh (leitura permitida via code_slice.sh).

## ESPECIFICAÇÃO (o JSON deve reproduzir as colunas do relatório de conciliação)
Por missão detectada, uma linha com:
- missao (ID);
- onde_esta: {unit_ativa (systemd harness-*), trilha_viva (bool), trilha_path, trilha_mtime, resumo_path, resumo_mtime};
- progresso: {tentativas, ultimo_veredito, custo_usd, budget_usd} (de autoretry-summary.json e trilha);
- ledger_vs_realidade: {ledger_status, ledger_updatedAt, concilia: OK|<tipo de discrepância>};
- veredito (string curta, ex.: "PASS em disco, ledger parado em dispatched");
- acao_pendente (fechar | investigar | aguardar | none).

## COMPORTAMENTO EXIGIDO
1. `ciclo_status.sh` (sem args): quadro humano-compacto para leitura por agente (texto, uma missão por linha). `ciclo_status.sh --json`: UMA linha JSON `{"ok":true,"tool":"ciclo_status","modo":"...","missoes":[...],"fila":{...},"gerado_em":"..."}`. Exit 0 sempre; falhas tipadas `{"ok":false,"tool":"ciclo_status","error":"<TIPO>"}`.
2. Fontes cruzadas (todas tolerantes a ausência — fonte ausente = campo null + nota, nunca crash):
   a. units ativas: reuso do mesmo método de runs_status.sh (systemctl list-units 'harness-*' / parse equivalente);
   b. trilhas: `find` de harness-trail.jsonl por MTIME (sort por mtime real, NUNCA lexical — lição: sort lexical engoliu tentativa-3); incluir runs dirs ANINHADOS `runs/<ID>/runs/<ID2>/` (lição GB-VERED-CRED-01C);
   c. autoretry-summary.json de cada runs dir (também aninhados);
   d. resumos /tmp/resumo-*.json;
   e. ledgers: diretório de estado via env `CICLO_STATE_DIR` (default /root/.hermes/mission-state);
   f. fila: reuso/chamada de queue_peek.sh (env `CICLO_QUEUE_FILE` sobreponível);
   g. journalctl -u 'harness-*' --since -40 min (opcional; ausente = campo null).
3. Camada DISCREPÂNCIA — tipagem exata:
   - trilha/resumo diz PASS mas ledger `dispatched`/`running` → `PENDENTE_FECHO` (ação: fechar);
   - ledger closed/failed mas unit ainda ativa → `LEDGER_REABERTO`;
   - runs dir/autoretry-summary sem nenhuma trilha em disco → `RUN_SEM_TRAIL`;
   - intent na fila sem ledger correspondente → `ENFILEIRADA_AGUARDANDO`.
   Sem discrepância → `concilia: "OK"`.
4. Permissões: a tool roda como worker (sem acesso a /root). Se o diretório de ledgers for inacessível (permissão), NÃO amplie permissões: emita `modo:"MODE_SUPERVISOR"` com fallback determinístico documentado — campos de ledger = null, `ledger_concilia:"INACESSIVEL_WORKER"` para as missões afetadas, e os tipos PENDENTE_FECHO/LEDGER_REABERTO ficam `null` (indeterminável) em vez de inventados. Tudo determinístico, zero LLM.
5. Prova hermética (fixture tempdir): testes criam ledger fake + trilha fake + resumo fake + fila fake via envs (CICLO_STATE_DIR, CICLO_RUNS_DIR contendo runs fake, CICLO_QUEUE_FILE, CICLO_TMP_DIR) e cobrem: PENDENTE_FECHO, LEDGER_REABERTO, RUN_SEM_TRAIL, ENFILEIRADA_AGUARDANDO e caso limpo (tudo OK). Unit ativa e journalctl podem ser stub via env (CICLO_UNITS_JSON / CICLO_JOURNAL_OFF=1).
6. Entrega no worktree em `tools-bash/ciclo_status.sh` + `tests/test_ciclo_status.py`. A instalação no diretório oficial das tools (ao lado de runs_status.sh) é feita pelo supervisor no merge — worker não escreve lá.

## MAPA
- tools-bash/ciclo_status.sh — ARQUIVO NOVO (Write inteiro; wrapper autônomo estilo runs_status.sh/entrega_verify.sh, sem source externo obrigatório).
- tests/test_ciclo_status.py — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest), fixtures em tempfile.mkdtemp.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva tests/test_ciclo_status.py (Write inteiro): 5 casos do item 5. `python3 -m pytest tests/test_ciclo_status.py -q` VERMELHO no baseline (arquivo da tool ainda não existe). Commit do aceite vermelho, assunto com CICLO-STATUS-01, git add só do teste.
2. Implemente tools-bash/ciclo_status.sh (Write inteiro). `bash -n` verde.
3. Testes verdes + rodar `--json` com fixtures herméticas e imprimir o JSON no RELATORIO-CICLO-STATUS-01.md.
4. Smoke real somente-leitura (se permitido pelo ambiente): rode `tools-bash/ciclo_status.sh --json` no baseline e anote a saída no relatório; se /root for inacessível, a saída MODE_SUPERVISOR é o resultado esperado — documente no relatório.
5. Commit do código + RELATORIO-CICLO-STATUS-01.md na raiz do worktree (2-5 linhas: arquivos, casos cobertos, saída do smoke, dívidas).

## REGRAS
- Provas como worker. Sem sleep, sem sudo, sem escrever fora do worktree. Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh. Sem ';' nos stops.
- git add só dos arquivos da missão; sem git reset/checkout/stash/clean.
- JSON de saída: 1 linha, sem literal US$ (use campo custo_usd numérico).

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd cd /home/worker/wt-CICLO-STATUS-01 && bash -n tools-bash/ciclo_status.sh
cmd cd /home/worker/wt-CICLO-STATUS-01 && python3 -m pytest tests/test_ciclo_status.py -q
cmd cd /home/worker/wt-CICLO-STATUS-01 && bash tools-bash/ciclo_status.sh --json | grep -q -F '"tool":"ciclo_status"'
cmd cd /home/worker/wt-CICLO-STATUS-01 && git log --format=%s | grep -q -F CICLO-STATUS-01
cmd cd /home/worker/wt-CICLO-STATUS-01 && grep -q -F PENDENTE_FECHO tests/test_ciclo_status.py
```
O stop 3 é o smoke E2E real com fixtures herméticas (dados falsos em tempdir). O stop 5 prova a tipagem das discrepâncias.

# MISSÃO RD-SUPGUARD-M2A — budget de turno + trail indexado dos turnos

Fonte: ROADMAP.md linha 55 (RD-SUPGUARD-M2, parte A; dep RD-SUPGUARD-M1 fechada).

## Contexto

O harness (harness.py do repo) hoje só tem teto de custo TOTAL da run (harness.py:1429-1440, `ledger.cost >= budget_usd`) e max_turns. Falta: (1) teto de CUSTO POR TURNO — um turno único pode queimar o orçamento inteiro; (2) trail indexado — o harness-trail.jsonl é apêndice puro e o supervisor relê o arquivo inteiro para achar um turno.

## Tarefa

1. Budget de turno em harness.py:
   - Novo parâmetro `turn_budget_usd` (default None = desligado; CLI `--turn-budget` em mission_run.py:~255 e plumbing até run_mission:1324).
   - No loop de turnos (harness.py:1424): DEPOIS da call que fecha o turno, calcule o custo do turno como delta do ledger. Se o delta > turn_budget_usd → veredito `FAIL` com motivo `TURN_BUDGET_EXCEDIDO` (não levante exceção; registre no trail e no resumo como os outros fins).
   - Pricing já existe no CostLedger (harness.py:~849-859, price/add/summary) — reutilize, não duplique.
2. Trail indexado:
   - Ao fim de cada turno, acrescente em um sidecar `harness-trail.idx.jsonl` no mesmo run dir uma linha JSON: `{"turno": N, "offset": <byte offset inicial da linha do turno no trail>, "ts": "...", "custo_usd": <delta>}` — um append O(1) por turno, nunca releia o trail inteiro para construir.
   - Índice é best-effort: falha de escrita do índice NUNCA derruba a run (log no trail, segue).
3. Testes OFFLINE (fixture com bridge_fn mock, sem rede, sem porta) cobrindo: turno dentro do teto segue; turno acima do teto para com TURN_BUDGET_EXCEDIDO; turn_budget None não muda comportamento atual; índice tem uma linha por turno e offsets apontam para linhas válidas do trail; índice com write quebrado não mata a run.
4. Prova como worker: `sudo -u worker bash -c 'cd /home/worker/wt-RD-SUPGUARD-M2A && python3 -m pytest tests/ -k supguard_m2a -q'` (ou a suíte existente se pytest não estiver no padrão do repo — verifique com `grep -n 'def test' tests/*.py | head`).
5. Escreva RELATORIO-RD-SUPGUARD-M2A.md na raiz do worktree (Write inteiro) com: contagem literal de tests/pass/fail, as linhas editadas (arquivo:linha), o marcador literal `M2A-OK`.
6. Commit cedo com o ID no assunto; `git add` restrito aos arquivos da missão.

PROIBIDO: tocar no orchestrator-consumer (isso é a parte B), git reset/checkout/stash/clean, escrever fora do worktree, chamadas de rede em teste.

## MAPA

- harness.py:1424 loop principal de turnos (`for turn in range(1, max_turns + 1)`)
- harness.py:1429-1440 checagens de budget/stop_flag existentes (modelo do novo check)
- harness.py:~849-859 CostLedger.price/add/summary (pricing por modelo, reutilizar)
- harness.py:~897 call_bridge (ponto onde o custo do turno é adicionado ao ledger)
- harness.py:1324 run_mission (assinatura — plumbagem do novo parâmetro)
- mission_run.py:~255 argparse `--budget` (adicionar `--turn-budget` ao lado)
- Trail atual: run_dir/run-*/harness-trail.jsonl (apêndice por turno)

```harness-stop
cmd cd /home/worker/wt-RD-SUPGUARD-M2A && grep -q -F 'TURN_BUDGET_EXCEDIDO' harness.py
cmd cd /home/worker/wt-RD-SUPGUARD-M2A && grep -q -F 'harness-trail.idx.jsonl' harness.py
cmd cd /home/worker/wt-RD-SUPGUARD-M2A && test -f RELATORIO-RD-SUPGUARD-M2A.md
cmd cd /home/worker/wt-RD-SUPGUARD-M2A && grep -q -F 'RD-SUPGUARD-M2A' RELATORIO-RD-SUPGUARD-M2A.md
cmd cd /home/worker/wt-RD-SUPGUARD-M2A && grep -q -F 'M2A-OK' RELATORIO-RD-SUPGUARD-M2A.md
```

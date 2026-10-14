# RELATORIO-HARNESS-SPRINT5-01 — prova de fogo: primeira entrega real executada pelo executor novo

**Veredito: PASS** (trabalho provado pelo supervisor; 3 runs do loop, custo total US$ 0,38) · commit `3a096860` branch `harness-sprint5-recover` · suíte do daemon **11/11 verde**

## Problema
Provar o caminho completo: missão mission-ops executada pelo LOOP do harness (glm), sem pane CLI no comando. Alvo: item 3 do self-heal do orquestrador (recover de pane morta com trilha `orch_recover` + dedupe).

## A saga (tabela pedida)

| Run | Turnos | Custo | Resultado |
|---|---|---|---|
| run1 (janela 6) | 80 (max_turns) | US$ 0,098 | FAIL honesto — só explorou; janela pequena pra arquivo grande, re-leu 3–4× |
| run2 | 80 (max_turns) | US$ 0,141 | FAIL honesto — **escreveu 90%** (impl + teste 10); parou no teto |
| run3 (NOTES.md + janela maior) | 65 | US$ 0,14 | FAIL `parou_sem_stop_condition` — **mas trabalho COMPLETO e VERDE 11/11**; marker do stop mal calibrado (`ℹ fail 0` vs `# fail 0`) |

**Total do executor novo: US$ 0,38** pela entrega completa do item 3 — contra US$ 14,75 da ORCH-05 (CLI) que entregou um fix de 1 linha.

## Descobertas técnicas
1. `node:sqlite` no `memoryStore.ts` exige Node 24+; a VPS tem Node 20 no PATH e **Node 26 em `/usr/local/bin/node`** — provas devem pinar o caminho absoluto
2. Dedupe do recover tinha `dedupe_window` indevido com `dedupePath` persistido — corrigido no run3 (pelo glm, TDD)
3. Stop-condition markers devem casar o formato REAL do reporter (ℹ vs #) — ajuste no contrato-alvo, não no harness
4. Preparação host-side precisa: worktrees devem nascer worker-owned (index/logs root-owned custaram o `.git2` e retrabalho)

## Não entregues (honesto)
- Evento `mission_completed` no spool do mission-ops: os runs terminaram em FAIL de stop-condition, o emissor só emite em PASS — prova fica para o primeiro run verde de produção
- cache_control no POST do harness: runs pagaram cache=0 (dívida conhecida)

## Prova
`verify-HARNESS-SPRINT5-01.json` (campo mission; suíte do daemon com node 26, grep orch_recover, commit).

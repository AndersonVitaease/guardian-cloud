# RELATÓRIO — HARNESS-SPRINT4-01 (productização: harness como executor de missões mission-ops)

**Branch:** `harness-sprint4-recover` (worktree `/home/worker/harness-s2`, evolução do v2 — sem duplicação)
**Data:** 2026-10-07

## Problema
O harness v2 provado (spike GO, s2 3/3 canárias, s3 missão real 3/3 stop-conditions) só era disparado manualmente; faltava a ponte determinística entre o mission-ops (contratos `missao-*.md`) e o executor.

## Entrega (itens 1, 2 e 5 do contrato)
1. **Adaptador** (`adaptador.py` + `tests/test_adaptador.py`): `missao-*.md` → config do harness. Bloco ` ```harness-stop``` ` inline vence; sem bloco, deriva `cmd` do primeiro comando determinístico em `## Provas` (`/usr/bin/python3 -m pytest ...`); sem prova determinística → **FAIL honesto no setup** (`AdaptadorSetupError`), sem adivinhar prova subjetiva. Suporta `{{HARNESS_CWD}}`, budget extraído das Regras (`budget US$ X`, default 1.0), mission id do título.
2. **Emissor mission-ops** (`mission_report.py` + `tests/test_mission_report.py`): run-summary → eventos `mission_completed`/`mission_failed` no spool `/opt/mission-events/spool.jsonl` (`source: harness-v2`, formato idêntico ao `notify.emit_event`), **dedupe por assinatura** (`kind|missionId|transição`) persistida em `harness-signatures.json` — a mesma transição nunca reemite; spool ausente não cria nada nem sobe.
3. **CLI comando único** (`mission_run.py`, item 5/runbook): `mission_run.py --mission <missao.md> --cwd <alvo>` — adaptador → loop → emissor, tudo num comando. Runbook de 1 página: `RUNBOOK-DESPACHO.md` (inclui o caminho pra sprint 5: dispatcher nativo).

## Provas
- Suíte: **48/48 verde** (`/usr/bin/python3 -m pytest tests/ -q` — 30 do v2 + 10 do adaptador + 8 do emissor).
- Gate verify mission-ops: `verify-HARNESS-SPRINT4-01.json` (3 cmds + 7 files, schema cmd+file com `mission` e `/usr/bin/python3` absoluto) — verde após o relatório abaixo ser escrito.
- FAIL honesto no setup provado: contrato sem prova determinística → exit 1 com `motivo: setup_adaptador`.

## Itens não feitos (honesto)
- **Item 3 (run real de missão mission-ops pelo loop)**: exigiria despacho de missão nova pelo supervisor (fora do meu alcance — sem pane CLI nesta missão) e budget de loop adicional; o caminho está pronto e documentado no runbook.
- **Item 4**: coberto parcialmente — verify no schema mission-ops feito; tabela spike/s2/s3/s4 abaixo.

## Custo
| Sprint | O que | Resultado |
|---|---|---|
| spike | GO/NO-GO do conceito | GO |
| s2 | 3 canárias | 3/3 stop-conditions |
| s3 | missão real (pypin no eng-mcp) | 3/3 stop-conditions |
| s4 | integração mission-ops → harness | adaptador + emissor + CLI, 48/48 |

Custo desta sessão (loop principal): ~US$ 0,80 de US$ 2 (estimativa pela price table; sem chamadas de loop glm nesta sessão — itens 1/2/5 são código determinístico + testes).

## Dívidas
- Item 3 (run real end-to-end com despacho do supervisor) — pendente pra sprint 5.
- Dispatcher nativo no supervisor (consumidor do spool) — runbook já desenha o caminho.

PASS
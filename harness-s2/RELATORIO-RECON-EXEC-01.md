# RELATORIO-RECON-EXEC-01 — reconciliação da rota de despacho (plano RECON-AUDIT-01, 799c9d50)

Data: 14/10. Executor: worker (missão RECON-EXEC-01). Fonte: ordem do operator ("vai").

## Contagem da suite por passo
Filtro: `python3 -m pytest tests/ -q -k "not despachante and not vigia_chat and not vigia_run" --tb=no`

| Passo | Resultado |
|---|---|
| 1. Baseline | 614 passed, 2 skipped |
| 2. Revert working tree orquestrador-ask.sh | 614 passed, 2 skipped |
| 3. Lane MEC_CONTRATO ausente (grep -c == 0) | confirmado, sem resíduo |
| 4. Revert whitelist env (a79e3286) | 614 passed, 2 skipped |
| 5. Shim despachar_missao.py (carregador da canônica) | 614 passed, 2 skipped |

## O que ficou KEEP / REVERT
- REVERT: diff de repasse VAR/env em `harness-s2/scripts/orquestrador-ask.sh` (working tree descartado via `git checkout --`).
- REVERT: whitelist env do commit a79e3286 (`git revert --no-edit`).
- KEEP: lane MEC_CONTRATO permanece ausente de `scripts/mecanico.sh` (c9bde2a8 já revertida; nada a fazer).
- KEEP→SHIM: `scripts/despachar_missao.py` local virou carregador da fonte única canônica `/opt/mission-events/scripts/despachar_missao.py` via `importlib.util.spec_from_file_location`, reexportando `main()`, `sh`, `fail` e demais símbolos do módulo (globals().update). Nenhuma lógica local.
- Nota lint: os 6/6 testes do gate de lint (`tests/test_despachar_missao_lint.py`) continuam verdes contra a canônica — a contagem da suite não mudou; o gate do lint segue ativo na canônica, então o patch abaixo é portabilidade de robustez, não correção de regressão.

## Artefato para a camada root
`runs/mecanico/patch-gate-lint-opt.patch` — diff de `git show b88e3ca9` (LINT-GATE-PORTA-01: gate do lint + validação completa na porta do dry-run), portado para a canônica /opt.

### Instruções do apply em /opt (missão root separada — NUNCA pelo worker)
1. Como root, em `/opt/mission-events` (repo da canônica):
   `git apply --check /home/worker/harness-s2/harness-s2/runs/mecanico/patch-gate-lint-opt.patch`
2. Se o check passar: `git apply /home/worker/harness-s2/harness-s2/runs/mecanico/patch-gate-lint-opt.patch`
   (o patch tem cabeçalho de caminho `harness-s2/scripts/despachar_missao.py`; usar `git apply --directory=` ou ajustar `-p` para mapear em `scripts/despachar_missao.py` da canônica).
3. Rodar a suite da canônica (lint 6/6) e commitar com mensagem LINT-GATE-PORTA-01-OPT.
4. Não aplicar via worker; não tocar em /root.

## Provas / stop-conditions
- STOP-1: relatório + patch + shim presentes; commit do worker no HEAD (RECON-EXEC-01).
- STOP-2: nada escrito em /opt ou /root (patch é arquivo no repo, não aplicado).
- STOP-3: sem git reset/stash/clean; checkout somente para orquestrador-ask.sh.
- STOP-4: suite final == baseline (614 passed, 2 skipped); nenhuma falha nova.
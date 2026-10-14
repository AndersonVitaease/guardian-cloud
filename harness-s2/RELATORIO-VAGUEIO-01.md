# RELATORIO — VAGUEIO-01

**Data:** 08/10/2026 (BRT) · **Entrega: vagueio** · Implementado pelo supervisor (rota governada — precedentes: escada §4, cirurgia Base44; o worker provou 2× que não segura implementação: BASE44-DECOUPLE 44–184 Bash/0 Write, missão VAGUEIO-01 própria 177 Bash/0 Write, $0,062).

## O problema (§3)

8 runs FAIL por max_turns hoje em que o worker passou a run inteira explorando
sem entregar (padrão: dezenas de Bash/Read, ZERO Write/Edit). A escada §4 não
cobre (só dispara em resposta vazia); o budget queima até o fim da janela.

## Entrega

1. **Detector de vagueio** (`harness.py`): turno produtivo = Write/Edit OU
   stop-condition nova verde; senão conta 1 vagueio. `VAGUEIO_TRIGGER`
   (default **8**, env `HARNESS_VAGUEIO_TRIGGER`) turnos CONSECUTIVOS →
   **FAIL "vagueio" antecipado** (não espera max_turns).
2. **Evidência no trail**: evento `_vagueio` com streak, trigger e sequência
   de tools dos últimos turnos; pane com linha `vagueio | Nx sem entregável`.
3. **Resumo**: campos `vagueio`, `turnos_vagueio`, `recomendacao`
   (nota + últimos 3 comandos Bash + 3 Reads do turno do gatilho).
4. **Recomendação de re-run** no CHECKPOINT.json (FAIL vagueio também grava
   checkpoint agora) — insumo cirúrgico pronto pra próxima janela.
5. **CLI**: `mission_run.py --vagueio on|off` (default on); `HARNESS_VAGUEIO=0`
   desliga. Convive com escada e advisor (detectores independentes).

## Provas

- `pytest tests/ -q` → **321 passed** (4 novos: dispara no gatilho, Write no
  meio zera, flag off = paridade, recomendacao no resumo).
- `tests/test_harness.py::test_janela_limitada_em_run_longa` ganha
  `vagueio=False` (cobertura dele é a TRIMMING da janela, não o abort).
- `mission_run.py --help` → exit 0.

## Ajustes de contrato da frente

- Stop-condition `tsc exit 0` inalcançável → contratos passam a exigir
  "zero erros NOVOS" via diff de contagem (ver BASE44-DECOUPLE).

## Veredito: DONE — commit branch `VAGUEIO-01` (merge em master pendente decisão operator).
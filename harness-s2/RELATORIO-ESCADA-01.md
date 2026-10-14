# RELATORIO-ESCADA-01 — §4 do roadmap: escada de camada automática

Entrega: escada — o harness sobe sozinho de camada quando o worker degenera.
Ordem do operator (08/10): aprovação da política de retry/escada. Implementação
em rota governada pelo supervisor (exceção pontual: 2 runs do flash FAILaram em
loop de exploração sem escrever — ESCADA-01 s/2214 e 01B s/2215).

## O que mudou

| Arquivo | Mudança |
|---|---|
| `harness.py` | Constantes `HARNESS_ESCADA` (env, default ON), `ESCADA_MODEL` (nex-agi/nex-n2.5-pro), `ESCADA_TRIGGER=2`. `run_mission(..., escada=None)`: detector de degeneração (resposta vazia = sem texto E sem tool_use) conta consecutivas; 2 seguidas → todas as chamadas LLM seguintes saem com `model_ativo = ESCADA_MODEL` até o fim da run. Evento `_escada` no trail, marca `| escalada` nas linhas llm do pane, resumo ganha `escalada`, `model_escalada` e `custo.escalada_usd` (contabilidade separada). |
| `mission_run.py` | Flag CLI `--escada on\|off` (default `on`) plumbada até `run_mission`. |
| `tests/test_escada.py` | 5 testes com bridge 100% mockada (zero chamada real): gatilho em 2 vazias, vazia isolada não sobe, flag off = paridade, evento no trail, custo separado (preços flash vs pro assertados). |

## Gatilho (design)

- **Degeneração** = resposta do LLM sem texto E sem tool_use (o caso real
  GUARDIAN-SITE-V4-02: 4 turnos `stop=max_tokens` vazios, $0,0024/turno).
- Turno produtivo (qualquer tool_use) zera o contador.
- 2 consecutivas → escalada permanente até o fim da run (sem desescala nesta
  versão — anotado como possível refinamento; o custo da fase é separado e
  auditável, então uma escalada indevida é barata e visível).
- Rollback: `HARNESS_ESCADA=0` ou `--escada off` (paridade exata).

## Provas

- `pytest tests/test_escada.py -q` → **5 passed**.
- `pytest tests/ -q` → **316 passed** (nenhuma regressão, advisor/despachante/
  autoretry intactos).
- Preço do modelo da escada já existia na tabela (`nex-agi/nex-n2.5-pro`:
  in 0.075 / out 0.25 / cache 0.015) — o Ledger calcula `escalada_usd` certo.
- E2E real (bridge real respondendo vazio por 2 turnos) fica como next step
  natural: a primeira missão que degenerar em produção agora escala sozinha —
  o trail/pane mostram `escada | glm-5.3-flash → nex-n2.5-pro`.

## Custos da frente

- 2 runs flash que falharam antes da exceção: $0,101 + $0,023 (trail preservado).
- Implementação supervisor: US$ 0 de worker; será medida na 1ª escalada real.

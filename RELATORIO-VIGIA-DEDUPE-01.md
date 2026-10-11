# RELATORIO-VIGIA-DEDUPE-01

## Causa raiz
O vigia por missao (`scripts/vigia_run.py`, spawnado por `despachar_missao.py:163-180`) emitia eventos sem qualquer controle de duplicidade: o `fim` podia ser reemitido para o mesmo (veredito, tentativas) e o `andamento` reemitido com o mesmo (turn, custo). Como o consumidor do chat relê o jsonl (`/tmp/vigia-<ID>.jsonl`), o mesmo aviso de término chegou 3x no chat (HEADLESS-TAB-02C, CICLO-STATUS-01B); no CICLO-STATUS-01B o jsonl tinha `andamento` duplicado (turn 17 emitido 3x) e turnos reiniciando após retry (turn 19 -> turn 4).

## Antes
- `_emit` gravava toda linha sem checagem: `fim` e `andamento` podiam repetir.
- Nenhuma leitura do próprio jsonl antes de emitir.

## Depois
- `_fim_ja_emitido(ev)`: antes de emitir `fim`, varre o jsonl; se já existe `fim` com o MESMO veredito+tentativas, não reemite (troca legítima de veredito/tentativa continua sendo emitida).
- `_ultimo_andamento_jsonl()` + cache `_ULTIMO_ANDAMENTO`: `andamento` com (turn, cost_usd) idêntico ao último emitido (em memória ou no jsonl) é suprimido.
- `_emit` agora grava no `VIGIA_JSONL_PATH` quando definido (testes/prova herméticos); em produção segue escrevendo no stdout, redirecionado pelo despachar para o jsonl — formato e caminho dos eventos inalterados.

## Prova
- `scripts/test_vigia_dedupe.py`: 3 testes pytest herméticos (fim duplicado 1x; andamento mesmo (turn,custo) 1x; fim com veredito diferente emitido) — 3 passed.
- `scripts/prova-VIGIA-DEDUPE-01.py`: roda o fluxo 2x com o mesmo estado; saída `VIGIA-DEDUPE-01-PROVA-OK` (fins=1, andamentos=1) gravada em `scripts/prova-VIGIA-DEDUPE-01.out`.

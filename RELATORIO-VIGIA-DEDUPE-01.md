# RELATORIO-VIGIA-DEDUPE-01

## Causa raiz
O vigia por missao (`scripts/vigia_run.py`, spawnado pelo `despachar_missao.py:163-180`) emite
eventos `andamento`/`fim` em `/tmp/vigia-<ID>.jsonl`. No dia 11/10 o consumidor do chat reenviou
o MESMO aviso de termino 3x (HEADLESS-TAB-02C e CICLO-STATUS-01B): o jsonl tinha eventos
`andamento` duplicados com mesmo turn (turn 17 emitido 3x) e turnos reiniciando apos retry
(turn 19 -> turn 4); o `fim` de HEADLESS-TAB-02C era unico no jsonl, mas era relido/reanunciado
por quem consome o arquivo. Nao havia dedupe no ponto unico de emissao (`_emit`).

## Antes
- `fim`: emitido toda vez que o loop chegava ao veredito; reemissoes/releituras geravam avisos repetidos no chat.
- `andamento`: reemitido com mesmo (turn, custo) — turn 17 apareceu 3x seguidas.

## Depois
- `fim`: `_emit` consulta o proprio jsonl (`_fim_ja_emitido`) e NAO reemite se ja existir `fim`
  com o MESMO (veredito, tentativas). Troca legitima de veredito/tentativa continua sendo emitida.
- `andamento`: dedupe em memoria (`_ULTIMO_ANDAMENTO`) + consulta ao jsonl
  (`_ultimo_andamento_jsonl`): nao reemite se (turn, custo) identicos ao ultimo evento emitido.
- Formato dos eventos e caminho do jsonl inalterados (consumidor externo depende).
- `_emit` grava no `VIGIA_JSONL_PATH` quando definido (testes/prova hermetica); em producao
  segue escrevendo no stdout redirecionado pelo despachar para `/tmp/vigia-<ID>.jsonl`.

## Provas
- `python3 -m pytest scripts/test_vigia_dedupe.py -q` -> 3 passed
  (fim duplicado nao emitido 2x; andamento mesmo (turn,custo) nao reemitido; fim com veredito
  diferente e emitido).
- `python3 scripts/prova-VIGIA-DEDUPE-01.py` -> `VIGIA-DEDUPE-01-PROVA-OK`
  (fluxo emitido 2x com o mesmo estado: jsonl final com exatamente 1 `fim` e 1 `andamento`).

# RELATÓRIO GB-DESP-ORDEM-01 — ordem do pipeline + destinos.py único

## Problema
O despachante (`scripts/despachar_missao.py`) spawnava a unit systemd ANTES do
guard de duplicidade (espelho nativo) e antes da montagem da aba — quando o guard
falhava (ESPELHO_NAO_NASCEU / UNIT_JA_ATIVA), a unit ficava VIVA e HEADLESS
(GB-THUMB-03 s137/s199, GB-OFFICE-CARD-01 s149/s151; contorno manual com
mount-espelho 2x no dia 13/10). Além disso, os caminhos de destino dos artefatos
(espelho de sala, ledger, aba, aviso, resumo, spool) estavam hard-coded
espalhados entre despachante e contratador, sem declaração única.

## O que foi feito
1. **Ordem do pipeline** (`scripts/despachar_missao.py`): o guard de duplicidade
   (`espelho_nativo.nascer_espelho`) foi movido para ANTES de qualquer spawn —
   a ordem agora é SEMPRE: (a) limpar_orfaos → (b) guard de duplicidade
   (espelho nativo + unit viva via UNIT_JA_ATIVA) → (c) spawn systemd-run →
   (d) mount-espelho/aba → (e) verificar_unit_com_aba. Falha em (b) = fail
   tipado SEM unit viva.
2. **`scripts/destinos.py` (NOVO)**: declaração única de DESTINOS — ABA (herdr
   via mount-espelho), ESPELHO_SALA (/tmp/ag-live), ESPELHO_NATIVO
   (/tmp/espelho-nativo), LEDGER (/root/.hermes/mission-state), AVISO
   (aviso_chat.sh), RESUMO (/tmp/resumo-<id>.json), SPOOL
   (/opt/mission-events/spool.jsonl) + helpers `resumo(mid)`,
   `espelho_sala(mid)`, `espelho_nativo_dir()`. `despachar_missao.py` importa e
   consome `destinos` (fim dos hard-codes de ag-live/resumo/spool);
   `python3 scripts/destinos.py` imprime o bloco markdown `## DESTINOS`.
3. **Contratador (`scripts/contratador.sh`)**: o contrato gerado passa a
   carregar o bloco `## DESTINOS` (worktree, aba esperada, caminho do
   relatório) — o worker e o fecho sabem onde postar sem adivinhar (lição
   GB-OFFICE-CARD-01).

## Prova
`prova-GB-DESP-ORDEM-01.py` (hermética, primeiro plano, dirs temporários via
ESP_DIR/HERDR_BIN):
- (a) espelho nativo pré-existente → 2ª chamada recusada; guard posicionado
  ANTES do systemd-run no fonte (assert por posição); fail tipado
  ESPELHO_NAO_NASCEU; nenhuma unit nova `harness-PROVA-*` no systemd
  (comparação antes/depois).
- (b) despachante importa `destinos` e usa `destinos.DESTINOS`/`destinos.resumo`;
  sem hard-codes remanescentes de `/tmp/ag-live` e `/tmp/resumo-`; contratador
  referencia `destinos.py`; todas as 7 chaves declaradas.
- (c) `python3 scripts/destinos.py` emite bloco `## DESTINOS`; contratador o
  injeta no contrato.
- (d) despacho normal com herdr fake: guard passa e a aba (pane fake0) nasce.
Saída final: `GB-DESP-ORDEM-01-PROVA-OK`.

## Stops
- `python3 -m py_compile scripts/despachar_missao.py scripts/destinos.py` — OK.
- `python3 prova-GB-DESP-ORDEM-01.py` → `GB-DESP-ORDEM-01-PROVA-OK` — OK.
- RELATORIO-GB-DESP-ORDEM-01.md — este arquivo.
- Commit com mensagem exata + worktree limpo.
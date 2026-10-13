# GB-DESP-ORDEM-01 — Ordem do pipeline + destinos únicos

## O que foi feito
1. **Ordem do pipeline no `scripts/despachar_missao.py`**: a sequência agora é
   (a) `limpar_orfaos(mid)` → (b) guard de duplicidade (espelho nativo + unit viva)
   → (c) spawn da unit systemd → (d) mount-espelho/aba → (e) `verificar_unit_com_aba`.
   Nenhum spawn antes de (a)+(b); falha no guard = fail tipado (`ESPELHO_NAO_NASCEU` /
   `UNIT_JA_ATIVA`) SEM unit viva headless (lição GB-THUMB-03 / GB-OFFICE-CARD-01).
2. **`scripts/destinos.py` (NOVO)**: declaração única de destinos — ABA (herdr via
   mount-espelho), ESPELHO_SALA (AG_LIVE_DIR), ESPELHO_NATIVO (/tmp/espelho-nativo),
   LEDGER (mission-state), AVISO (aviso_chat.sh), RESUMO (/tmp/resumo-<id>.json),
   SPOOL (AVISO_SPOOL). `despachar_missao.py`, `espelho_nativo.py` e `contratador.sh`
   consomem destinos.py — fim dos hard-codes espalhados.
3. **Contratador (`contratador.sh`/`contrato/`)**: contrato gerado carrega bloco
   `## DESTINOS` (worktree, aba esperada, caminho do relatório) — worker e fecho
   sabem onde postar sem adivinhar (lição GB-OFFICE-CARD-01).

## Prova (hermética, fakes via env — modelo prova-GB-DESP-CLEAN-01)
`prova-GB-DESP-ORDEM-01.py`: fakes em tmpdir (HERDR_BIN, HERDR_LEDGER_DIR,
HERDR_AG_LIVE_DIR, systemctl fake que só loga, ESP_DIR), importlib com env antes
do import. Asserts:
- (a) espelho nativo pré-existente → recusa tipada `ESPELHO_NAO_NASCEU` e
  systemctl fake NUNCA chamado (sem spawn) — ok.
- (b) destinos.py import único por despachante/espelho-nativo/contratador, sem
  hard-codes de /tmp/ag-live e /tmp/resumo- — ok.
- (c) `destinos.py` emite bloco `## DESTINOS` com ESPELHO_SALA — ok.
- (d) caminho normal com fakes → aba nasce no herdr fake e espelho de sala
  gravado no AG_LIVE_DIR fake — ok.
Resultado: `GB-DESP-ORDEM-01-PROVA-OK`.

## Notas
- Ajuste no despachante: saída JSON passa a incluir `"tab"` (alias de `"pane"`)
  para consumidores da prova; semântica inalterada.
- Prova editada apenas por correção sintática (duplicação de linhas no setup),
  sem enfraquecimento de asserts.
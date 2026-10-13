# MISSÃO GB-DESP-ORDEM-01 — Despachante e contratador: ordem certa + destino de postagem

## Problema (ordem do operador 13/10, repetido 3x hoje)
O despachante (`scripts/despachar_missao.py`) SPAWNA a unit systemd ANTES do guard de
duplicidade (espelho nativo) e antes da montagem da aba — quando o guard falha
(ESPELHO_NAO_NASCEU / UNIT_JA_ATIVA), a unit fica VIVA e HEADLESS (aconteceu com
GB-THUMB-03 s137/s199, GB-OFFICE-CARD-01 s149/s151; contornado à mão com
mount-espelho 2x hoje). Além disso, o despachante e o contratador NÃO SABEM onde
devem postar os artefatos de destino: espelho de sala (/tmp/ag-live), ledger
(/root/.hermes/mission-state), aba herdr, aviso (aviso_chat.sh) — cada um em
caminho hard-coded espalhado, sem uma declaração única de DESTINO.

## Escopo (fecha sozinho)
1. **Ordem do pipeline no despachar_missao.py** — a ordem passa a ser, SEMPRE:
   (a) limpar_orfaos(mid) → (b) guard de duplicidade (espelho nativo + unit viva)
   → (c) spawn da unit → (d) mount-espelho/aba → (e) verificar_unit_com_aba.
   Nenhum spawn ANTES de (a)+(b) passarem. Falha em (b) = fail tipado SEM unit viva.
2. **DESTINOS declarados num único lugar** (`scripts/destinos.py` NOVO): constante
   única com onde postar cada artefato — ABA (herdr via mount-espelho), ESPELHO_SALA
   (AG_LIVE_DIR), ESPELHO_NATIVO (/tmp/espelho-nativo), LEDGER (mission-state),
   AVISO (aviso_chat.sh), RESUMO (/tmp/resumo-<id>.json), SPOOL (AVISO_SPOOL).
   despachar_missao.py e espelho_nativo.py importam destinos.py (fim dos hard-codes).
3. **Contratador (`contratador.sh`/`contrato/`)**: o contrato gerado passa a carregar
   os destinos da missão (worktree, aba esperada, caminho do relatório) em bloco
   `## DESTINOS` — o worker e o fecho sabem onde postar sem adivinhar (lição
   GB-OFFICE-CARD-01: worker leu o repo VIVO porque não sabia o destino do trabalho).

## MAPA (âncoras reais — lidas no repo, branch base rd-segue-01)
- scripts/despachar_missao.py:204+ (limpar_orfaos já existe), :237-244 (guard
  DESPACHO-UNICO), spawn systemd-run logo antes de :243 (ordem errada: spawn
  acontece antes do guard/aba), :29 verificar_unit_com_aba.
- scripts/espelho_nativo.py (porta única GB-FUNIL-UNICO-01).
- contratador.sh + contrato/ (geração de contrato).

## PROVA (stop) — LIÇÃO DAS 3 TENTATIVAS QUE FALHARAM: use fakes via env
MODELO EXATO: prova-GB-DESP-CLEAN-01.py (leia-a como referência — fechou PASS
com esse padrão). NUNCA chame o despacho real nem systemd verdadeiro na prova:
- fakes em tmpdir via env (HERDR_BIN fake herdr, HERDR_LEDGER_DIR,
  HERDR_AG_LIVE_DIR, PATH com systemctl fake que só loga);
- load do despachar_missao via importlib com env ANTES do import;
- asserts: (a) espelho nativo pré-existente => recusa tipada e systemctl fake
  NUNCA chamado (não há spawn); (b) destinos.py import único por despachante,
  espelho-nativo e contratador (sem caminho duplicado — grep prova); (c)
  contrato gerado contém bloco `## DESTINOS`; (d) caminho normal com fakes =>
  aba nasce no fake herdr e espelho de sala gravado no AG_LIVE_DIR fake.
Saída: `GB-DESP-ORDEM-01-PROVA-OK`. Se um assert falhar: conserte o CÓDIGO,
nunca a prova para esconder falha (editar prova só por bug sintático — documente).

## STOPS
```harness-stop
cmd cd /home/worker/wt-GB-DESP-ORDEM-01 && python3 -m py_compile scripts/despachar_missao.py scripts/destinos.py
cmd cd /home/worker/wt-GB-DESP-ORDEM-01 && python3 prova-GB-DESP-ORDEM-01.py 2>&1 | grep -q -F 'GB-DESP-ORDEM-01-PROVA-OK'
cmd cd /home/worker/wt-GB-DESP-ORDEM-01 && test -s RELATORIO-GB-DESP-ORDEM-01.md
cmd cd /home/worker/wt-GB-DESP-ORDEM-01 && test "$(git log -1 --format=%s)" = "GB-DESP-ORDEM-01: ordem do pipeline (guard antes do spawn) + destinos.py unico (despachante e contratador sabem onde postar)"
cmd cd /home/worker/wt-GB-DESP-ORDEM-01 && test -z "$(git status --porcelain)"
```

## REGRAS
CÓPIA dos scripts no worktree (scripts/); o vivo fica em /home/worker/harness-s2 —
só LEITURA do vivo para consultar; o ship aplica via âncoras mínimas. Prova em
PRIMEIRO plano (nunca nohup/&). Sem sudo. Sem git reset/checkout/stash. Comando
falhou 2x → NÃO repita: leia e adapte. Budget US$0,35. Turnos max 40.

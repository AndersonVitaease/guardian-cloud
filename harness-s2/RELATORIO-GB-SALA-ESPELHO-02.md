# RELATORIO GB-SALA-ESPELHO-02

## Ciclo completo (nascimento -> sala -> pouso -> sai da sala)

1. **Nascimento** — `scripts/despachar_missao.py`, apos o bloco mount-espelho
   ter SUCESSO (`tab != None`), grava atomicamente
   `/tmp/ag-live/<MID>.espelho.json` (cria o dir se faltar; fail-open: se a
   escrita falhar, apenas acrescenta aviso e o despacho segue). Formato:
   `{"id", "tab_id", "pane_id", "workspace_id" (parte de tab antes de ':'),
   "status": "running", "started_at" (ISO com TZ)}` — igual aos fixtures
   `tests/fixtures/TESTE-ESPELHO-*.espelho.json`. Sobrescreve em retry (a
   ponte deduplifica por id, sem session_start duplicado).
2. **Sala** — a ponte do escritorio (porta 8113) drena `/tmp/ag-live/` e ve
   o espelho `running`: a missao aparece na sala do Guardian como viva.
3. **Pouso** — no fecho (PASSE ou FAIL), `scripts/fechar_mirror.py`
   renomeia `<MID>.espelho.json` -> `<MID>.espelho.pousado.json`
   (os.replace, fail-open; dir via `AG_LIVE_DIR`, default `/tmp/ag-live`).
4. **Sai da sala** — a ponte observa o rename: sem `<MID>.espelho.json`
   running, a missao deixa de aparecer como viva na sala.

## Missao viva de hoje (GB-THUMB-03) apos a aplicacao

Com o patch aplicado, o proximo despacho de GB-THUMB-03 via
`despachar_missao.py` (caminho do harness, mount-espelho) grava
`/tmp/ag-live/GB-THUMB-03.espelho.json` no nascimento — a ponte passa a ve-la
na sala (antes: gap provado, sala so com fantasmas). Quando o fecho rodar
`fechar_mirror.py`, o espelho pousa (`.espelho.pousado.json`) e GB-THUMB-03
sai da sala.

## Testes

`tests/test_sala_espelho.py` (unittest stdlib, hermetico, tmpdir como
AG_LIVE_DIR): (1) gravacao no formato do fixture; (2) sobrescrita em retry;
(3) fail-open com dir ilegivel; (4) pouso renomeia e ponte nao ve mais
running; (5) fecho sem espelho = noop tipado. Suite verde:
`GB-SALA-ESPELHO-02-PROVA-OK`.
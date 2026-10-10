# MISSÃO RD-H1H2-REPORT-01 — janela de leitura (H1/H2 re-port) no harness atual

Objetivo: portar o COMPORTAMENTO da janela de leitura (original RD-HARNESS-LEITURA-01/H4, em
wt-H4-VAGUEIO, commit da7004bd — NÃO force merge, re-porte sobre o código ATUAL) para
`harness.py` do worktree. Problema medido (PASS-OCO-01): 9 leituras recusadas seguidas com
write=0 — o streak de vagueio conta turno de leitura desde o turno 1 e queima tentativas
inteiras antes do 1º Write.

## ESTADO ATUAL (verificado pelo despachante em 10/10)
- Worktree: `/home/worker/wt-RD-H1H2-REPORT-01` (branch `rd-h1h2-report-01`, de rd-segue-01 @ 19067527).
- Suíte atual: 503 passed, 2 skipped (`python3 -m pytest tests/ -q`, como worker).
- `harness.py` NÃO tem `HARNESS_READ_WINDOW` (code_find 'janela|leitura_recusada|read_window' em scripts/: só checkpoint/deploy_janela/cache_stream — nada na janela do vagueio).
- Desenho atual do vagueio: `HARNESS_VAGUEIO`/`VAGUEIO_TRIGGER` (harness.py:68-69); contagem no bloco `if vagueio:` (~harness.py:1288-1296: `_produtivo` zera, senão `vagueio_streak += 1`); injeção de nudge tipada JÁ existe como padrão na FORÇA-ESCRITA (~harness.py:1313-1324: `win.add(turn, ..., nudge=...)` + `emit` + `pane.write`) — copie esse padrão.
- Recusas com dica governada (code_find/git_peek no redirect) JÁ existem no harness atual (harness.py:209-341) — NÃO re-faça.

## MAPA
- harness.py | VAGUEIO_TRIGGER | L69 | âncora: logo abaixo, adicionar `HARNESS_READ_WINDOW = int(os.environ.get("HARNESS_READ_WINDOW", "12"))`, `_READ_GOVERNED_TOOLS = frozenset(("code_slice", "code_find", "git_peek", "trail_tail", "mission_cost", "queue_peek", "runs_status", "flights"))` e a função `_turno_so_leitura_governada(uses)` (True se TODO tool_use do turno é leitura governada; para `Bash`, resolver a tool do JSON `{"tool": ...}` ou argv após `tool_bash`, como no original; `HARNESS_READ_WINDOW=0` = paridade antiga).
- harness.py | bloco `if vagueio:` | ~L1288-1296 | no ramo não-produtivo: se `turn <= HARNESS_READ_WINDOW` e `_turno_so_leitura_governada(uses)`, o turno é NEUTRO (nem incrementa nem zera `vagueio_streak`); fora da janela, conta normal (paridade).
- harness.py | mesmo bloco | manter contador NOVO `leitura_streak` (turnos só-leitura-governada CONSECUTIVOS, independente da janela; zera em turno produtivo) e, quando `leitura_streak >= HARNESS_READ_WINDOW` e o aviso ainda não foi usado (`leitura_aviso_usada`, 1x por run), injetar nudge tipado no padrão da FORÇA-ESCRITA: `win.add(turn, ..., nudge='AGIR-OU-PARAR (turno N): você leu por N turnos seguidos sem escrever. Pare de ler: escreva AGORA a melhor primeira versão do entregável com o que já leu, ou declare o bloqueio em texto.')` + `emit({"turno": turn, "tool": "_janela_leitura", "tipo": "AGIR_OU_PARAR", "streak": leitura_streak, ...})` + `pane.write`/`flush`.
- tests/test_vagueio.py | VagueioBridge/Base/go | L36-110 | PADRÃO de fake bridge dirigido por roteiro + `harness.run_mission(..., ledger=harness.Ledger(prices), bridge_fn=bridge, escada=False)` — reutilize o desenho no arquivo novo (mas em pytest, ver Aceite).
- harness.py | `HARNESS_ADVISOR`/`FORCA_ESCRITA` | patch de ATRIBUTO de módulo nos testes (setUp/fixture), como test_vagueio.py:87-89 — advisor OFF e FORCA_ESCRITA=0 nos testes do roteiro.

## Regras
- PROIBIDO git reset/checkout/stash/clean; só git add/commit.
- Arquivo novo (teste) = Write inteiro; arquivo existente (harness.py) = ler o trecho exato com `sed -n 'A,Bp'` imediatamente antes de cada Edit e copiar o old_string literal; old_string de UMA linha distinta quando possível.
- Sem sudo nos comandos; python/pytest sempre como worker; sem `cat/head/ls/grep -A`/`;`.
- NÃO mexer em despacho/fila/systemd (DESP-CWD-01 não entra); NÃO instalar tools; deploy é do supervisor.
- Escrever cedo: faça o patch do harness.py e o teste já nos primeiros turnos; não explore além do mapa.

## Stops
```harness-stop
cmd cd /home/worker/wt-RD-H1H2-REPORT-01 && python3 -m pytest tests/test_janela_leitura.py -q
cmd cd /home/worker/wt-RD-H1H2-REPORT-01 && python3 -m pytest tests/ -q
cmd cd /home/worker/wt-RD-H1H2-REPORT-01 && git log -1 --pretty=%s | grep -q 'RD-H1H2-REPORT-01'
cmd cd /home/worker/wt-RD-H1H2-REPORT-01 && grep -q 'RD-H1H2-REPORT-01' RELATORIO-RD-H1H2-REPORT-01.md
```

## Aceite
1. `tests/test_janela_leitura.py` NOVO, pytest com FUNÇÕES (não classes unittest) e fakes (bridge fake dirigida por roteiro no padrão de test_vagueio.py), cobrindo: (a) N turnos só-leitura-governada dentro da janela NÃO disparam vagueio nem a nudge; (b) turno só-leitura FORA da janela conta pro vagueio (paridade antiga); (c) `leitura_streak >= HARNESS_READ_WINDOW` injeta a nudge tipada UMA vez (evento `_janela_leitura` no trail, texto contém AGIR-OU-PARAR; 2ª vez não injeta); (d) `HARNESS_READ_WINDOW=0` = paridade antiga (leitura conta como vagueio desde o turno 1); (e) turno com Write é produtivo (zera streaks).
2. Suíte completa verde (regressão: 503 passed baseline + os novos, como worker).
3. Commit com `RD-H1H2-REPORT-01` no subject; `RELATORIO-RD-H1H2-REPORT-01.md` no worktree contendo o ID e o que mudou (símbolos/linhas).

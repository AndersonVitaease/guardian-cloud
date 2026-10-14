# RELATORIO-HARNESS-SPRINT2-01 — harness v2: de spike a runner de missões reais (glm-5.3-flash)

**Data:** 2026-10-07 · **Repo:** `/home/worker/harness-s2` (git, worker) · **Modelo:** `z-ai/glm-5.3-flash` via bridge :8103 (só leitura do bridge/price-table) · **Veredito: PASS**

## Problema
Generalizar o loop do spike (GO em 07/10) para um runner de missões de 1 comando e provar isso numa canária média, com vários entregáveis, criada do zero 3 vezes, sem intervenção humana. Também fechar as dívidas do spike: artefatos copiados entre runs, janela sem compactação e latência não medida.

## Entregas

### 1. harness.py v2 — `harness.py --contract <path.md> --cwd <dir> --budget 3.0 --max-turns 60 [--seed N] [--raw-window K]`
- **(a) Stop-conditions no contrato:** bloco ```` ```harness-stop ```` com linhas `file <caminho>` (arquivo-prova não vazio), `cmd <shell>` (verificador com exit 0) e `marker <TEXTO> <caminho>`. O harness checa tudo sozinho depois de cada turno e para assim que todas forem cumpridas. `{{SEED}}` no contrato é substituído pelo seed.
- **(b) Janela com compactação:** o contrato vai **sempre** no `system`, reenviado em toda chamada. Só as últimas K trocas ficam cruas (padrão 6), com os pares `tool_use`/`tool_result` íntegros. As trocas mais antigas viram 1 linha cada num **sumário rolante** dentro da 1ª mensagem user. O sumário tem teto de 60 linhas e o excedente vira uma linha de contagem, então a janela tem tamanho limitado. Resultados longos são truncados em 4000 caracteres.
- **(c) Retry/backoff próprio:** 3 tentativas com backoff 2^n (1 s, 2 s). Depois disso a run fecha com FAIL honesto (`bridge_error:…`), sem martelar. Corpo 200 com `type:error` também conta como erro.
- **(d) cwd isolado por run:** `<cwd>/run-<ts>-seed<N>-<pid>` é criado **novo e vazio** (`exist_ok=False`). Read/Write/Edit ficam confinados a esse cwd (`../` e caminhos absolutos fora dele dão `PermissionError`). O Bash roda no cwd, mas não é sandbox (ver limites).
- **(e) Budget:** abort antes e depois de cada chamada quando o custo acumulado chega ao teto (`budget_excedido`). O custo vem da price-table do orchestrator (só leitura) e o acumulado sai no resumo. Também há abort por `max_turns` e por `parou_sem_stop_condition` (5 turnos seguidos sem tool e sem stop-condition).

### 2. Trilha estruturada — `harness-trail.jsonl` (1 por run, dentro do cwd da run)
Uma linha JSON por passo:
- `_inicio`: stop-conditions declaradas, seed, budget.
- `llm`: ts, turno, latencia_ms, custo_usd, bytes, stop_reason, retries, tamanho da janela, linhas do sumário, cum_usd.
- uma linha por tool: ts, turno, tool, input resumido (para Write só path + bytes), latencia_ms, bytes do resultado, is_error.
- `_stop_check`: `stop_tick` (condições que **viraram** verdes nesse turno) e o estado de todas.
- `_resumo` no fim: veredito, motivo, turnos, custo total, custo/turno, p50/p99/max de latência por turno, stop-conditions cumpridas (n/N).

Com isso o supervisor lê o JSONL e não precisa raspar o pane.

### 3. Canária média — 3/3 PASS do zero, sem intervenção
O contrato `canary/contrato-canaria-media.md` pede um utilitário CLI com 3 subcomandos argparse, ≥10 testes pytest, README e `verify.json` de si mesmo (schema cmd+file com `mission`), mais o relatório. O **tema depende do seed** (seed % 3 → `textkit` / `numkit` / `listkit`, com interface de I/O exata), então copiar o artefato de outra run não passa. O verificador próprio é `canary/check_canary.py`: sondas de I/O exatas, `--help` de cada subcomando, subcomando inválido saindo ≠ 0, pytest com ≥10 testes passando, README citando cada subcomando, e cada `cmd`/`file` do `verify.json` do modelo executado e checado.

**Runs oficiais** (harness no commit `32d3a1a`, seeds 11/12/13 → temas 2/0/1):

| run | seed → tema | turnos | custo US$ | custo/turno | p50 ms | p99 ms | testes | stop-conds | retries |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 11 → listkit | 5 | 0.002633 | 0.000527 | 2324 | 8571 | 16 passed | 4/4 | 0 |
| 2 | 12 → textkit | 5 | 0.003941 | 0.000788 | 1569 | 10790 | 17 passed | 4/4 | 0 |
| 3 | 13 → numkit | 4 | 0.002006 | 0.000502 | 1723 | 4398 | 14 passed | 4/4 | 0 |
| **total** | | **14** | **0.008580** | **0.000613** | **1569** | **10790** | | **3/3 PASS** | 0 |

Trilhas: `runs/canaria/run-*/harness-trail.jsonl`. Depois das runs, rodei de novo e de forma independente o `check_canary.py` e o pytest em cada cwd: os 3 deram `CANARIA PASS` e pytest verde. Pela trilha, todos os arquivos foram criados por `Write` no próprio cwd, sem nenhum `cp` nem leitura de fora. Isso fecha a dívida dos artefatos copiados.

**Evidência extra:**
- **Lote A preliminar** (seeds 1/2/3, harness `fa5fe07`+canária, antes de a trilha gravar o input das tools): também 3/3 PASS, 14 turnos, US$ 0.008509. Está em `runs/lote-A-preliminar/`.
- **Run de compactação** (seed 14, `--raw-window 2` — flag adicionada no commit final, após as runs oficiais; bridge real): PASS 4/4 em 10 turnos, US$ 0.00475. A janela ficou estável em 5 mensagens do turno 3 ao 10 e o sumário cresceu 0→10 linhas, com custo/turno estável (~0.0003–0.0007). Isso prova (b) contra o modelo real, e não só na suíte. Nas canárias com janela padrão 6 a compactação não chegou a disparar porque as runs fecharam em ≤7 turnos. Trilha em `runs/compactacao/`.

### 4. Comparativo medido

| alvo | runs | turnos | custo total US$ | **custo/turno US$** | p50 ms | p99 ms |
|---|---|---|---|---|---|---|
| (a) spike NOROOT (harness v1, `harness-spike-01/harness-run.jsonl`) | 3 | 22 | 0.006939 | **0.000315** | 900 | 4800 |
| **harness v2 — canária média (oficial)** | 3 | 14 | 0.008580 | **0.000613** | 1569 | 10790 |
| harness v2 — lote A preliminar | 3 | 14 | 0.008509 | 0.000608 | 1947 | 8072 |
| harness v2 — compactação (raw-window 2) | 1 | 10 | 0.004750 | 0.000475 | 3341 | 29864 |
| (b) CLI hoje (SHIP, número do enunciado) | — | — | — | **0.0054** | não medido | não medido |

Leitura:
- **v2 vs CLI:** US$ 0.000613 contra 0.0054 por turno, ou seja **~8,8× mais barato por turno** no mesmo glm-5.3-flash. Contra o spike, o custo/turno quase dobrou: a canária média escreve 2–4 arquivos por turno (mais tokens de saída) e o system carrega um contrato maior. Por run o custo segue na casa de US$ 0,003 (US$ 0,0029/run contra US$ 0,0023/run do spike), e o alvo agora tem 5 entregáveis em vez de 1.
- **Latência:** p50 de 1,6 s por turno. O p99 com n=14 é praticamente o máximo (10,8 s), uma amostra pequena. O p99 do spike (4,8 s) vem de `dt` com resolução de 0,1 s. O outlier de 29,9 s (turno 1 da run de compactação) foi do lado do bridge, porque o harness não fez retry (retries=0).
- Não há p50/p99 do CLI medidos no disco. O US$ 0,0054/turno vem do enunciado, sem reprocessamento meu.

### 5. Suíte própria — 30/30 verde
`/usr/bin/python3 -m pytest -q tests` → `30 passed` (29 originais + 1 de `pin_python`, adicionado no fix do gate).
- `tests/test_harness.py` (24) cobre, todos sem rede (bridge falso injetado):
  - parse/check de stop-conditions;
  - janela: compactação, pares tool_use/tool_result íntegros, tamanho limitado em 200 turnos, truncagem, nudge;
  - backoff: exatamente 3 tentativas com sleeps [1,2] e depois `BridgeError`, recuperação na 2ª tentativa, FAIL de run em erro de bridge;
  - budget-abort, max_turns, parada sem stop-condition, janela limitada numa run longa;
  - isolamento: cwd novo e vazio por run, 2ª run não vê artefatos da 1ª, tools confinadas ao cwd;
  - campos da trilha, `pctl` e preço do ledger.
- `tests/test_check_canary.py` (6, contando o de `pin_python`): a solução de referência passa nos 3 temas; tema errado, <10 testes, verify sem `mission`/file inexistente e README incompleto falham.

## Achados
1. **O glm erra a aritmética do contrato (2/2 vezes):** com seed múltiplo de 3 (seed 3 no lote A, seed 12 no oficial), o modelo calculou o tema errado e escreveu `listkit` primeiro. O verificador acusou pelo stop-condition `cmd` e o modelo se corrigiu sozinho (na seed 12 ainda apagou os arquivos errados), fechando PASS sem humano. **Lição para contratos:** parâmetros derivados (tema, caminhos, ids) devem ser **calculados pelo harness** e injetados prontos, sem pedir ao modelo para computar.
2. **O stop-condition `cmd` é o que segura a qualidade:** `file` e `marker` são fáceis de cumprir. Quem pegou o erro de tema foi o verificador executável. Toda missão real deve declarar ao menos um `cmd` verificador.
3. **Restrição registrada verbatim:** `touch: cannot touch '/opt/mission-events/verify-HARNESS-SPRINT2-01.json': Permission denied` (`/opt/mission-events` é `root:root 755`; worker uid=993). Relatório e verify ficaram no repo, como no spike. Para irem a `/opt/mission-events`, o supervisor/root precisa copiar ou dar permissão. Não fiz contorno.

4. **Close recusado pelo gate (1ª tentativa) — corrigido:** o pré-close gate deu `verify.py` exit=2 em P2-cmd-1 (suíte). Causa reproduzida: no ambiente do gate, `python3` resolve para o venv do hermes (`/root/.hermes/installs/…`), que não tem pytest (`No module named pytest`, exit 1). Correção: todos os cmds do `verify-HARNESS-SPRINT2-01.json` agora fixam `PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` (mesmo padrão dos manifestos SUITE-LOCK-01) e `PYTHONDONTWRITEBYTECODE=1`, para não deixar `__pycache__` do root no repo do worker. Prova: com um `python3` sem pytest à frente do PATH, o manifesto antigo reproduz o exit 1 e o novo passa 7/7 cmds + 8/8 files. O `verify.py` completo não roda como worker: ele quebra ao adquirir o suite-lock, que é do root. Por isso a reprodução executou os cmds do manifesto da mesma forma que o `proof_cmd` (shell=True). A validação final é a re-execução do gate.

5. **Finding — o sandbox do gate usa um venv sem pytest:** o sandbox do runner do gate resolve `python3` para um venv **sem pytest**, enquanto `/usr/bin/python3` tem o pytest 7.4.4. O gate reprovou por ambiente, não por qualidade. Correção definitiva, a pedido do supervisor:
   - **(i) manifesto:** todos os cmds do verify chamam `/usr/bin/python3` com path absoluto (ids e expect_exit intocados);
   - **(ii) verificador:** `canary/check_canary.py` usa `/usr/bin/python3` explícito nas sondas, no pytest e nos cmds do `verify.json` de cada run, onde troca o `python3` solto via `pin_python()`, coberto por um teste novo.

   Conferência com `/usr/bin/python3`, rodada tanto no PATH normal quanto com o venv sem pytest na frente: suíte **30/30** (as 29 originais + 1 teste de `pin_python`), **3× CANARIA PASS** (seeds 11/12/13), manifesto 7/7 cmds + 8/8 files. **Recomendação para a frota:** manifestos e verificadores devem sempre usar `/usr/bin/python3` absoluto.

## Limites / dívidas
- O Bash da run **não é sandbox**: o modelo poderia ler ou escrever fora do cwd via shell. O isolamento é por cwd novo + confinamento de Read/Write/Edit + auditoria pela trilha (input das tools). Sandbox de verdade (namespace/uid por run) fica para depois.
- O p99 com n pequeno (14 turnos) é indicativo. Para estatística real, a frota precisa acumular trilhas.
- O sumário compactado é extrativo (1 linha por passo, sem LLM). É suficiente nas canárias, mas não foi testado em missões de mais de 60 turnos.
- Custo de cache sempre 0: o bridge não reporta `cache_read_input_tokens` para o glm.

## Fora de escopo (registrado)
- Roteamento por modelo no :8103 (P1; missão própria depois de BRIDGE-CACHE-01).
- Integração com o dispatcher do mission-ops (sprint 3).
- Execução como daemon.

## Custo da missão
| item | US$ |
|---|---|
| runs oficiais (3) | 0.008580 |
| lote A preliminar (3) | 0.008509 |
| run de compactação (1) | 0.004750 |
| 2 smokes manuais do bridge (curl) | 0.000174 |
| **total** | **0.022013** (budget US$ 3, ou seja 0,73%) |

O desenvolvimento do harness em si (esta sessão de Claude Code) não entra nessa conta. Ela mede só as chamadas glm feitas pelo harness e pelos smokes.

## Veredito: PASS
3/3 canárias médias PASS do zero, com cwd isolado, seeds variados, stop-condition automática e zero intervenção. Suíte 30/30. Comparativo medido: ~8,8× mais barato por turno que o CLI. **PASS + PARE**

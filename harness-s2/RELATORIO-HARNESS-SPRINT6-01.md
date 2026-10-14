# RELATÓRIO — HARNESS-SPRINT6-01 (07/10/2026, BRT)

**Executor:** supervisor (hermes), assumindo após turno do worker travar ~50 min
no upstream (grep trivial sem resposta; nudge com token do operator aplicado e
turno interrompido por ordem explícita do operator: "pare o worker, finalize a
missão e termine vc"). Worker parado no prompt (❯ idle); trabalho assumido
pelo supervisor com o mesmo contrato.

## Entregas

1. **Stop-check tolerante a formato** ✅ — `harness.marker_regex()`:
   espaços viram `\s+`; todas as palavras menos a última viram grupo
   OPCIONAL (reporter pode trocar `fail` por símbolo `✖` ou omitir);
   prefixo de reporter (`#`, `ℹ`, `✖`, `✔`, `✗`, `*`) sempre opcional;
   **`^` no início do marker declarado vira âncora de linha (escape
   automático, semântica multiline)** — nunca um literal. Novo kind
   **`cmdout <marker> :: <shell>`** no bloco `harness-stop`: roda o shell,
   exige exit 0 E casa o marker contra a **saída bruta** com a regex
   flexível. `marker` (arquivo) também passa a usar a regex — `fail 0`
   engata em `# fail 0`, `ℹ fail 0` e `✖ 0` (3 formatos testados).
   Commits: `4bf58ed8` (item 1), `98d412a8` (item 2).
2. **cache_control no POST** ✅ (entrega 2, já pronta antes da sprint —
   commit `635ed722`, sprint 5.1) + **emissor** (`791776f9`) — não refeitas.
3. **`--pane` no mission_run.py** ✅ — `pane_mount()` monta os argvs
   determinísticos (`herdr tab create --title RUN:<id>` + `herdr pane
   send-text` com espelho `tail -F` da trilha); runtime cria a tab, extrai
   o pane-id, envia o espelho (puro shell, ZERO CLI Claude), roda a run
   localmente e imprime a linha final `veredito + custo_usd + trilha`.
   **herdr indisponível → `PaneUnavailable`, falha honesta ANTES de rodar**
   (exit 1, motivo `pane_indisponivel`); espelho é só visibilidade — nunca
   bloqueia a run. Montagem unit-testada com mock (herdr inacessível do
   sandbox de teste), `tests/test_mission_run_pane.py`.
4. **Canária E2E** ✅ — `canary/contrato-sprint6-canary.md`: NOTES.md +
   STATUS.txt com data + **última linha `ℹ fail 0` (TAP sem # — de
   propósito)** + RELATORIO.md. Run SEM `--pane` (pane é do supervisor):
   **PASS em 4 turnos, 5/5 stop-conditions, US$ 0,000815, latência p50
   875 ms** — o `cmdout` engatou no formato ℹ na primeira. **Evento
   `mission_completed` real no spool do mission-ops:**
   `{"ts": "2026-10-07T18:49:03Z", "event": "finding", "kind":
   "mission_completed", "missionId": "HARNESS-SPRINT6-CANARY-01", ...,
   "source": "harness-v2"}` (linha integral em
   /opt/mission-events/spool.jsonl).
5. **RUNBOOK-DESPACHO v2** ✅ — caminho `--pane` + **regra do operator**
   (runs só no herdr, run fora do herdr = PROIBIDO).

## Custo

| Item | Valor |
|---|---|
| Suíte (63 testes) | US$ 0,00 (determinística, zero LLM) |
| Canária E2E (4 turnos, glm-5.3-flash) | **US$ 0,000815** |
| Total da sprint | **US$ 0,000815** (budget: US$ 0,50) |
| Latência p50 / p99 / max | 875 ms / 1283 ms / 1283 ms |

## Findings (dívidas honestas, não bloqueiam)

- **Adaptador não tolera vírgula decimal pt-BR no budget**: `budget US$ 0,50`
  no contrato → `_RE_BUDGET` (`[\d.]+`) não casa → budget 0.0 → FAIL
  imediato `budget_excedido` com 0 turnos. Corrigido no contrato da canária
  (para `US$ 0.50`); o regex do `adaptador.py` segue intolerante (sprint 7).
- **Emissor exige quem escreve no spool**: worker não-gráfico não tem
  permissão em `/opt/mission-events/spool.jsonl` (PermissionError honesto);
  a run E2E rodou como supervisor (root), precedente do sprint 5. Se runs
  futuras forem do worker, precisa de rota de escrita auditada no spool.
- **Turnos do upstream (CLI) seguem lentos** (p50 ~65 min no ledger) — fora
  do escopo do executor; a canária da ponte :8103 (flash) tem p50 < 1 s.

## Provas

- Suíte: **63/63 verde** (`pytest tests/ -q`, 48 anteriores + 15 novos).
- verify-HARNESS-SPRINT6-01.json (campo `mission`, provas cmd+file absolutas).
- Trail da canária: `runs/canaria-sprint6/run-20261007-154900-seed0-1847398/harness-trail.jsonl`.

Veredito: **PASS**

PARE

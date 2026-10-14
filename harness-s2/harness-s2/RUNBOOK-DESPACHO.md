# RUNBOOK — despachar uma missão mission-ops pelo harness v2 (1 comando)

**Para:** supervisor do mission-ops. Caminho pra sprint 6 (dispatcher nativo + `--pane`).

**Regra do operator:** todo run de prova é visível — runs do executor só
rodam no herdr (pane visível do supervisor). Run fora do herdr = PROIBIDO.

## Comando único

```bash
/usr/bin/python3 /home/worker/harness-s2/mission_run.py \
  --mission /opt/mission-events/missao-<MISSION-ID>.md \
  --cwd <worktree-ou-repo-alvo> \
  [--budget 2.0] [--max-turns 60] [--seed 0] \
  [--out /tmp/resumo-<MISSION-ID>.json] \
  [--pane]   # sprint 6: tab RUN:<id> no herdr com espelho tail -F da trilha
```

Exit 0 = PASS (stop-conditions cumpridas); exit 1 = FAIL (budget, stalls,
setup do adaptador). Resumo completo em `<run_dir>/run-summary.json` +
trilha em `<run_dir>/harness-trail.jsonl`.

## Modo `--pane` (sprint 6)

`--pane` cria uma tab **`RUN:<mission-id>`** no herdr (`herdr tab create` +
`herdr pane send-text` — puro shell, ZERO CLI Claude no caminho) com um
espelho `tail -F` da trilha da run, roda a run localmente e imprime no fim
a linha final `veredito + custo_usd + trilha`. **herdr indisponível → falha
honesto ANTES de rodar** (exit 1, motivo `pane_indisponivel`); sem pane-id
extraível do `tab create`, segue com aviso (o espelho é visibilidade, a run
nunca é bloqueada por ele). A montagem dos argvs é determinística e
unit-testada (`tests/test_mission_run_pane.py`, com mock — o herdr é
inacessível do sandbox de teste).

## O que acontece (determinístico, ZERO-LLM fora do loop)

1. **Adaptador** (`adaptador.py`): lê o `missao-*.md`; bloco
   ` ```harness-stop``` ` inline vence; sem bloco, deriva `cmd` do primeiro
   comando determinístico em `## Provas` (`/usr/bin/python3 -m pytest ...`);
   sem prova determinística → **FAIL no setup** (não adivinha prova subjetiva).
   `{{HARNESS_CWD}}` nas conds vira o `--cwd` real; budget vem de
   `budget US$ X` nas Regras (default 1.0).
2. **Loop** (`harness.py`): roda a missão com janela compactada, budget,
   stalls, stop-conditions — igual às canárias s2/s3.
3. **Fecho** (`mission_report.py`): emite `mission_completed` /
   `mission_failed` no spool `/opt/mission-events/spool.jsonl`
   (`source: harness-v2`), dedupe por assinatura — a mesma transição nunca
   reemite.

## Pré-requisitos

- Contrato com prova determinística (bloco harness-stop ou pytest em Provas).
- `--cwd` apontando pro worktree/repo da missão (o loop edita lá, confinado).
- Bridge de modelo no ar (`call_bridge`, :8103).

## Sprint 5 (dispatcher nativo)

Substituir o passo manual por: supervisor lê fila → chama
`mission_run.py --mission ... --cwd ...` → consome evento do spool no fecho.
O emissor (item 2) já fala o formato do spool; falta só o lado consumidor.
# RUNBOOK — despachar uma missão mission-ops pelo harness v2 (1 comando)

**Para:** supervisor do mission-ops. Caminho pra sprint 5 (dispatcher nativo).

## Comando único

```bash
/usr/bin/python3 /home/worker/harness-s2/mission_run.py \
  --mission /opt/mission-events/missao-<MISSION-ID>.md \
  --cwd <worktree-ou-repo-alvo> \
  [--budget 2.0] [--max-turns 60] [--seed 0] \
  [--out /tmp/resumo-<MISSION-ID>.json]
```

Exit 0 = PASS (stop-conditions cumpridas); exit 1 = FAIL (budget, stalls,
setup do adaptador). Resumo completo em `<run_dir>/run-summary.json` +
trilha em `<run_dir>/harness-trail.jsonl`.

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
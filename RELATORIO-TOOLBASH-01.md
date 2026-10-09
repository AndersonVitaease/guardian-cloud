# RELATÓRIO TOOLBASH-01 (RD-HARNESS-TOOLBASH-01)

Data: 09/10/2026 (BRT). Branch: `RD-HARNESS-TOOLBASH-01` @ **787ad15b** (worktree `/home/worker/wt-harness-toolbash`, base f6dd9d83).

## Entregue
- **tool_bash nativa** em `harness.py`: catálogo lido DINAMICAMENTE de `/opt/mission-events/tools-bash/tools.json` (já pegou code_find/code_slice/git_peek/queue_peek instalados pelo agente sa-0-c7b6d3d8 em runtime); catálogo ausente/inválido ⇒ tool_bash não registrada, harness segue como hoje.
- Handler em `run_tool`: **sem shell=True** (lista argv), timeout 20s, cwd = dir do catálogo, env mínimo (PATH + MISSION_STATE_DIR, default /root/.hermes/mission-state), saída truncada em 4000 chars, erros tipados (TOOL_NOT_IN_CATALOG, BAD_ARGS, TOOL_TIMEOUT, SCRIPT_EXIT_N, CATALOG_UNAVAILABLE) — fail-open, sem crash. Args: `[A-Za-z0-9._/=-]`, ≤200 chars/arg, sem '-' inicial (desvio documentado: '/' e '=' permitidos para paths de code_find/code_slice; argv sem shell mantém segurança).
- Enum da tool vem do catálogo; `HARNESS_TOOLBASH=0` desliga (braço A / rollback).
- System prompt fatorado em `worker_system_prompt()` (mesma f-string de antes, agora testável) + instrução curta PT-BR: leitura mecânica SEMPRE via tool_bash; Read só trecho exato; Write/Edit/Bash para escrita.
- **Shim Bash→tool_bash**: o glm-flash consistentemente emite a chamada de tool_bash como comando Bash com body JSON `{"tool":...}`; run_tool roteia para o handler em vez de executar JSON no shell. Sem o shim, toda tentativa virava turno perdido (evidência nos trails de runsB/B2).
- TDD: `tests/test_toolbash.py` — 16 testes herméticos (<1s úteis; slow/timeout ~20s), RED→GREEN. Suite existente (test_harness, test_hygiene, test_stream_always, test_adaptador) verde. Fix de flake pré-existente: `run_tempo_ms` com ceil (runs fake <0,5ms davam 0).
- 15 erros de loader no `discover tests` são **pré-existentes** (idênticos no master f6dd9d83 — ambiente, não código).

## A/B real (mesma missão, seed 42, budget $0.05, HARNESS_ADVISOR=0, usuário worker, código da branch)
Missão: custo de RD-TOOLS-BASH-01A + achar anti-fantasma em harness-s2 + answer.md.

| braço | veredito | calls | turnos | tokens in | tokens out | custo.usd | run_ms |
|---|---|---|---|---|---|---|---|
| A (TOOLBASH=0) | **FAIL** (vagueio, 32 Bash caros, zero Write) | 8 | 8 | 29.668 | 878 | 0.004889 | 22.401 |
| B (TOOLBASH=1) | **PASS** (stop-conditions) | 3 | 3 | 6.816 | 241 | **0.001143** | **4.968** |

Economia: **−76,6% custo**, −77% tokens in, −72,5% tempo, e A falhou onde B passou. Trails: /tmp/ab/runsA e /tmp/ab/runsB4 (resumos /tmp/ab/resumoA.json, resumoB4.json). answer.md correto no braço B (custo via mission_cost; anti-fantasma harness.py:778).

## Desvios/bloqueios reportados (sem contorno)
1. `worker` não atravessa `/root/.hermes` (700) — missão original apontava ledger em /root/.hermes/mission-state e código em /root/.hermes/plugins/mission-ops. Ledger copiado para `/tmp/ab-state` (MISSION_STATE_DIR) e alvo de código trocado para /home/worker/harness-s2. Ferramenta continua apontando o default /root/.hermes/mission-state para runs root.
2. O modelo nunca chamou a tool tool_bash diretamente (mesmo com enum+exemplo no prompt) — usa Bash com body JSON; o shim cobre isso e é o que entrega a economia medida.
3. Suite completa `discover tests` leva ~90s (>60s); rodei o subconjunto hermético relevante (verde).

## NÃO feito (ordem do operador)
Merge em master NÃO executado. Backup do harness.py de produção antes de qualquer merge:
```
sudo cp /home/worker/harness-s2/harness.py /home/worker/harness-s2/harness.py.bak-toolbash-$(date +%s)
```
Merge (ordem do operador):
```
cd /home/worker/harness-s2 && git merge --no-ff RD-HARNESS-TOOLBASH-01 -m "TOOLBASH-01: tool_bash nativa (A/B: custo −76.6%, FAIL→PASS)"
```
Rollback (após merge) — código ou runtime:
```
cd /home/worker/harness-s2 && git revert --no-edit 787ad15b ff39fd7b f26fc19c ea41be83
# ou runtime, sem deploy: HARNESS_TOOLBASH=0 no unit do harness
```

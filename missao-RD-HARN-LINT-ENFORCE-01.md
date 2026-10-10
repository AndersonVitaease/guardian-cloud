# MISSÃO RD-HARN-LINT-ENFORCE-01 — contrato_lint bloqueante no despachar_missao.py

**Componente:** harness-s2 · **Prioridade:** 1 · **Fonte:** ROADMAP.md linha 128 (RD-HARN-LINT-ENFORCE-01, prio 1). Operator autorizou 10/10 ~17:5x BRT.

## Contexto / ESTADO ATUAL
- O `despachar_missao.py` VIVO (`/opt/mission-events/scripts/despachar_missao.py`, 194 linhas) tem **0 chamadas ao lint** (verificado). NÃO edite nada em `/opt` — a missão entrega uma CÓPIA corrigida em `scripts/despachar_missao.py` DENTRO deste worktree, e o SUPERVISOR instala em /opt depois (fora do escopo da run).
- O linter já existe e está vivo: `/home/worker/harness-s2/scripts/contrato_lint.py` (com `STOP_RELATIVO`; testes 9 passed). CLI: `python3 scripts/contrato_lint.py <contrato.md>` — exit 0 = verde, exit ≠ 0 = recusa (códigos: SEM_STOP, FENCE_ERRADA, SUDO_NO_STOP, STOP_RELATIVO, SEM_MAPA, ID_DIVERGENTE, STOP_SO_TRIVIAL…).

## Entregas
1. Copie para `scripts/despachar_missao.py` NO worktree o arquivo vivo do despacho (caminho no MAPA; leia-o por code_slice antes de editar) e aplique DUAS mudanças bloqueantes:
   a. **Lint bloqueante no despacho**: logo após ler o contrato (linha ~69), ANTES do `parse_stop_conditions` (~linha 78), rodar `python3 /home/worker/harness-s2/scripts/contrato_lint.py <contrato>` (via `sh()`) e, se exit ≠ 0, `fail("LINT_RECUSADO", id=mid, detalhe=<saída do lint>)`. Constante nova `LINT` perto das constantes de caminho (linhas 15-17). `--dry-run` também passa pelo lint.
   b. **Recusar baseline vazia (vácio)**: onde hoje só sai `avisos.append("VACUO ...")` (linhas 98-102), o caso `all(b is True ...)` vira `fail("VACUO_STOPS_VERDES", id=mid, dica="stop de entrega deve estar VERMELHO na baseline")` — sem flag que contorne (vácio é sempre erro de contrato).
2. **Testes novos** em `tests/test_despachar_missao_lint.py` (pytest): importe o módulo da CÓPIA do worktree (importlib por caminho) e prove comportamento real, não existência: contrato com stop relativo (sem `cd /abs &&`) → `LINT_RECUSADO`; fence aberto/0 stops → recusa; stop trivial só `test -f` → recusa; contrato válido com stop de entrega vermelho passa pelo gate do lint; baseline vazia (todos os stops verdes) → `VACUO_STOPS_VERDES`. Para os casos que não chegam ao baseline, exercite via `--dry-run`/função isolada (nunca suba unit real).
3. `RELATORIO-RD-HARN-LINT-ENFORCE-01.md` na raiz: o que mudou, o diff contra o vivo (2 blocos), e o passo de instalação que fica para o supervisor (backup + posse root + modo preservados).
4. Commit único com o ID no assunto: `RD-HARN-LINT-ENFORCE-01: lint bloqueante no despachar_missao`. `git add` SÓ de scripts/despachar_missao.py, tests/test_despachar_missao_lint.py, RELATORIO.

## MAPA (arquivo:símbolo:LINHA — leituras por code_slice.sh ≤120)
- /opt/mission-events/scripts/despachar_missao.py:15 — HARNESS = caminho do repo
- /opt/mission-events/scripts/despachar_missao.py:17 — LEDGER (modelo de constante de caminho p/ LINT)
- /opt/mission-events/scripts/despachar_missao.py:41 — def fail(code, **kw)
- /opt/mission-events/scripts/despachar_missao.py:48 — def main()
- /opt/mission-events/scripts/despachar_missao.py:69 — leitura do contrato (texto = open…)
- /opt/mission-events/scripts/despachar_missao.py:76-78 — parse_stop_conditions (lint entra ANTES)
- /opt/mission-events/scripts/despachar_missao.py:87-97 — baseline paralela dos stops como worker
- /opt/mission-events/scripts/despachar_missao.py:98-102 — avisos VACUO (vira fail)
- /opt/mission-events/scripts/despachar_missao.py:111-113 — dry-run
- /home/worker/harness-s2/scripts/contrato_lint.py:36 — def lint(texto); :134 — def main() (CLI argv=1 contrato)

## LEITURAS AUTORIZADAS
- `code_slice` no arquivo vivo de /opt (trechos do MAPA), em `scripts/contrato_lint.py` e na própria cópia do worktree.
- `code_find.sh` para símbolos. Leitura recusada 2× → wrapper listada, não improvare variante (`cat`/`head`/`ls`/`grep -A`/`;` recusados).

## Regras
- ESCREVA CEDO: testes e relatório = `Write` inteiro; na cópia existente leia o trecho exato por code_slice IMEDIATAMENTE antes de cada `Edit` (old_string literal).
- pytest como uid da run (worker). NÃO baixe nada da internet. NÃO edite /opt (Permission: o lint do contrato também barra; a instalação é do supervisor).
- Não mude nenhuma OUTRA linha do arquivo vivo além das duas mudanças bloqueantes (diff mínimo — o supervisor compara lado a lado antes de instalar).

```harness-stop
cmd cd /home/worker/wt-RD-HARN-LINT-ENFORCE-01 && python3 -m pytest tests/test_despachar_missao_lint.py -q
cmd cd /home/worker/wt-RD-HARN-LINT-ENFORCE-01 && python3 scripts/contrato_lint.py missao-RD-HARN-LINT-ENFORCE-01.md
cmd cd /home/worker/wt-RD-HARN-LINT-ENFORCE-01 && grep -q -F LINT_RECUSADO scripts/despachar_missao.py
cmd cd /home/worker/wt-RD-HARN-LINT-ENFORCE-01 && grep -q -F VACUO_STOPS_VERDES scripts/despachar_missao.py
cmd cd /home/worker/wt-RD-HARN-LINT-ENFORCE-01 && git log -1 --pretty=%s | grep -q -F RD-HARN-LINT-ENFORCE-01
```

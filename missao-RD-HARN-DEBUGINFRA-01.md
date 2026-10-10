# MISSÃO RD-HARN-DEBUGINFRA-01 — Infra de debug do harness (--modo debug + --memoria trail)

**Componente:** harness-s2 · **Prioridade:** 1 · **Fonte:** ROADMAP.md linha 356 (RD-HARN-DEBUGINFRA-01, prio 1, origem ROADMAP-HARNESS.md:40-49, não duplica RD-HARNESS-LEITURA-01). Operator autorizou 10/10 ~17:5x BRT.

## Contexto / ESTADO ATUAL
- O harness.py ATUAL do repo (branch rd-harn-debuginfra-01, base e19dfab7) tem **0 ocorrências** de `HARNESS_READ_WINDOW`, `--modo` e `--memoria` (verificado). Não copie commit antigo.
- O comportamento da janela de leitura H4 (referência de estilo, NÃO para copiar literal) vive em `/home/worker/wt-H4-VAGUEIO/harness.py:69` (HARNESS_READ_WINDOW), `:80` (`_turno_so_leitura_governada`) e em `apply_H4_janela_leitura.py`.
- Baseline: suíte completa 509 passed na ponta de rd-segue-01. Runner = pytest 7.4.4 (provido como worker).

## Entregas (degrau 1 — esta missão NÃO institucionaliza default; rollback por env)
1. **`--modo debug`** em `harness.py`: `main()` ganha `--modo` com escolhas `normal|debug` (default `normal`). Com `--modo debug` e sem override explícito dos outros flags, os parâmetros de janela sobem: `raw_window` 12→40, `max_summary` 60→120, `max_tool_chars` 4000→12000. Env de rollback `HARNESS_MODO_DEBUG=0` desliga o efeito mesmo com o flag presente (paridade antiga). Isso flui pelos parâmetros EXISTENTES de `run_mission` (raw_window/max_tool_chars/max_summary) e `Window.__init__` — não duplique estado.
2. **`--memoria trail`**: `run_mission` ganha parâmetro `memoria_trail=None` (caminho de um `harness-trail.jsonl` de run anterior). Quando presente, um bloco `DIAGNOSTICO PREVIO` (últimas 15 ações + stops pendentes, no formato que `scripts/diagnostico.py` já produz) entra no kickoff junto do bloco de checkpoint (perto de `bloco_checkpoint`/`contract_prefix`). `main()` ganha `--memoria` que recebe o caminho e valida existência (caminho ausente = erro claro no boot, nunca silêncio). Degrau 2: o caminho `stop_flag` de `run_mission` deve aceitar debug+memoria combinados sem conflito (teste cobre).
3. **6 testes novos** em `tests/test_harness_debuginfra.py` (pytest, bridge mockada — padrão dos testes existentes; teste de run longa passa `vagueio=False`): (a) defaults de debug alargam os 3 parâmetros; (b) `--modo normal` não muda nada; (c) rollback `HARNESS_MODO_DEBUG=0`; (d) `--memoria` injeta `DIAGNOSTICO PREVIO` no kickoff; (e) trail inexistente = erro claro; (f) stop_flag + debug + memoria coexistem.
4. `RELATORIO-RD-HARN-DEBUGINFRA-01.md` na raiz do worktree (pt-BR, o que mudou, como provar, rollback).
5. Commit único com o ID no assunto: `RD-HARN-DEBUGINFRA-01: implementacao modo debug e memoria trail`. `git add` SÓ dos arquivos da missão (harness.py, tests/test_harness_debuginfra.py, RELATORIO).

## MAPA (arquivo:símbolo:LINHA — leitura autorizada via code_slice.sh, ≤120 linhas por leitura)
- harness.py:117 — MAX_TOOL_CHARS = 4000 (constante default)
- harness.py:118 — RAW_WINDOW = 12
- harness.py:123 — MAX_SUMMARY_LINES = 60
- harness.py:717 — class Window.__init__(raw_window, max_summary, max_tool_chars, compact_to)
- harness.py:746 — truncagem do tool_result cru dentro da janela
- harness.py:1040 — bloco_checkpoint() (modelo para o bloco DIAGNOSTICO PREVIO)
- harness.py:1062-1066 — assinatura de run_mission (raw_window/stop_flag/max_tool_chars/max_summary)
- harness.py:1102 — `win = Window(raw_window=raw_window, max_tool_chars=...)` (único ponto de construção da janela)
- harness.py:1432 — main(argv); add_argument --contract/--cwd/--budget/--max-turns/--seed/--model/--raw-window/--out (1434-1442)
- harness.py:1447 — out_path do resumo
- Referência de comportamento (só leitura): /home/worker/wt-H4-VAGUEIO/harness.py:69-108 (HARNESS_READ_WINDOW + _turno_so_leitura_governada)
- Referência de teste: /home/worker/wt-H4-VAGUEIO/tests/test_h4_janela_leitura.py (estilo de mock de janela)

## LEITURAS AUTORIZADAS
- `code_slice.sh` do tools-bash de produção com ini e fim numéricos, no trecho do MAPA de harness.py.
- `code_slice` nos arquivos de referência do wt-H4-VAGUEIO citados acima.
- `code_find.sh` para localizar símbolos. Leitura recusada 2× → use a wrapper listada, NÃO improvare variante (`cat`/`head`/`ls`/`grep -A`/`;` são recusados pelo hook).

## Regras
- ESCREVA CEDO: arquivo novo (testes, relatório) = `Write` inteiro; em harness.py (existente) leia o trecho exato por code_slice IMEDIATAMENTE antes de cada `Edit` e copie o `old_string` literal.
- Python/pytest no worktree sempre como uid da run (worker), nunca root. NÃO baixe nada da internet; se faltar algo, STOP-AND-REPORT.
- Não toque em `/opt` nem em `/home/worker/harness-s2` (repo raiz) — só este worktree.
- Não institucionalize `--modo debug` como default de despacho (isso é passo posterior, decisão do operator).

```harness-stop
cmd cd /home/worker/wt-RD-HARN-DEBUGINFRA-01 && python3 -m pytest tests/test_harness_debuginfra.py -q
cmd cd /home/worker/wt-RD-HARN-DEBUGINFRA-01 && python3 harness.py --help | grep -q -F -- "--modo"
cmd cd /home/worker/wt-RD-HARN-DEBUGINFRA-01 && python3 harness.py --help | grep -q -F -- "--memoria"
cmd cd /home/worker/wt-RD-HARN-DEBUGINFRA-01 && python3 -m py_compile harness.py
cmd cd /home/worker/wt-RD-HARN-DEBUGINFRA-01 && git log -1 --pretty=%s | grep -q -F RD-HARN-DEBUGINFRA-01
```

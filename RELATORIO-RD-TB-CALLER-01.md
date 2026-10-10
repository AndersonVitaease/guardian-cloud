# RELATÓRIO — RD-TB-CALLER-01

## O que foi feito
Workers do harness agora se identificam nas bash tools via `TOOLS_CALLER`, eliminando o `caller=unknown` na trilha de auditoria (`/opt/mission-events/tools-bash-audit/calls.jsonl`).

### Mudanças em `harness.py`
1. **`_CALLER_ID = "harness"`** (variável de módulo, default) + **`_sanitize_caller(value)`**: saneia para `[A-Za-z0-9._:-]` (outros viram `_`) e trunca a 60 chars.
2. **`run_mission`** (após extrair `mission_id` do contrato, ~L1089): se `mission_id` não vazio, `global _CALLER_ID; _CALLER_ID = _sanitize_caller(f"harness:{mission_id}")`.
3. **`_tool_bash`** (env do subprocess, ~L414): acrescentado `"TOOLS_CALLER": _sanitize_caller(_CALLER_ID)`. Como o redirecionamento do Bash (`_bash_redirect`) chama `_tool_bash`, todos os caminhos (tool_bash direto e redirect de grep/git) passam pelo mesmo ponto de montagem do env — sem alterar `_bash_redirect`.

### Testes (`tests/test_tb_caller.py`, 4 testes)
- (a) default `harness` sem missão;
- (b) após id de missão, env contém `TOOLS_CALLER=harness:RD-TB-CALLER-01` (monkeypatch de `subprocess.run`);
- (c) saneamento (espaço/`!`/`/` → `_`, truncamento a 60, acentos → `_`);
- (d) caminho de redirect: `cat` → recusa `FILE_READ` sem subprocess; `grep -rn` → redirect para tool_bash com caller no env.

## Verificação
- `python3 -m py_compile harness.py` OK
- `python3 -m unittest tests.test_tb_caller` → OK (4 testes)
- `python3 -m unittest discover -s tests` → OK (suíte inteira verde)

## Limitações / notas honestas
- O caller é por processo (variável de módulo): runs concorrentes no mesmo processo compartilhariam o valor; no harness cada missão roda em processo próprio, então não há conflito na prática.
- O saneamento é aplicado no env e no setter; o valor default `"harness"` já é válido.
- Não medi a taxa de `caller=unknown` pós-mudança (exige nova coleta de trilha em runs reais); a correção ataca a causa raiz identificada (env sem `TOOLS_CALLER`).

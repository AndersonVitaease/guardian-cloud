# RELATÓRIO — RD-TB-CALLER-01

## Objetivo
Identificar o chamador nas bash tools do harness: a trilha de auditoria
(`/opt/mission-events/tools-bash-audit/calls.jsonl`) tinha 96% das chamadas com
`caller=unknown` porque o `env` do subprocess do `tool_bash` não exportava
`TOOLS_CALLER`.

## O que foi feito (harness.py)
1. Variável de módulo `_CALLER_ID = "harness"` (default) + helper
   `_sanitize_caller()` (só `[A-Za-z0-9._:-]`, demais viram `_`, trunca a 60).
2. Em `run_mission`, logo após extrair `mission_id` do contrato, se não vazio:
   `global _CALLER_ID; _CALLER_ID = _sanitize_caller(f"harness:{mission_id}")`.
3. No `env` do `subprocess.run` da tool_bash, acrescentado
   `"TOOLS_CALLER": _sanitize_caller(_CALLER_ID)`. Como o redirecionamento do
   Bash (`_bash_redirect`) chama o mesmo ponto de execução da tool_bash, todos
   os caminhos (tool_bash direto e redirect) passam a levar o caller.

## Testes (tests/test_tb_caller.py, 4 testes)
- (a) sem run_mission, `TOOLS_CALLER == "harness"`;
- (b) com id de missão, env do subprocess contém `harness:RD-TB-CALLER-01`
  (monkeypatch de `subprocess.run` capturando `env`);
- (c) saneamento: espaços/barras/exclamação → `_`, truncamento a 60, acentos → `_`;
- (d) caminho de redirect: `cat arquivo` → recusa FILE_READ sem subprocess;
  `grep -rn x dir` → redireciona e o env carrega o caller.

## Verificação
- `python3 -m py_compile harness.py` OK.
- `python3 -m unittest tests.test_tb_caller` → OK (4 testes).
- `python3 -m unittest discover -s tests` → OK (suíte inteira verde).

## Limitações / honestidade
- O caller é uma variável de módulo global: runs concorrentes no mesmo
  processo compartilhariam o valor (o harness executa 1 run por processo, então
  na prática não há corrida).
- O valor é saneado no ponto de uso e no ponto de atribuição; missões com ids
  exóticos ficam com `_` no lugar dos caracteres inválidos.
- Não foi alterado `_bash_redirect`, escada, vagueio, janela nem força-escrita.

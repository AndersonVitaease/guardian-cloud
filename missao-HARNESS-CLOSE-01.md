# MISSÃO HARNESS-CLOSE-01 — FASE-FECHO determinística no harness (bloco ```harness-close```)

Fonte: ROADMAP.md linha 370.

Desenho já decidido pelo supervisor — implemente POR CONTRATO, não redesenhe. Repo: /home/worker/harness-s2 (você está no worktree /home/worker/wt-HARNESS-CLOSE-01).

## O QUE FAZER

Implementar fase de fecho no `harness.py`:

(a) Novo bloco de contrato ``` ```harness-close ``` ``` parseado como o ``` ```harness-stop ``` ``` existente: mesmo parser, só linhas `cmd <shell>` / `file <path>` / `marker <TEXTO> <path>` dentro de fence fechado. Nova função de parse (ex.: `parse_close_conditions`) ou flag no `parse_stop_conditions` existente.

(b) Se a missão DECLARA o bloco `harness-close`:
  - O veredito PASS/fecho natural SÓ sai quando TODOS os cmds do bloco close dão exit 0.
  - Se o modelo sinaliza fim (stop-conditions do harness-stop verdes) e o close está vermelho: o harness NÃO encerra — injeta 1 prompt de fecho com texto fixo curto:
    `FASE DE FECHO: rode os stops de fecho pendentes, commit os arquivos da missão com o ID no assunto, rode a suíte, mostre git log -1`
    e continua. MÁXIMO 3 ciclos; contador registrado no trail como evento `_close_reprompt` (campo `turno`/`ciclo`).
  - 3º ciclo ainda vermelho = FAIL honesto com motivo `fecho_incompleto` e o estado git no resumo (saída de `git status --porcelain` + `git log -1 --oneline` no campo recomendacao ou equivalente do summary).

(c) Se a missão NÃO declara o bloco: comportamento atual inalterado (todos os testes existentes continuam verdes).

(d) Rollback: constante de módulo `HARNESS_CLOSE` lida no import exatamente como a `HARNESS_ADVISOR` (linha 44: `HARNESS_CLOSE = os.environ.get("HARNESS_CLOSE", "1") != "0"`); `HARNESS_CLOSE=0` desliga a fase de fecho inteira (paridade do comportamento anterior).

## MAPA PRÉ-DIGERIDO (arquivo:LINHA no HEAD atual de /home/worker/harness-s2/harness.py, commit 534c1a84)

- `harness.py:44` — `HARNESS_ADVISOR = os.environ.get("HARNESS_ADVISOR", "1") != "0"` (leitura no import; espelie para `HARNESS_CLOSE` logo abaixo).
- `harness.py:547` — `def parse_stop_conditions(contract_text):` — docstring e parser do bloco; regex do fence em `harness.py:564` (`re.search(r"```harness-stop\n(.*?)```", ...)`) e ramos `file`/`cmd`/`cmdout` em 566–580. Baseie `parse_close_conditions` aqui (fence ```harness-close```, mesmos ramos; pode fatorar um helper comum).
- `harness.py:1328` — `done, new = tick(turn, "check")` — stop-check a cada turno (emit `_stop_check` logo abaixo); é aqui que o estado das stops é recalculado por turno. O tick do close deve ser avaliado no mesmo ponto (ou imediatamente após).
- `harness.py:1332` — `verdict, reason = "PASS", "stop_condition"` — onde o veredito de fecho natural é decidido. Este `break` é o ponto exato da regra (b): se há bloco close e ele não está 100% verde, NÃO saia com PASS aqui — injete o reprompt (evento `_close_reprompt`, máx 3 ciclos; no 3º, `verdict, reason = "FAIL", "fecho_incompleto"` + estado git no summary).
- `harness.py:1453` — montagem do `summary` dict (adicione campos do fecho: ex. `close_ciclos`, `close_state`).
- Tests: crie `tests/test_harness_close.py` (unittest, só stdlib, fakes de bridge — espelie os fakes dos tests existentes de advisor/stop; lembre: patchear o ATRIBUTO `harness.HARNESS_CLOSE` / `harness.HARNESS_ADVISOR`, NUNCA a env; testes que exercitam o loop longo de run usam `vagueio=False`).

Regra de edição: `old_string` de UMA linha distinta; arquivo novo (`tests/test_harness_close.py`) = Write inteiro. Commit cedo com o ID no assunto.

## PROVA DE FECHO (stop-conditions)

```harness-stop
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && git log -1 --format=%s | grep -q -F HARNESS-CLOSE-01
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && /usr/bin/python3 -m py_compile harness.py
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && /usr/bin/python3 -m pytest tests/test_harness_close.py -q
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && /usr/bin/python3 -m pytest tests/ -q
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && git ls-files --error-unmatch tests/test_harness_close.py && git diff --quiet HEAD -- harness.py
```

Sem sudo. Baseline verificado hoje (10/10/2026): suíte completa verde (518 passed, 2 skipped) — stop 4 mantida integral.

operatorOrder: FASE-FECHO autorizado pelo operador 10/10.

Escreva o relatório em RELATORIO-HARNESS-CLOSE-01.md e PARE.

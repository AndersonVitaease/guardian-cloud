# MISSÃO VAGUEIO-PROMPT-01 — harness: nudge AGIR-OU-PARAR com prazo de entregável

Fonte: ROADMAP.md linha 379.

operatorOrder: reforço do nudge autorizado pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Caso medido (10/10, RD-H1H2-REPORT-01 tentativa 3): 24 comandos bash, ZERO write/edit, só exploração até estourar max_turns — o nudge AGIR-OU-PARAR existente não segurou. Custos: 12 turnos desperdiçados na tentativa, e a missão inteira girou 3x.
- HARNESS-CLOSE-01B e STOP-STALE-01 editam harness.py EM PARALELO — re-ler HEAD do worktree antes de editar; achar o nudge pelo texto, não por linha.
- Vagueio: registro `_vagueio` no trail; detector marca turnos sem entregável; após N marcações → FAIL antecipado (medido: "11x sem entregável | FAIL antecipado").

## OBJETIVO
1. Localizar o texto do nudge AGIR-OU-PARAR no harness.py e a janela de detecção de vagueio.
2. Reforçar o nudge com prazo explícito: ao primeiro registro de vagueio, o prompt injetado passa a dizer "produza 1 entregável commitado nos próximos 5 turnos ou a run é encerrada com FAIL vagueio"; ao 2º registro, prazo cai para 3 turnos. Contadores e textos no módulo (constantes nomeadas), comportamento inalterado quando VAGUEIO_PROMPT=0 (lida no import, constante de módulo, patcheada por atributo nos testes).
3. O detector NUNCA dispara FAIL antes do prazo prometido (o FAIL antecipado existente passa a respeitar o prazo declarado no nudge — mesmo contador).

## TAREFA
1. Editar harness.py + tests/test_vagueio_prompt.py (unittest stdlib, fakes de bridge, patchear atributo): (a) 1º vagueio → nudge contém "5 turnos"; (b) 2º → "3 turnos"; (c) FAIL antecipado só após o prazo; (d) VAGUEIO_PROMPT=0 → texto antigo intacto.
2. Suíte completa verde (baseline provado: 529 passed, 2 skipped).
3. Commit `VAGUEIO-PROMPT-01: nudge com prazo de entregavel` e `VAGUEIO-PROMPT-01: relatorio` (RELATORIO-VAGUEIO-PROMPT-01.md, 2 linhas).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01 && git log -1 --format=%s | grep -q -F "VAGUEIO-PROMPT-01: nudge"
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01 && /usr/bin/python3 -m py_compile harness.py
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01 && /usr/bin/python3 -m pytest tests/test_vagueio_prompt.py -q
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01 && /usr/bin/python3 -m pytest tests/ -q
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01 && git ls-files --error-unmatch tests/test_vagueio_prompt.py && git -C /home/worker/wt-VAGUEIO-PROMPT-01 diff --quiet HEAD -- harness.py
```

PROIBIDO: git reset/checkout/stash/clean; tocar routing/bridge; mudar modelo de worker; mexer no detector de vagueio além do prazo/contador.

# MISSÃO VAGUEIO-PROMPT-01B — gatilho de vagueio consciente de progresso real (régua de eventos novos)

Fonte: ROADMAP.md linha 395.

operatorOrder: régua de progresso autorizada pelo operador 10/10 ("entendi e descobrindo o que é podemos atacar").

## MAPA PRÉ-DIGERIDO
- Desenho decidido pelo supervisor (worker implementa por contrato, não redesenha).
- Contexto medido hoje (3 FAILs de vagueio com WIP bom: HARNESS-CLOSE-01B 2×, SEC-ESCAPE-01 tent.1): gatilho fixo `HARNESS_VAGUEIO_TRIGGER`=8 turnos sem Write/Edit derruba missões legítimas de varredura (grep/code_slice/código novo lido) que exploram 10-20 turnos antes de escrever.
- Arquivo-alvo: `harness.py` no tick do `_vagueio` (evento `_vagueio` + FAIL `vagueio` antecipado com `recomendacao` no resumo/CHECKPOINT.json) — achar símbolo:LINHA com code_find no HEAD.

## NOVA RÉGUA (objetivo)
Contar turnos desde o último EVENTO NOVO; evento novo = qualquer um:
1. Write/Edit (como hoje);
2. leitura de arquivo AINDA NÃO lido nesta run (mapa de arquivos já tocados por caminho);
3. stop-condition parcial que ficou verde num turno novo (`todas` com novo true);
4. arquivo novo criado fora do checkout (ex.: /tmp) detectável pela trilha do turno.
Contador 8 (override por contrato, campo `vagueio_trigger:`) sem NENHUM evento novo → FAIL `vagueio` como hoje (evento `_vagueio`, `recomendacao` intacta). Loop real (mesmo comando repetido, custo estável, nada novo) CONTINUA morrendo.

## TESTES DISCRIMINADORES (tests/test_vagueio_regua.py, unittest stdlib)
- A: missão-exploradora (reads novos por 12 turnos, depois 1 Write) → SEM FAIL, PASS.
- B: loop real (mesmo comando x9) → FAIL `vagueio` no turno do gatilho.
- C: override por contrato (`vagueio_trigger: 4`) → FAIL no 4º sem eventos.
- D: mapa de reads não cresce infinito (respeita janela/memória — N caminhos, não append ilimitado).
- E: recomendação/resumo no FAIL mantém formato atual (parse do harness não muda).
Fakes de bridge como nas outras sprints (patchear atributo do módulo, nunca env; run longa com vagueio=False nos testes).

## TAREFA
1. Implementar a régua no tick do vagueio (mapa de reads + eventos 2-4).
2. Campo `vagueio_trigger:` no parse do contrato (default = HARNESS_VAGUEIO_TRIGGER atual).
3. Commit `VAGUEIO-PROMPT-01B: regua de progresso real no gatilho de vagueio` + RELATORIO-VAGUEIO-PROMPT-01B.md (2 linhas: o que mudou + provas A-E).

```harness-stop
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01B && git log -1 --format=%s | grep -q -F "VAGUEIO-PROMPT-01B: regua de progresso real"
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01B && /usr/bin/python3 -m py_compile harness.py
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01B && /usr/bin/python3 -m pytest tests/ -q
cmd cd /home/worker/wt-VAGUEIO-PROMPT-01B && git ls-files --error-unmatch RELATORIO-VAGUEIO-PROMPT-01B.md && git -C /home/worker/wt-VAGUEIO-PROMPT-01B diff --quiet HEAD -- harness.py
```

## ACEITE
- Provas A-E citadas no relatório; suíte completa verde; sem vagueio=False escondendo o comportamento real; sem sudo; entrega commitada (nada untracked).

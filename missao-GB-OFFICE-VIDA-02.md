# MISSAO GB-OFFICE-VIDA-02

Fonte: ROADMAP.md linha 475 (continuacao direta da GB-OFFICE-VIDA-01 — o aceite real NAO passou: a office continua status idle/activity vazio mesmo com a ponte injetando tool_start).

Diagnostico cravado (provas E2E do supervisor hoje, contra a office REAL em producao :8113):
- A ponte nova injeta session_start (o agente NASCE na sala — funciona) e tool_start com call_id ponte-<mid>, tool_name e preview (6 eventos no 1o teste, 5 no 2o).
- O state_model.py TEM handler para tool_start (linha ~253): ensure + active_tools + settle => status "working" + tool preenchido.
- MAS o GET /state depois mostra status "idle", tool vazio, activity vazio — o evento tool_start ou nao chega ao apply, ou chega e algo depois (ex.: session_idle emitido em sequencia pela propria ponte, ou regra de inatividade) volta pra idle, ou a ordem/origem dos eventos no apply nao e a esperada.
- Outro sintoma: a cada --once saem 5-6 eventos para UMA linha nova de UM espelho — sequencia suspeita (ex.: tool_start + session_idle logo em seguida).
- Sessoes pousadas: o re-encerramento funcionou para GB-CHAT-SUMI-01 mas os fantasmas antigos (GB-STREAM-CRU-01, GB-SESSAO-GUARD-01) continuam no piso com status idle.

Entrega (repo agent-office — arquivos: ponte_office.py e/ou prova; NAO altere state_model.py/run.py/event_* — se o bug estiver neles, DOCUMENTE no relatorio com arquivo:linha e o patch fica pro supervisor):
1. PROVA E2E DE VERDADE (prova-GB-OFFICE-VIDA-02.sh): suba uma office REAL de teste em porta efemera (python3 run.py --port <efemera> com HERMES_HOME tempdir — o run.py e stdlib-only e nao precisa runtime), rode a ponte nova apontada pra ela (AGENT_OFFICE_PORT=<efemera> ponte_office.py --once) com espelho fake + sessao.log com 3 linhas de tipos diferentes, e ASSERTIONE no GET /state dessa office de teste: agente presente com status working/typing (NUNCA idle logo apos tool_start), tool preenchido, activity/preview visivel. Depois: rename do espelho para pousado => --once de novo => agente SAI do /state (status gone/ausente). Essa prova e o novo padrao de aceite da ponte — nada de contar evento na inbox.
2. Corrija o que a prova E2E acusar (na ponte: sequencia/espaco entre tool_start e session_idle; o idle so deve sair se NAO houve linha nova na janela de pausa — nunca no mesmo ciclo de uma atividade nova; ghost: session_end para os pousados antigos idempotente).
3. Garanta: sem atividade nova na janela => session_idle (comportamento desejado); COM atividade nova => working/typing e NADA sobrescreve no mesmo ciclo.
4. Nao quebre: session_start, re-encerramento PISO-03, traducao PT-BR, fail-open.

MAPA:
- ponte_office.py:308-350 (inject calls: session_start/tool_start/session_idle/session_end — a sequencia por ciclo e o suspeito)
- state_model.py:253-262 (tool_start => settle => working — SO LEITURA, nao altere)
- state_model.py:19-27 (_agent_key)
- run.py:1-40 (como subir a office de teste em porta efemera)

Stops (4):
```harness-stop
cmd cd /home/worker/wt-GB-OFFICE-VIDA-02 && python3 -m py_compile ponte_office.py
cmd cd /home/worker/wt-GB-OFFICE-VIDA-02 && bash prova-GB-OFFICE-VIDA-02.sh
cmd cd /home/worker/wt-GB-OFFICE-VIDA-02 && test -f RELATORIO-GB-OFFICE-VIDA-02.md
cmd cd /home/worker/wt-GB-OFFICE-VIDA-02 && test "$(git log -1 --format=%s)" = "GB-OFFICE-VIDA-02: prova E2E contra office real — working/typing no /state e pousado sai"
```

Restricoes: SO ponte_office.py + prova + relatorio neste worktree. Prova sobe office em PORTA EFEMERA com HERMES_HOME em tempdir (nunca a 8113 de producao). Proibido: git reset, checkout, stash, clean, push — nunca.

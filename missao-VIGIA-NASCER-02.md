# MISSÃO VIGIA-NASCER-02 — ordens via Guardian (rota /api/ordens + guard consultando o app)

CONTINUAÇÃO de VIGIA-NASCER-01 (PASS, merge pousado) + decisão do operador (opção 2, 11/10 ~15:50 BRT): as ordens do operador passam a ser servidas e editadas pelo Guardian app. Worktree real: `/home/worker/wt-VIGIA-NASCER-01` (branch `rd-vigia-nascer-01`, base com merges de UI-LIMPA e afins já pousados).

## Problema
- O guard (`ordens_guard.sh`, /opt/mission-events/tools-bash, root) hoje é estático: as regras vivem no próprio script.
- O operador quer: edita as ordens no Guardian app → guard se atualiza sozinho. Fonte = o app, não o arquivo local.

## Entregas
1. **Rota no server.js do guardian-app**: `GET /api/ordens` — serve o markdown das ordens (novo arquivo `ORDENS-OPERADOR.md` na raiz do repo, com os blocos `## ORD-XXX` por regra). Auth: exige token válido (padrão do F1; visitante sem token → 401). `PUT /api/admin/ordens` (role admin) para editar — mesma proteção de role do painel admin existente.
2. **Painel**: no admin existente, seção "Ordens do Operador" — textarea com o markdown + botão salvar (PUT acima). UI mínima, PT-BR.
3. **Seed**: `ORDENS-OPERADOR.md` com as 10 regras consolidadas (a lista exata está em `ordens-seed.md` do worktree ORDENS-GOVERNANCA-01 — copie de lá, ou reconstrua: delegar-não-executar, não travar terminal, tools governadas, veredito honesto, ship via tool, PT-BR/BRT, avisos nasce/morre, redespacho, voo solo worker, disco>ledger). Formato: um `## ORD-XXX` por regra, cada bloco com `regra:` e `guard:` (o comportamento que o guard aplica).
4. **Guard integrado**: nova versão do `ordens_guard.sh` (script `ordens_guard_v2.sh` no mesmo repo) que, em cada pre_tool_call: lê cache local `/tmp/ordens-cache.md` (TTL 60s); se vencido, GET na rota (`GUARDIAN_ORDENS_URL` + `GUARDIAN_ORDENS_TOKEN` via env — o supervisor injeta o token na aplicação, worker só usa env); aplica as regras que têm `guard:` no bloco. **Fail-open para leitura de ordens** (se o app estiver offline, usa o último cache e, sem cache, permite a chamada EXCETO as regras duras hardcoded que ficam sempre: delegate/sleep-long/git-destrutivo/serviços-vitais — nunca fail-open para elas).
5. **Testes**: pytest para a rota (401 sem token, 200 com, PUT admin ok/403 não-admin) + prova E2E hermética (server em tempdir com GUARDIAN_DB_DIR próprio, mktemp; guarda v2 consultando o server local de teste; marcador `VIGIA-NASCER-02-PROVA-OK` no .out >200 bytes).

## Regras
- Worktree `wt-VIGIA-NASCER-01`, branch `rd-vigia-nascer-01`. Commits atômicos com prefixo `VIGIA-NASCER-02:`.
- Proibido: mexer em routing/bridge, `git reset/checkout/stash/clean`, editar o design-fonte de /opt/operator-harness.
- Sem sudo (você já é worker). Sem cat/head/ls/grep -r; leitura por code_slice/grep -n.
- Não baixe nada da internet.

## Stops
```harness-stop
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 -m pytest tests/ -q
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 scripts/prova-VIGIA-NASCER-02.py
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test $(stat -c%s scripts/prova-VIGIA-NASCER-02.out 2>/dev/null || echo 0) -gt 200
cmd cd /home/worker/wt-VIGIA-NASCER-01 && git log --format=%s -1 | grep -q -F 'VIGIA-NASCER-02'
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test -z "$(git status -s -- .)"
```

## Notas
- O token do operador para o guard consumir em produção: o SUPERVISOR injeta via EnvironmentFile/secret — no contrato use só a variável `GUARDIAN_ORDENS_TOKEN` (não hardcode valor).
- A rota `/api/ordens` é nova: sem ela, o guard v2 no modo degradação usa cache e regras duras — o app nunca fica refém do guard nem vice-versa.

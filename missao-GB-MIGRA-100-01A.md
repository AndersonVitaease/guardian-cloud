# MISSÃO GB-MIGRA-100-01A

Fonte: ROADMAP.md linha 461 (DECISÃO 12/10 FIXA). Operator 12/10 15:38: "sim" (autorizado despachar a migração).

## Objetivo
Fases (a) e (b) da MIGRAÇÃO 100% AO GUARDIAN — fases (c) herdr espelho-only e (d) desligar despacho manual ficam PREPARADAS mas NÃO ATIVAS nesta fatia (mudança de comportamento do operator exige ordem própria).

## Entregas

- ### (a) Notifica com título em TODOS os pousos
vigia_chat.sh (tools-bash + harness-s2/scripts, as 2 cópias) e notify_hermes.sh: TODO aviso de pouso (PASS/FAIL) inclui o TÍTULO da missão — ler o título do contrato (linha "# MISSÃO <ID>" ou campo titulo do ledger/resumo) e incluir no texto: "✅ <TITULO> (<ID>) — veredito PASS · custo US$x · N turnos". Se título indisponível, usa o ID (honesto, não falha).
Ordem dos eventos não muda; só o CONTEÚDO do aviso ganha título. Payload do gateway intocado.

- ### (b) briefing mission_list soma sessões de agente
A fonte de missões do briefing (mission_list do plugin mission-ops / fontes: mission-state + spool + espelho) passa a incluir SESSÕES DE AGENTE (agentes de agente/espelho.json em /tmp/ag-live etc.), não só mission-records — o print de hoje mostrava "ignorados (não são mission-records)" — esses passam a aparecer como "agentes de agente" no briefing, contados, com seu estado (em voo/pousado).
Formato do briefing mantido (uma linha por missão/agente); nada quebra o FAST-ROUTER.
Se o briefing é gerado por plugin eng-mcp (mission_list), o parche é no arquivo do plugin correspondente (procurar por "não são mission-records" no código do plugin, caminho informado pelo supervisor na aplicação).

### (c)+(d) PREPARAÇÃO (sem ativar)
- Criar docs/MIGRA-100.md no cwd com: procedimento exato das fases c (herdr espelho-only) e d (desligar despacho manual antigo), com o feature-flag proposto (ex. MIGRA_100=off|on) e o plano de rollback. NADA é ativado.

## Regras
- Proibido alterar: gateways de aviso (8642), toast/UI do Guardian, guard, despachar_missao.py (a trava de espelho nativa é recente — não regredir).
- As 2 cópias de vigia_chat.sh (harness-s2/scripts e tools-bash) devem ficar IDÊNTICAS após o parche (sha256 iguais — a stop valida).

## MAPA
- tools-bash/vigia_chat.sh: bloco de entrega (emit/D ELIVERED ~linha 330-355)
- harness-s2/scripts/vigia_chat.sh: mesma cópia
- harness-s2/scripts/notify_hermes.sh: texto do aviso
- tools-bash/mission_list.sh (ou plugin correspondente): briefing "ignorados (não são mission-records)"

## Stops (prova)
```harness-stop
cmd cd /home/worker/wt-GB-MIGRA-100-01A && grep -q -e "titulo" vigia_chat.sh
cmd cd /home/worker/wt-GB-MIGRA-100-01A && grep -q -e "titulo" notify_hermes.sh
cmd cd /home/worker/wt-GB-MIGRA-100-01A && test -f docs/MIGRA-100.md && grep -q -e "MIGRA_100" docs/MIGRA-100.md
cmd cd /home/worker/wt-GB-MIGRA-100-01A && python3 prova_migra_a.py 2>&1 | grep -q -e "MIGRA-A-OK"
cmd cd /home/worker/wt-GB-MIGRA-100-01A && test "$(git log -1 --format=%s)" = "GB-MIGRA-100-01A: fases a+b da migracao (titulo em todos os pousos + briefing soma sessoes de agente)"
```

## Anti-vagueio
Proibido git reset/checkout/stash/clean. Proibido reiniciar serviços. prova_migra_a.py: fixture de resumo/contrato fake → gera o texto de aviso → asserta título presente; e parser do briefing com um agente de agente fake → asserta contagem. Tudo offline, sem rede.

## Aplicação (supervisor, autorizado pelo "sim" 15:38)
Copiar vigia_chat.sh/notify_hermes.sh para as 2 cópias + sha256; aplicar parche do briefing no plugin; restart de nada (avisos são por-invocação).
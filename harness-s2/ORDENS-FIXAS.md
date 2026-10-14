# ORDENS-FIXAS DO OPERADOR — leitura obrigatória antes de despachar/fechar/mexer

Última atualização: 13/10/2026 (BRT). Fonte: ordens explícitas do operador no chat.
Se este arquivo e o chat divergirem, VALE O CHAT (ordem mais recente do operador).

## Regra-mestra
1. **1 ordem = 1 mudança.** Nada nasce, nada é corrigido, nada é redespachado sem ordem
   EXPLÍCITA do operador para AQUELA mudança exata (ORD-011). Diagnóstico/leitura: livre.
2. **Despacho limpo ou nada.** Antes de qualquer redespacho: ledger órfão arquivada,
   espelho .pousado removido, unit anterior inativa verificada — TUDO antes de chamar
   despachar_missao. Jamais `rm`/`mv` manual NO MEIO de um despacho falho.
3. **Missão sem aba no herdr = violação de ordem (10/10, RD-DESP-TAB-SILENT-01).**
   Unit ativa sem pane = parar a unit e falhar tipado. Proibido deixar run headless.
4. **Prova em PRIMEIRO plano.** Nunca nohup/&/background dentro de run do harness
   (lição GB-THUMB-03 tentativa 2: run morreu sem veredito).
5. **TERMINAL = SÓ DESPACHO** (hook ordens_guard): leitura/auditoria/teste = agente
   nosso via pipeline; contorno manual = finding.
6. **CHAT NUNCA TRAVA (13/10):** operação em sessão TUI com turnos rápidos; conversa
   do operador em Novo chat; trabalho longo = missão, nunca turno do chat. Chat nunca
   mudo >40s: relatar status a cada ciclo.
7. **Prompt e relatórios SEMPRE em PT-BR; horários SEMPRE em BRT (UTC-3).**
8. **Fecho/SHIP sempre via missao_fechar.sh; worker nunca git reset/checkout/stash.**
9. **Paralelo: 1 missão por repo/área.** Nunca duas missões no mesmo repo em voo.
10. **Delegação só pelos nossos** (pipeline mission-ops / perfis VPS). Nunca CLI externo
    (Claude Code etc.) como mão de obra.
11. **Avisos ao operador:** nascimento e morte de missão chegam no CHAT ATIVO do
    operador (via gateway 8642, mecanismo vigia_chat/despachar — NÃO event_bus).
    Falha de entrega = retry tipado, nunca silêncio.
12. **Liveness honesta:** parado = parado; veredito do worker vale, entrega do
    supervisor é nota, não veredito.

13. (SUBSTITUÍDO 13/10) [ ] Rota correta de despacho de missão: SEMPRE despachar_missao.py <contrato> <worktree> --seed N --budget B [--executar] (spawn nativo: unit + aba RUN:<ID>#s<seed> no herdr + espelho /tmp/ag-live + marcador .espelho-nativo + avisos de nascimento/morte no chat do operador). PROIBIDO despachar pelo plugin mission-ops handle_mission_dispatch ou por spawn de claude no pane — o plugin deve delegar ao despachar_missao.py via subprocess com --executar.
13-A. ROTA ÚNICA DE DESPACHO (operador 13/10, vigente): toda missão é despachada pelo supervisor via agente MECANICO — `bash scripts/despachar-mecanico.sh <worktree> "<missão>" MEC_PROVA=<cura>` — Guardian harness: nasce com aba RUN no herdr, espelho na sala, spool/ledger e avisos 🛰️ nascimento / 🏁 veredito. PROIBIDO: despachar_missao.py (--executar), consumer mission-ops, spawn de claude/pane. Supervisor prepara a cura (patch por âncora + prova) antes de despachar.

14. SECRETÁRIA (13/10): agente bash puro ($0 LLM), hierarquia ACIMA de contratador/despachante/mecanico — SÓ o supervisor delega. Ações: responder/consultar/despachar (3 rotas: despachante DAG, contratador, despacho rápido). Responde DIRETO no chat (💬 SECRETÁRIA), aviso 🛰️/🏁 dispensado para o que ela mesma despacha. Fronteira: NUNCA código, NUNCA missão pesada. Guia: docs/SECRETARIA-GUIA.md.

15. ROTEAMENTO DE PERGUNTAS (13/10): pergunta do operador sobre ESTADO/DADO/VERIFICAÇÃO (missões, fila, herdr, custos, modelos, latência, configs) → supervisor DELEGA à SECRETÁRIA (responder/consultar) e fica livre; julgamento, decisão e prestação de contas do supervisor → resposta direta do supervisor.

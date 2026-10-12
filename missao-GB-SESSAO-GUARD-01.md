# MISSAO GB-SESSAO-GUARD-01

Fonte: ROADMAP.md linha 468 (item SESSAO-GUARD-01, ordem operator 12/10: chat "travou" com "Stopped waiting for another Hermes process on this session" — par TUI/gateway orfao segurando lock de sessao; supervisor aplicou cura manual hoje, esta missao torna a cura automatica).

Diagnostico pronto (nao investigue de novo):
- Cada janela TUI do Hermes spawna um PAR: node (ui-tui/dist/entry.js) + python3 (tui_gateway.entry). Varios pares = normal; orfao = problema.
- O orfao segurou lock de sessao e o chat do dashboard exibiu "Stopped waiting for another Hermes process on this session" sem processar a mensagem.
- Ownership provado por arvore: os comandos do chat ao vivo aparecem como filhos do python do par correto (pstree). Par sem filhos vivos do chat + session antiga no HERMES_SESSION_ID = orfao.
- Logs: ~/.hermes/logs/agent.log (em producao o supervisor le; no worker, o caminho vem por env).

Entrega (harness-s2, arquivo UNICO novo: scripts/sessao_guard.sh + prova):
1. scripts/sessao_guard.sh — daemon/sweep 1-shot: inventaria pares TUI+gateway (ps aux | grep ui-tui/dist + tui_gateway), agrupa node+python do mesmo par (mesmo PPID/parent tree), e para cada par decide:
   - se o python do par tem filhos vivos de chat (bash/python com Hermes snap scratch recente em cmdline) => PAR VIVO, nunca matar;
   - se nao tem filhos e HERMES_SESSION_ID dele e de outro par colide OU a sessao dele nao recebe "tui prompt accepted" ha > N minutos (env GUARD_STALE_MIN, default 120) => ORFAO: kill (SIGTERM, escalar kill -9 apos 5s se sobreviver em estado R), registrar linha em log env GUARD_LOG (default stdout) com pids e causa tipada (ORFAO_SEM_FILHOS / LOCK_COLIDINDO).
   - Fail-open: qualquer erro de leitura = pular par, nunca matar por duvida. Nunca matar pelo criterio de tempo de inicio sozinho.
2. Modo prova injetavel: os dados de ps vem de GUARD_PS_CMD (default "ps aux"; a prova injeta um ps fake) e o pstree de GUARD_PSTREE_CMD — assim a prova e hermetica sem /proc real.
3. Prova hermetica (prova-GB-SESSAO-GUARD-01.sh, tempdir, sem rede): cenario (a) par vivo com filho fake => NAO mata; (b) par orfao sem filhos com lock colidindo => mata e loga ORFAO_SEM_FILHOS; (c) par R sobrevivente a SIGTERM fake => kill -9; (d) erro de leitura => fail-open. RESUMO: 0 falhas no fim.

MAPA:
- scripts/espelho-segue.sh:1-20 (padrao de script bash do repo, header e fail-open)
- scripts/herdr_limpar.sh:1-30 (padrao de tool com JSON de saida + dry-run)
- Conhecimento do supervisor (dados): nomes de processo reais = "ui-tui/dist/entry.js" e "-m tui_gateway.entry" (ou similar); HERMES_SESSION_ID no environ.

Stops (4):
```harness-stop
cmd cd /home/worker/wt-GB-SESSAO-GUARD-01 && bash -n scripts/sessao_guard.sh
cmd cd /home/worker/wt-GB-SESSAO-GUARD-01 && bash scripts/prova-GB-SESSAO-GUARD-01.sh
cmd cd /home/worker/wt-GB-SESSAO-GUARD-01 && test -f RELATORIO-GB-SESSAO-GUARD-01.md
cmd cd /home/worker/wt-GB-SESSAO-GUARD-01 && test -z "$(git status --porcelain scripts/)" && test "$(git log -1 --format=%s)" = "GB-SESSAO-GUARD-01: guarda mata par TUI/gateway orfao com lock colidindo"
```

Restricoes: SO scripts/ novo neste worktree. Nao toque em server.js, app.js, espelho, /opt, /root. Proibido: git reset, checkout, stash, clean, push — nunca.

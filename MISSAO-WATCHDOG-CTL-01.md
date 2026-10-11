# MISSÃO WATCHDOG-CTL-01 — watchdog.d genérico (sweep + governança + timer systemd)

Fonte: ROADMAP (proposta do operador 10/10 noite, autorizada: "sim"). operatorOrder: WATCHDOG-CTL-01 autorizada pelo operador 10/10 noite ("despache as missões"). Reutilizável para QUALQUER projeto (drop-in).

## CONTEXTO
- Padrão provado hoje: tab_reap --apply silencioso (herdr), vigia por missão. O cron do Hermes é local à sessão; timer systemd é infra da VPS (persiste reboot — mesmo argumento do iptables-restore-boot).
- Diretório alvo: o diretório watchdog.d da instalação (resolvido por env WATCHDOG_D_DIR em runtime; o patch do timer cria o diretório no fecho do supervisor) (numérico-<nome>.sh). Execução é sempre do supervisor/root no fecho.

## MAPA
- scripts/watchdog_sweep.sh — ARQUIVO NOVO (bash puro).
- scripts/watchdog_ctl.sh — ARQUIVO NOVO (bash puro, tb_audit inline).
- watchdog.d/10-tab-reap.sh — ARQUIVO NOVO (wrapper de 3 linhas).
- patches/08-watchdog-timer.sh — ARQUIVO NOVO (dry-run default).
- tests/test_watchdog.py — ARQUIVO NOVO (pytest, fakes em tmpdir).
- Referência de padrão: tools do catálogo (JSON 1 linha, falha tipada, exit 0).

## TAREFA (tudo no worktree, worker não escreve /opt nem /etc)
1. scripts/watchdog_sweep.sh: executa cada script executável habilitado em WATCHDOG_D_DIR (env, default o diretório watchdog.d da instalação (env WATCHDOG_D_DIR)), em ordem alfabética, com timeout por script (env WATCHDOG_TIMEOUT=120s); silencioso quando nada reporta; captura stdout de cada um em /tmp/watchdog-<nome>-ultima.txt (0600); JSON 1 linha {ok, rodados:[{script,ms,reportou}], falhas_tipadas} — falha de UM script não aborta os demais; exit 0 sempre.
2. scripts/watchdog_ctl.sh (0-LLM, tb_audit, dry-run default): list | enable <nome> | disable <nome> | timer-install (gera patches) | timer-status. enable/disable = chmod +x / -x no script do watchdog.d real (root no fecho; sem --apply só lista o que faria). Jamais cria/remove arquivos fora do watchdog.d.
3. watchdog.d/10-tab-reap.sh (novo, no worktree): wrapper de 3 linhas que chama a tool tab_reap do catálogo (path absoluto resolvido no runtime; no wrapper use a constante do patch) --apply e só imprime se houver mortas (padrão do watchdog já provado).
4. patches/08-watchdog-timer.sh (dry-run default): instala unit+timer systemd watchdog-sweep (.service oneshot rodando watchdog_sweep.sh; .timer OnCalendar=*:0/10, Persistent=true) + cria o diretório watchdog.d da instalação (env WATCHDOG_D_DIR) + migração do 10-tab-reap. EXECUÇÃO é do supervisor no fecho — worker NÃO toca systemctl.
5. TESTES tests/test_watchdog.py (pytest, fakes em tmpdir com WATCHDOG_D_DIR apontando pra tmp): (a) sweep roda 2 scripts, falha do 1º não impede o 2º; (b) script desabilitado (sem +x) é pulado; (c) timeout mata script dorminhoco e segue; (d) ctl dry-run não muta; (e) ctl enable chmod'a no tmpdir; (f) JSON 1 linha parseável em todos.

## REGRAS
Português/BRT; git como worker; sem sudo; sem sleep nos testes (timeout via subprocess timeout=); leitura por code_slice/code_find; git add só dos arquivos da missão.
## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd cd /home/worker/wt-WATCHDOG-CTL-01 && bash -n scripts/watchdog_sweep.sh && bash -n scripts/watchdog_ctl.sh && bash -n patches/08-watchdog-timer.sh
cmd cd /home/worker/wt-WATCHDOG-CTL-01 && TMPDIR=/tmp python3 -m pytest tests/test_watchdog.py -q | grep -q passed
cmd cd /home/worker/wt-WATCHDOG-CTL-01 && TMPDIR=/tmp python3 -m pytest tests/ -q | tail -1 | grep -q passed
cmd cd /home/worker/wt-WATCHDOG-CTL-01 && git log --format=%s | grep -q -F WATCHDOG-CTL-01
cmd cd /home/worker/wt-WATCHDOG-CTL-01 && grep -q -F WATCHDOG-CTL-01 RELATORIO-WATCHDOG-CTL-01.md
```

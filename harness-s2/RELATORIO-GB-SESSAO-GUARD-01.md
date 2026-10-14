# RELATORIO GB-SESSAO-GUARD-01

## Entrega
- `scripts/sessao_guard.sh` — sweep 1-shot que inventaria pares TUI (node ui-tui/dist/entry.js) + gateway (python -m tui_gateway.entry), agrupa por PPID, e decide por par:
  - filhos vivos de chat (cmdline com Hermes/snap scratch) => PAR VIVO, nunca matar;
  - sem filhos + colisao de HERMES_SESSION_ID com outro par OU sessao sem "tui prompt accepted" ha > GUARD_STALE_MIN (default 120) => ORFAO: SIGTERM, escalar kill -9 se sobreviver em estado R; causa tipada (ORFAO_SEM_FILHOS / LOCK_COLIDINDO) em GUARD_LOG (default stdout).
  - Fail-open: erro de leitura => pula par; nunca mata por tempo de inicio sozinho.
- Injecao: `GUARD_PS_CMD` / `GUARD_PSTREE_CMD` / `GUARD_ENV_DIR` tornam a prova hermetica.

## Prova (prova-GB-SESSAO-GUARD-01.sh, tempdir, sem rede)
- (a) par vivo com filho fake => NAO mata — PASS
- (b) orfao sem filhos com lock colidindo => mata + loga ORFAO_SEM_FILHOS — PASS
- (c) R sobrevivente a SIGTERM fake => kill -9 — PASS
- (d) erro de leitura => fail-open — PASS
- RESUMO: 0 falhas

## Stops
- bash -n scripts/sessao_guard.sh — OK
- bash scripts/prova-GB-SESSAO-GUARD-01.sh — 0 falhas
- RELATORIO-GB-SESSAO-GUARD-01.md — este arquivo
- git limpo em scripts/ + commit "GB-SESSAO-GUARD-01: guarda mata par TUI/gateway orfao com lock colidindo" — OK
# RELATORIO-TAB-REAP-01

## O que o script faz
`tab_reap.sh` detecta abas de run mortas e, com `--apply`, fecha-as via `$HERDR_BIN tab close <tab_id>`.

- Entrada: `herdr tab list` (ou `--tabs-json F`) e `runs_status.sh` (ou `--active-json F`).
- Cruzamento determinístico (0 LLM): aba morta = label começa com `RUN:`/`MISSION:`/`AGENTE:` e o missionId (trecho entre `:` e `#`) não aparece em `runs[].missionId` do active-json. Abas de label `1` ou sem os prefixos nunca são tocadas.
- Default é DRY-RUN (nada fechado). Com `--apply`, fecha só as mortas; herdr inacessível no apply → `HERDR_INACESSIVEL` sem fechar nada.
- Saída: 1 linha JSON `{"ok":true,"tool":"tab_reap","abas_total":N,"mortas":[...],"fechadas":[...],"modo":"dry-run"|"apply"}`; `exit 0` sempre (inclusive nos fail).

## Saída real do teste (`bash test_tab_reap.sh`)
```
{"ok":true,"tool":"tab_reap","abas_total":4,"mortas":[{"tab":"w8:tT1","label":"RUN:TESTE-VAZIO#s1"}],"fechadas":[],"modo":"dry-run"}
{"ok":true,"tool":"tab_reap","abas_total":4,"mortas":[{"tab":"w8:tT1","label":"RUN:TESTE-VAZIO#s1"}],"fechadas":[{"tab":"w8:tT1","label":"RUN:TESTE-VAZIO#s1"}],"modo":"apply"}
TESTE_OK
```
O teste hermético prova: dry-run NÃO fecha nada (prova vazia) e `--apply` com `HERDR_BIN` fake fecha só a aba morta (`tab close w8:tT1`), nunca as vivas (`RUN:RD-H1H2-REPORT-01#s239`, `RUN:RUN-CLOSE-01#s77`) nem a aba de label `1`.

## Nota de instalação
A instalação em `/opt/mission-events/tools-bash` é passo do SUPERVISOR no fecho (via `tools_install.sh`) — o worker NÃO instala nada fora do worktree.
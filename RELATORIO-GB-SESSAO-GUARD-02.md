# RELATORIO GB-SESSAO-GUARD-02

## Diagnostico (finding do 01, confirmado em producao)
Producao imprimiu `GUARD_PAR_OK node=1265370 gw=` — o par node+gateway real (node 1265370 pai do python 1265378, pstree: node-+-python3) ficou SEM gw no parse e o guard skipou sem avaliar orfao/lock. Causa: o casamento node<->gateway assumia pares irmaos/adjacentes no `ps aux`; em producao o gateway python e FILHO do node, e o loop em `$gw_pids` nunca casava pai com filho. Com gw vazio caia em GUARD_PAR_OK sem avaliar nada: um orfao nessa topologia NUNCA seria morto.

## Cura (scripts/sessao_guard.sh)
1. **Casamento topologico por arvore**: mapa pai->filhos construido a partir do PPID do `ps` (funcoes `desc_de`/`na_arvore`); cada node (`ui-tui/dist/entry.js`) casa com o gateway python (`tui_gateway.entry`) que esteja NA SUA ARVORE — aceita as duas topologias: python filho do node E node filho do python (sobe cadeia de PPID ate 64 niveis).
2. **Par incompleto = candidato orfao**: se um dos dois nao for encontrado na arvore, emite `GUARD_ORFAO_CANDIDATO node=... gw=... causa=GW_FORA_ARVORE|NODE_FORA_ARVORE` e NAO mata (fail-open; nunca matar por tempo sozinho). `GUARD_PAR_OK` agora so para par completo e casado na arvore — fim do skip silencioso.
3. **Inalterado**: fail-open (`GUARD_FAIL_OPEN`), env `GUARD_*` (PS_CMD/PSTREE_CMD/STALE_MIN/LOG/DRY_RUN/ENV_DIR/AGENT_LOG), prova injetavel via `GUARD_PS_CMD`, log tipado, nunca matar por tempo sozinho, nunca matar par com filho de chat vivo (`GUARD_PAR_VIVO causa=FILHO_CHAT_VIVO`).
4. Gateway sem node na arvore tambem vira candidato orfao (chave `gw_<pid>` com node vazio).

## Prova (scripts/prova-GB-SESSAO-GUARD-02.sh) — RESUMO: 0 falhas
- (a) python FILHO do node vivo com filho de chat => `GUARD_PAR_VIVO node=101 gw=102` PASS
- (b) mesma topologia, orfao sem filhos + lock colidindo (HERMES_SESSION_ID igual em 2 pares) => `LOCK_COLIDINDO` + `GUARD_DRY_RUN mataria` nos dois pares casados por arvore PASS
- (c) node FILHO do python => casa e `GUARD_PAR_VIVO node=302 gw=301` PASS
- (d) gw fora da arvore => `GUARD_ORFAO_CANDIDATO ... causa=GW_FORA_ARVORE` e `... causa=NODE_FORA_ARVORE`, sem GUARD_PAR_OK falso-positivo PASS
- (e) fail-open preservado (`GUARD_PS_CMD=false` => `GUARD_FAIL_OPEN`) PASS

## Bugs encontrados durante a cura
- `${PAIR_PY[$np]}` com `np` vazio explodia sob `set -u` (chave `gw_*`): corrigido lendo `gp` antes de zerar `np`.
- Candidatos orfao caiam no branch stale e viravam KILL antes do report: reordenado para reportar candidato orfao ANTES da avaliacao stale/kill (fail-open estrito).

Commit: c0893c0f "GB-SESSAO-GUARD-02: casamento node/gateway por arvore de processos (python filho do node)"
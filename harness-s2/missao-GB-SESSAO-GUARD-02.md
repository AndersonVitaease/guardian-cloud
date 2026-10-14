# MISSAO GB-SESSAO-GUARD-02

Fonte: ROADMAP.md linha 472 (cura do finding ao vivo do GB-SESSAO-GUARD-01: parse de pid falha em producao).

Diagnostico pronto (prova real do supervisor hoje, producao):
- scripts/sessao_guard.sh rodou no host real e imprimiu: "GUARD_PAR_OK node=1265370 gw=" — ou seja, o par node+gateway REAL (node 1265370 pai do python 1265378, pstree: node -> python -> filhos) ficou SEM gw no parse, e o guard skipou (GUARD_PAR_OK) em vez de avaliar orfao/lock.
- Causa provavel no codigo: o casamento node<->gateway (linha ~21 e 57) assume pares irmaos/adjacentes no ps aux, mas em producao o gateway python e FILHO do node (pstree: node(1265370)-+-python3(1265378)). O loop em $gw_pids nao casa o pai node com o filho python, ou o pid fica vazio por parse de coluna errada. Com gw vazio cai no GUARD_PAR_OK sem avaliar nada: um orfao nessa topologia NUNCA seria morto.
- Entrada real (dados): "ps aux" do host lista o node como "/root/.hermes/tools/node-26.7.0.../node --expose-gc" (caminho truncado varia) e o python como "/root/.hermes/tools/python-3.14.7+.../bin/python3 -m tui_gateway.entry".

Entrega (harness-s2 — arquivo UNICO: scripts/sessao_guard.sh, evolutivo do existente):
1. Casamento topologico correto: construa o mapa pai->filhos a partir do ps (PPID) e casar cada node (ui-tui/dist/entry.js) com o gateway python (tui_gateway.entry) que esteja NA SUA ARVORE (descendente direto ou o python pai do node — aceitar as duas topologias: python filho do node e node filho do python). Se um dos dois nao for encontrado na arvore, o par e candidato a ORFAO (nao GUARD_PAR_OK).
2. Em nada mudar: fail-open, GUARD_* env, prova injetavel, log tipado, nunca matar por tempo sozinho, nunca matar par com filho de chat vivo.
3. Prova (prova-GB-SESSAO-GUARD-02.sh ou evolua a 01): cenario (a) python FILHO do node vivo com filho de chat => PAR_VIVO; (b) mesma topologia com orfao sem filhos e lock colidindo => KILL; (c) node filho do python => tambem casa; (d) gw nao encontrado na arvore => candidato orfao (nao skip silencioso); (e) fail-open preservado. RESUMO: 0 falhas.

MAPA:
- scripts/sessao_guard.sh:21 (parse gw_pids do ps)
- scripts/sessao_guard.sh:29-31 (leitura de environ por pid, GUARD_ENV_DIR)
- scripts/sessao_guard.sh:57-104 (loop de casamento e veredictos tipados)

Stops (4):
```harness-stop
cmd cd /home/worker/wt-GB-SESSAO-GUARD-02 && bash -n scripts/sessao_guard.sh
cmd cd /home/worker/wt-GB-SESSAO-GUARD-02 && bash scripts/prova-GB-SESSAO-GUARD-02.sh
cmd cd /home/worker/wt-GB-SESSAO-GUARD-02 && test -f RELATORIO-GB-SESSAO-GUARD-02.md
cmd cd /home/worker/wt-GB-SESSAO-GUARD-02 && test "$(git log -1 --format=%s)" = "GB-SESSAO-GUARD-02: casamento node/gateway por arvore de processos (python filho do node)"
```

Restricoes: SO scripts/sessao_guard.sh + prova + relatorio neste worktree. Nao toque em systemd (supervisor instala), /opt, /root. Proibido: git reset, checkout, stash, clean, push — nunca.

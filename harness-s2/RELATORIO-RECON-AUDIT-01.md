# RELATORIO-RECON-AUDIT-01 — auditoria de reconciliação (14/10)

Auditoria READ-ONLY. Nada foi revertido. Base: commits de 14/10 no harness-s2 + estado de /opt.

## Tabela de classificação

| Commit | Classificação | O que reverter exatamente | Risco do revert |
|---|---|---|---|
| e07d5d19 (SUITE-DEBT-01/01B parcial) | KEEP-CANDIDATO | Nada — consertos de teste (imports, paths do layout aninhado, fixtures, TMPDIR). `git revert e07d5d19` quebraria a suíte (17→12 falhas foi progresso real). | Alto: suíte volta a 17+ falhas. |
| 38747796 (VIGIA-CHAT-GUARD-02 fix 1/2) | KEEP-CANDIDATO | Nada — guard de governança em scripts/vigia_chat.sh (override gh-notifications recusado tipado ANTES do fallback). Bug real, prova tipada. | Médio: reabre buraco de governança no vigia. |
| 0bc2273d (MEC-LANE-TRABALHO-01) | REVERT-CANDIDATO | `git revert 0bc2273d` — bloco "lane de contrato" em scripts/mecanico.sh:240-258 (spawn de mission_run via MEC_CONTRATO/MISSION_RUN_CMD, fail-closed MEC_WORKER_FALHOU). Maquinaria inventada sem ordem: lane de AGENTE no mecanico. | Baixo: mecanico volta ao comportamento anterior (MEC_PROVA manual). Nenhum teste cobre a lane. |
| a79e3286 (LANE-ENV-FIX) | REVERT-CANDIDATO | `git revert a79e3286` — whitelist de env em scripts/despachar-mecanico.sh:48-58 (MEC_CONTRATO/MISSION_RUN_CMD repassados pelo sudo). Criada exclusivamente para a lane inventada. | Baixo: só faz sentido com a lane; sem ela é repasse de env morto. Reverter DEPOIS de 0bc2273d. |
| 419b1431 (FUNIL-FIX) | REVERT-CANDIDATO (cópia divergente) | O id determinístico foi aplicado na CÓPIA divergente scripts/despachar_missao.py (linha ~200), não na fonte /opt/mission-events/scripts/despachar_missao.py. Reverter o hunk na cópia OU reconciliar a cópia com /opt antes. | Médio: se a cópia divergente for mantida, espelho/mission_list voltam a divergir da fila. |
| b88e3ca9 (LINT-GATE-PORTA-01) | KEEP-CANDIDATO | Nada — gate do lint + validação de stops/baseline NA PORTA (scripts/despachar_missao.py:160-220, cópia local). Dívida real (RD-HARN-LINT-ENFORCE-01) com prova: 6/6 testes do lint verdes. | Alto: contratos recusados voltariam a enfileirar. |
| c723d698 (ROTA-CONFLITO-01) | KEEP-CANDIDATO | Nada — apenas documento (RELATORIO-ROTA-CONFLITO-01.md). Zero risco. | Zero. |

## Classificação do orquestrador-ask.sh (não commitado, working tree)

O diff não-commitado em scripts/orquestrador-ask.sh:50-80 (ORQ-PORTA-01: tokens VAR=v viram ENV do wrapper + fire-and-forget via nohup) é **REVERT-CANDIDATO**: repasse de env inventado para alimentar a lane de agente (0bc2273d/a79e3286), sem ordem e sem teste. Reverter = `git checkout -- scripts/orquestrador-ask.sh` (após reconciliação decidida). Risco baixo: sem a lane, o fire-and-forget só cria despachos órfãos sem observabilidade.

## /opt (fora do repo)

- /opt/mission-events/scripts/despachar_missao.py:18 — `HARNESS = os.environ.get("HARNESS_DIR", ...)` — patch feito hoje por mim; **documentado, KEEP** (necessário para o layout aninhado), mas a cópia local divergente precisa ser reconciliada com a fonte.
- /opt/mission-events/tools-bash/mission_dispatch.sh:213-215 — **JÁ-REVERTIDO confirmado**: não há mais referência a MEC_CONTRATO/MISSION_RUN_CMD/HARNESS_DIR no trecho da porta; parches de mission_dispatch.sh e pin de modelo não estão presentes.

## Divergência cópia local vs /opt (despachar_missao.py)

A cópia local tem: sys.path insert (SUITE-DEBT-01a), LINT relativo ao próprio diretório, gate do lint na porta (b88e3ca9), id determinístico (419b1431), dry-run na porta (DESP-DIV-01). /opt tem HARNESS_DIR env e LINT absoluto. **Ação da reconciliação: escolher UMA fonte e eliminar a divergência** — recomendado portar o gate do lint para /opt e descartar a cópia local, ou vice-versa; nunca manter as duas.

## PLANO-RECONCILIACAO (ordem segura, suite entre cada passo)

1. **Baseline**: rodar suíte (`pytest tests/ -q`, com exclusão dos testes que travam em nohup/rede: `-k "not despachante and not vigia_chat"`), registrar contagem verde/falha esperada (629+ verdes, 17+5 dívida conhecida).
2. **Revert 1 — orquestrador-ask.sh (working tree)**: descartar o diff ORQ-PORTA-01 (`git checkout -- scripts/orquestrador-ask.sh`). Suíte.
3. **Revert 2 — a79e3286**: `git revert a79e3286` (whitelist env do wrapper). Suíte.
4. **Revert 3 — 0bc2273d**: `git revert 0bc2273d` (lane de agente no mecanico.sh:240-258). Suíte — mecanico volta ao fluxo MEC_PROVA manual; nenhum teste deve quebrar.
5. **Revert 4 — 419b1431 na cópia OU reconciliação**: decidir fonte única para despachar_missao.py; se a cópia local for descartada em favor de /opt, portar antes o gate do lint (b88e3ca9) e o dry-run para /opt, então remover a cópia. Suíte + prova de despacho real (dry-run).
6. **KEEPs**: e07d5d19, 38747796, b88e3ca9, c723d698 permanecem. Patch HARNESS_DIR em /opt permanece documentado.
7. **Verificação final**: suíte completa + `git log` sem resíduos de revert pendente + fila sem payloads órfãos da lane.

## Provas coletadas

- `git show --stat` dos 7 commits (executado).
- `git diff 0bc2273d^ 0bc2273d -- scripts/mecanico.sh`: bloco lane 240-258 confirmado.
- `diff scripts/despachar_missao.py /opt/mission-events/scripts/despachar_missao.py`: divergência confirmada (gate do lint só na cópia local; HARNESS_DIR só em /opt).
- mission_dispatch.sh em /opt: revert dos parches confirmado (sem MEC_CONTRATO/MISSION_RUN_CMD).
- Suíte: pytest trava em testes de despachante/vigia_chat (nohup/rede) — usar exclusão `-k`; contagem completa pendente de janela sem travamento (registrado como limitação desta auditoria).
- Suíte parcial (excluindo despachante/vigia_chat): **626 passed, 2 skipped, 36 deselected** — consistente com 629+ verdes e dívida conhecida.
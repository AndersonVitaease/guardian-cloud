# RELATORIO-MAPA-ROTA-ANTIGA (GB-MAPA-ROTA-01)

- total de referencias: 432
- uso vivo (fora de textos de proibicao/ensino): 360

## Uso vivo (candidato a migrar para a rota mecanico)

- harness-s2/RELATORIO-DESP-FECHO-ROBUSTO-01.md:4 [despachar_missao] `scripts/despachar_missao.py` L147 usava ` ; ` entre 3 comandos dentro de um unico valor `--property=ExecStopP
- harness-s2/RELATORIO-DESP-FECHO-ROBUSTO-01.md:8 [despachar_missao] - `scripts/despachar_missao.py` (EDIT, L147): substituido por um unico `--property=ExecStopPost=-+/bin/bash /h
- harness-s2/RELATORIO-DESP-FECHO-ROBUSTO-01.md:19 [despachar_missao] 2. `python3 -m py_compile reconciliar_resumos.py despachar_missao.py` -> OK (PY_OK).
- harness-s2/RELATORIO-DESP-FECHO-ROBUSTO-01.md:20 [despachar_missao] 3. `grep fechar_missao.sh despachar_missao.py` OK; antigo `ExecStopPost=-+/usr/bin/python3` removido -> OK (ED
- harness-s2/RELATORIO-DESP-FECHO-ROBUSTO-01.md:28 [systemd_harness_unit] systemd-run --uid=worker --unit=prova-fecho-01 --collect --property=ExecStopPost=-+/bin/bash /home/worker/harn
- harness-s2/missao-RD-ENG-MCP-WORKER-01.md:24 [wt_spin] - tools-bash/test_run.sh / test_wt_spin.sh — padrão dos testes irmãos
- harness-s2/MISSAO-STOP-STALE-01B.md:8 [despachar_missao] - harness.py: pontos relevantes = avaliação de stop-conditions por tick (_stop_check), veredito por tentativa,
- harness-s2/MISSAO-STOP-STALE-01B.md:12 [despachar_missao] - despachar_missao.py — leitura de resumo/autoretry-summary para o auto-retry.
- harness-s2/MISSAO-ORQ-HYGIENE-01.md:9 [mission_run_spawn] - Contexto medido ao vivo (10/10, supervisor): watcher zumbi PID 84132 era `bash -lic ... while pgrep -f "miss
- harness-s2/mission_run.py:3 [mission_run_spawn] # Uso: /usr/bin/python3 mission_run.py --mission /opt/mission-events/missao-X.md \
- harness-s2/RELATORIO-VIGIA-DEDUPE-01.md:4 [despachar_missao] O vigia por missao (`scripts/vigia_run.py`, spawnado por `despachar_missao.py:163-180`) emitia eventos sem qua
- harness-s2/missao-VIGIA-NASCER-01.md:6 [despachar_missao] - `scripts/vigia_run.py` — roda junto com toda missão (spawn do despachar_missao.py ~L163-180), grava eventos 
- harness-s2/missao-VIGIA-NASCER-01.md:17 [despachar_missao] - NÃO mexa em vigia_run.py, despachar_missao.py, mission_run.py (a fiação final é do supervisor).
- harness-s2/missao-VIGIA-NASCER-01.md:17 [mission_run_spawn] - NÃO mexa em vigia_run.py, despachar_missao.py, mission_run.py (a fiação final é do supervisor).
- harness-s2/prova-GB-DESP-CLEAN-01.py:8 [despachar_missao] Importa despachar_missao como modulo (geteuid mockado para 0 — prova roda como worker),
- harness-s2/prova-GB-DESP-CLEAN-01.py:15 [despachar_missao] SCRIPT = os.path.join(HERE, "scripts", "despachar_missao.py")
- harness-s2/prova-GB-DESP-CLEAN-01.py:19 [despachar_missao]     spec = importlib.util.spec_from_file_location("despachar_missao", SCRIPT)
- harness-s2/prova-DESP-STOP-01.py:5 [despachar_missao] STOP_INTERPRETE_ESTRANHO com o nome do arquivo; despachar_missao.py recusaria com
- harness-s2/prova-DESP-STOP-01.py:82 [despachar_missao]         falhas.append("despachar_missao.py sem caminho LINT_RECUSADO")
- harness-s2/test_wt_spin.sh:2 [wt_spin] # test_wt_spin.sh — teste hermético de wt_spin.sh.
- harness-s2/test_wt_spin.sh:2 [wt_spin] # test_wt_spin.sh — teste hermético de wt_spin.sh.
- harness-s2/test_wt_spin.sh:29 [wt_spin] bash -n wt_spin.sh && ok "bash -n" || bad "bash -n"
- harness-s2/test_wt_spin.sh:32 [wt_spin] OUT=$(bash wt_spin.sh WT-Spin-99)
- harness-s2/test_wt_spin.sh:44 [wt_spin] OUT2=$(bash wt_spin.sh WT-Spin-99)
- harness-s2/test_wt_spin.sh:50 [wt_spin] OUT3=$(bash wt_spin.sh WT-Spin-98 --no-probe)
- harness-s2/test_wt_spin.sh:54 [wt_spin] OUT4=$(bash wt_spin.sh WT-Spin-97 rd-segue-01)
- harness-s2/test_wt_spin.sh:58 [wt_spin] OUT5=$(bash wt_spin.sh)
- harness-s2/test_wt_spin.sh:62 [wt_spin] OUT6=$(bash wt_spin.sh WT-Spin-96 rd-nao-existe)
- harness-s2/RELATORIO-MISSAO-FECHAR-TIMEOUT-01.md:86 [despachar_missao]   `reconciliar_resumos.py` e o ExecStopPost em `despachar_missao.py` ficaram
- harness-s2/RELATORIO-RD-TEST-SYSTEMD-01.md:6 [systemd_harness_unit]   - `test_systemd_run_true`: argv no formato de `comando_despacho` (`systemd-run --uid=worker --unit=harness-p
- harness-s2/missao-AUTORETRY-TURNS-01.md:4 [mission_run_spawn] - mission_run.py | ~3 linhas | No bloco 'if args.auto_retry > 0:' (linha ~229-233), na chamada rodar_com_retry
- harness-s2/RELATORIO-RD-HARN-DEBUGINFRA-01.md:6 [mission_run_spawn] - `--modo debug` em mission_run.py: janela crua de contexto turnos 12-40 (tool_results ate 12000 chars), sumar
- harness-s2/RELATORIO-RD-HARN-DEBUGINFRA-01.md:13 [mission_run_spawn] python3 mission_run.py --modo debug ...
- harness-s2/RELATORIO-RD-HARN-DEBUGINFRA-01.md:14 [mission_run_spawn] python3 mission_run.py --memoria runs/<run>/harness-trail.jsonl ...
- harness-s2/test_orq_hygiene.sh:13 [mission_run_spawn] printf '84132 worker bash -lic while pgrep -f "mission_run.py.*SHIP" ; do sleep 20 ; done\n' > "$TMP/proc_a.tx
- harness-s2/test_orq_hygiene.sh:23 [orchestrator_queue] 3772362 worker orqd.daemon --db /var/lib/orqd/orqd.db --workspace w8 --queue /opt/mission-events/orchestrator-
- harness-s2/missao-GB-DESP-CLEAN-01.md:11 [despachar_missao]    mount-espelho; chamada em TODOS os caminhos de saída do despachar_missao.py
- harness-s2/missao-GB-DESP-CLEAN-01.md:21 [despachar_missao] - scripts/despachar_missao.py:243-267 (bloco espelho/aba + PANE_AUSENTE existente) e o
- harness-s2/missao-GB-DESP-CLEAN-01.md:24 [despachar_missao] O despachar_missao.py VIVO fica em /home/worker/harness-s2/scripts/ — trabalhe numa
- harness-s2/missao-GB-DESP-CLEAN-01.md:35 [despachar_missao] cmd cd /home/worker/wt-GB-DESP-CLEAN-01 && python3 -m py_compile scripts/despachar_missao.py
- harness-s2/missao-VIGIA-CHAT-01.md:15 [despachar_missao] - Gancho existente: `scripts/despachar_missao.py:147-149` injeta `ExecStopPost=-+/usr/bin/python3 scripts/ledg
- harness-s2/missao-VIGIA-CHAT-01.md:33 [despachar_missao] 2. `patches/07-vigia-chat-hook.sh [--apply]`: patch IDEMPOTENTE que anexa ao bloco ExecStopPost existente em `
- harness-s2/missao-VIGIA-CHAT-01.md:33 [despachar_missao] 2. `patches/07-vigia-chat-hook.sh [--apply]`: patch IDEMPOTENTE que anexa ao bloco ExecStopPost existente em `
- harness-s2/missao-VIGIA-CHAT-01.md:33 [despachar_missao] 2. `patches/07-vigia-chat-hook.sh [--apply]`: patch IDEMPOTENTE que anexa ao bloco ExecStopPost existente em `
- harness-s2/missao-VIGIA-CHAT-01.md:34 [despachar_missao] 3. `tests/test_vigia_chat.py` — pytest com rota FAKE (tmp_path: servidor http simples em thread ou arquivo + `
- harness-s2/missao-VIGIA-CHAT-01.md:8 [mission_run_spawn] O pipeline novo (mission_run.py + ledger + ExecStopPost) fecha a missão mas NÃO avisa o operador no chat. O pi
- harness-s2/prova-GB-DESP-ORDEM-01.py:107 [despachar_missao]     desp = os.path.join(SCRIPTS, "despachar_missao.py")
- harness-s2/prova-GB-DESP-ORDEM-01.py:119 [mission_run_spawn]     # run dir pré-nascido: o systemd-run fake não executa mission_run.py;
- harness-s2/RELATORIO-VAGUEIO-01.md:23 [mission_run_spawn] 5. **CLI**: `mission_run.py --vagueio on|off` (default on); `HARNESS_VAGUEIO=0`
- harness-s2/RELATORIO-VAGUEIO-01.md:32 [mission_run_spawn] - `mission_run.py --help` → exit 0.
- harness-s2/test_funil_unico.py:34 [despachar_missao]     fonte = os.path.join(BASE, "scripts", "despachar_missao.py")
- harness-s2/test_funil_unico.py:37 [despachar_missao]     assert "espelho_nativo" in src, "despachar_missao.py nao importa espelho_nativo"
- harness-s2/test_funil_unico.py:38 [despachar_missao]     ok("despachar_missao.py chama espelho_nativo")
- harness-s2/test_funil_unico.py:47 [despachar_missao]     repo = os.path.join(BASE, "scripts", "despachar_missao.py")
- harness-s2/test_funil_unico.py:48 [despachar_missao]     ref = os.path.join(BASE, "fixtures", "despachar_missao.expected.py")
- harness-s2/test_funil_unico.py:50 [despachar_missao]     assert sha(repo) == sha(ref), "dessincronia: despachar_missao.py != fixtures/despachar_missao.expected.py"
- harness-s2/test_funil_unico.py:50 [despachar_missao]     assert sha(repo) == sha(ref), "dessincronia: despachar_missao.py != fixtures/despachar_missao.expected.py"
- harness-s2/test_funil_unico.py:51 [despachar_missao]     ok("sha256 sincrono: repo == fixtures/despachar_missao.expected.py")
- harness-s2/CONTRATO-RD-PASS-OCO-01.md:6 [despachar_missao] - O fechamento da run chama `scripts/ledger_missao.py fechar <ID> --resumo /tmp/resumo-<ID>.json` (ExecStopPos
- harness-s2/missao-VIGIA-NASCER-03.md:9 [despachar_missao] - `despachar_missao.py` — roda como ROOT; após o spawn bem-sucedido (onde obtém `pane` e `run_dir`, procure "e

## Referencias so-educativas (proibicoes/ensinamentos — manter)
- 72 ocorrencias

GB-MAPA-ROTA-01-PROVA-OK
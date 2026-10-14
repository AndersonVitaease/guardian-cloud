# RELATORIO — RD-DEPLOY-TOOL-01

- Tool governada `deploy_janela` implementada: `scripts/deploy_janela.py` (planos JSON com steps tipados: merge, tools_install, systemd_edit, service_restart, ledger_close, probe; backup → ação → prova → rollback), wrapper fino `tools-bash/deploy_janela.sh` (`exec python3 "$(dirname "$0")/../scripts/deploy_janela.py" "$@"`) e `tests/test_deploy_janela.py`.
- TDD cumprido: commit `b7ec4ed9` do aceite vermelho (8 failed, módulo inexistente), depois código verde (`1b62c00d`).
- `sudo -u worker python3 -m pytest tests/test_deploy_janela.py -q` → **8 passed in 0.48s** (casos a–f do contrato: PLAN_INVALID sem mutação, OPERATOR_ORDER_REQUIRED, rollback de merge com prova falha, dry-run 0 mutação, comando certo por tipo, JSON 1 linha com untrusted/notice).
- `python3 -m py_compile scripts/deploy_janela.py` ok; `bash -n tools-bash/deploy_janela.sh` ok; `git_peek status` limpo pós-commits.
- Saída JSON de 1 linha com `untrusted:true` e `notice`, exit 0 sempre (verificado nos 8 testes, dry-run e apply).
- Limitações anotadas: rollback por step NÃO implementado nesta versão (fica para a próxima missão) — o fluxo atual executa rollback apenas do step que falhou; merge, systemd_edit e tools_install executam subprocess real quando DEPLOY_FAKE ausente.
- Sem sudo no código, sem _lib.sh no wrapper, sem mutação de systemd/repos reais nos testes (fakes via env DEPLOY_FAKE=1 com estado/log em tmpdir).

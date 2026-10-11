# RELATORIO DESP-FECHO-ROBUSTO-01

## Bug
`scripts/despachar_missao.py` L147 usava ` ; ` entre 3 comandos dentro de um unico valor `--property=ExecStopPost=...`. systemd nao divide comandos dentro de um valor de property -> ledger fechar, tab_reap e vigia_chat nunca rodavam no stop.

## Arquivos
- `scripts/fechar_missao.sh` (NOVO): arg `{id}`; `set +e`; passos independentes (ledger fechar, tab_reap --apply, vigia_chat --send), 2 tentativas cada, linhas FAIL tipadas em `/tmp/fechar_missao-{id}.log`; sempre `exit 0`; idempotente.
- `scripts/despachar_missao.py` (EDIT, L147): substituido por um unico `--property=ExecStopPost=-+/bin/bash /home/worker/harness-s2/scripts/fechar_missao.sh %s`.
- `scripts/reconciliar_resumos.py` (NOVO, stdlib): le `/tmp/resumo-*.json`, extrai `{id}`; se entrada no ledger ainda `dispatched`/`running`, roda `bash fechar_missao.sh {id}`; imprime JSON `{checked, refechados, erros}`.
- `systemd/mission-watcher-fecho.conf` (NOVO): drop-in para o supervisor aplicar (nunca edita /etc).
- `scripts/prova-fecho-robusto-01.sh` (NOVO): resumo fake `/tmp/resumo-PROVA-FECHO.json`; roda fechar_missao.sh PROVA-FECHO 2x; asserta exit 0 nas duas e log presente.

## Simbolos
- fechar_missao.sh: `log()`, `step()` (2 retries, FAIL tipado).
- reconciliar_resumos.py: `ledger_estado(mid)`, `main()`.

## Saidas das stop-conditions
1. `bash -n scripts/fechar_missao.sh` + `grep "exit 0"` -> OK (BASH_OK).
2. `python3 -m py_compile reconciliar_resumos.py despachar_missao.py` -> OK (PY_OK).
3. `grep fechar_missao.sh despachar_missao.py` OK; antigo `ExecStopPost=-+/usr/bin/python3` removido -> OK (EDIT_OK).
4. `bash scripts/prova-fecho-robusto-01.sh` -> `PROVA OK rc1=0 rc2=0`; `/tmp/fechar_missao-PROVA-FECHO.log` presente (LOG_OK).
5. `RELATORIO-DESP-FECHO-ROBUSTO-01.md` presente (este arquivo).

## Divida / teste live pendente (supervisor-applied)
Teste ao vivo de unit systemd com ExecStopPost quebrado exige aplicar drop-in no host — supervisor-applied. Comandos exatos:
```
systemctl edit mission-watcher   # aplicar systemd/mission-watcher-fecho.conf
systemd-run --uid=worker --unit=prova-fecho-01 --collect --property=ExecStopPost=-+/bin/bash /home/worker/harness-s2/scripts/fechar_missao.sh PROVA-FECHO-01 /bin/sleep 2
systemctl stop prova-fecho-01
cat /tmp/fechar_missao-PROVA-FECHO-01.log
python3 /home/worker/harness-s2/scripts/reconciliar_resumos.py
```

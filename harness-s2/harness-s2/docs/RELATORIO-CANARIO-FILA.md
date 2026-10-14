# RELATORIO-CANARIO-FILA.md

canario_fila_ok

## Canário contínuo da fila (CANARIO-FILA-01)

CLI `scripts/canario_fila.py`: enfileira um intent de dispatch
(`mission_dispatch`, priority 0, missionId `CANARIO-FILA-<ts>`), espera o
consumer registrar `dispatch_via_harness: <missionId>` no log, checa o run
dir mais recente (existe, owner `worker:worker`, `harness-pane.log`
presente) e imprime uma linha PTBR:

```
CANÁRIO CANARIO-FILA-<ts> | OK/FAIL | despacho=OK run=OK owner=worker
```

Exit 0 se tudo OK, 1 se qualquer etapa falhar (FAIL honesto, nunca
silencioso). Com `--json`, imprime também um JSON com detalhes.

### Parâmetros

- `--fila` (default `/opt/mission-events/orchestrator-queue.jsonl`)
- `--log` (default `/opt/mission-events/orchestrator-consumer.log`)
- `--base-runs` (default `/home/worker/harness-s2/runs/`)
- `--json`, `--ciclos` (6), `--intervalo` (60s)

### Instalação do timer (passos do supervisor — worker NÃO escreve em /etc)

1. Criar `/etc/systemd/system/canario-fila.service`:

```ini
[Unit]
Description=Canário contínuo da fila (CANARIO-FILA-01)

[Service]
User=worker
Type=oneshot
ExecStart=/usr/bin/python3 /home/worker/harness-s2/scripts/canario_fila.py --json
# resultado vai para o journal; para logar em arquivo também:
# ExecStart=/bin/sh -c '/usr/bin/python3 /home/worker/harness-s2/scripts/canario_fila.py --json >> /home/worker/harness-s2/canario-fila.log 2>&1'
```

2. Criar `/etc/systemd/system/canario-fila.timer`:

```ini
[Unit]
Description=Timer horário do canário da fila

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

3. Ativar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now canario-fila.timer
systemctl list-timers canario-fila.timer
journalctl -u canario-fila.service -n 20
```

### Testes

`/usr/bin/python3 -m pytest tests/test_canario_fila.py -q` — 9 passed
(tmp dirs apenas; nunca contra a fila real de produção).
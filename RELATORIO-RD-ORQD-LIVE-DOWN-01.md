# RELATÓRIO RD-ORQD-LIVE-DOWN-01

ORQD-SENTINEL-OK

## Diagnóstico: por que nenhum alarme existia
O orqd-live.service ficou parado de 09/10 22:53 até 11/10 ~02:47 BRT sem disparar
qualquer alarme. Causa raiz: não havia NENHUMA checagem de liveness ativa para esse
serviço — o watchdog da casa não tinha um sentinel dedicado em /opt/hermes/watchdog.d/
para orqd-live, e o canário da fila só passou porque alguém subiu o serviço na mão
(~14:4x BRT). Ou seja: parado = parado, mas ninguém estava olhando. Doutrina da casa
exige liveness honesta; este entregável fecha essa lacuna.

## ACHADO (estado real)
- orqd-live NÃO existe como unit systemd no host (sem orqd-live.service em
  list-unit-files). O sentinel cobre AMBOS os caminhos: unit (se um dia existir) e
  processo (pgrep -x orqd-live) como heartbeat equivalente.
- Processo 2424807 (orqd-live) visto hoje em execução após o religamento manual —
  estado atual: vivo, mas sem cobertura de watchdog até esta entrega.

## Entregáveis
- watchdog/orqd-live-sentinel.sh — verifica systemctl is-active orqd-live (se a unit
  existir) OU pgrep do processo; exit 0 = saudável, exit 1 = ALERTA com 1 linha JSON
  {"ok":false,"check":"orqd-live","detalhe":...}. Só detecta: sem restart, sem conserto.
- test_orqd_live_sentinel.sh — teste hermético (systemctl/pgrep fake via PATH override),
  3 casos: ativo (verde), inativo (vermelho), comando inexistente (vermelho).

## Como instalar (linha de comando)
```
sudo install -m 0755 watchdog/orqd-live-sentinel.sh /opt/hermes/watchdog.d/orqd-live-sentinel.sh
```
O watchdog existente da casa aciona os scripts de /opt/hermes/watchdog.d/; nenhum
agendamento extra é necessário.

## Prova dos testes
```
$ bash test_orqd_live_sentinel.sh
OK   servico ativo (exit 0)
OK   servico inativo (exit 1)
OK   comando inexistente (exit 1)
TESTES: 3/3 verdes
$ bash -n watchdog/orqd-live-sentinel.sh   # limpo
```
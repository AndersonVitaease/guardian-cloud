# MISSÃO GB-PLUGIN-ROTA-01 — ensinar a rota correta de despacho (arquivos de estudo)

Fonte: operador 13/10. Rota correta de despacho de missão:
`despachar_missao.py <contrato> <worktree> --seed N --budget B --executar`
(spawn nativo: unit + aba RUN:<ID>#s<seed> no herdr + espelho /tmp/ag-live +
marcador .espelho-nativo + avisos de nascimento/morte no chat do operador).
Rota ERRADA = a do plugin: handle_mission_dispatch spawna claude direto no pane
com cwd do payload — desvia do despachar nativo.

## CONTEXTO (mapa pré-digerido)
- /root/.hermes/plugins/mission-ops/__init__.py vivo tem só 102 linhas (só snapshot);
  o completo está em __init__.py.bak-SNAP-RUN-01 (4900 linhas) — leitura do .bak é
  diagnóstico liberado pelo supervisor; worker NUNCA escreve fora do worktree.
- Referências da rota correta: scripts/despachar_missao.py:176 (payload), :234
  (cwd = worktree/runs/ID), :249-255 (guard duplicidade), :278-280 (glob run dir),
  :314-315 (systemd-run + --cwd), :424-427 (aviso nascimento),
  scripts/espelho_nativo.py:29-50, scripts/mount-espelho.sh:1-12.

## Entrega 1 — patches/GB-PLUGIN-ROTA-01/__init__.py
Arquivo de estudo p/ deploy no fecho: cópia do .bak-SNAP-RUN-01 com
handle_mission_dispatch MODIFICADO — após os gates (preflight, cap 24h, chain_gate),
NÃO spawnar claude no pane; delegar via subprocess:
["python3", "/opt/mission-events/scripts/despachar_missao.py", promptFile,
 cwd_resolvido, "--executar", "--seed", seed, "--budget", budget]
cwd_resolvido = "<worktree>/runs/<missionId>" (args.worktree); payload.cwd só vale
se começar com "<worktree>/runs/". Seed: args.seed ou aleatória; budget: 0.30 default.
Resultado JSON do despachar retorna tipado.

## Entrega 2 — ensinamentos (3 .md no mesmo diretório)
- despachante-MEMORY.patch.md: texto exato do item 1 das Regras de ferro da memória
  do despachante: "1. Despacho de missão = SEMPRE despachar_missao.py <contrato>
  <worktree> --seed N --budget B [--executar]. NUNCA pelo plugin mission-ops
  handle_mission_dispatch nem por spawn de claude no pane."
- contratador-ROTA.md: mesma regra para o contratador.
- ORDENS-FIXAS-item13.md: item 13 = rota correta + proibição do caminho plugin.

## Entrega 3 — prova hermética prova-GB-PLUGIN-ROTA-01.py (exit 0)
Importa o arquivo da Entrega 1 com mocks (mc fake, subprocess mockado) e prova:
(a) args.worktree → despachar chamado com cwd "<wt>/runs/<ID>" e --executar;
(b) payload.cwd fora do padrão → corrigido; (c) gate recusando → zero chamadas;
(d) NENHUM spawn de claude (run_command). Marker final GB-PLUGIN-ROTA-01-PROVA-OK.

## Regras
- SÓ escreve no worktree. PT-BR (BRT). Commit único:
  `GB-PLUGIN-ROTA-01: rota correta de despacho ensinada (plugin delega ao despachar_missao --executar) + ensinamentos despachante/contratador/ORDENS-FIXAS`.

```harness-stop
cmd cd /home/worker/wt-GB-PLUGIN-ROTA-01 && test -f patches/GB-PLUGIN-ROTA-01/__init__.py
cmd cd /home/worker/wt-GB-PLUGIN-ROTA-01 && python3 prova-GB-PLUGIN-ROTA-01.py 2>&1 | grep -q -F 'GB-PLUGIN-ROTA-01-PROVA-OK'
cmd cd /home/worker/wt-GB-PLUGIN-ROTA-01 && test -z "$(git status --porcelain)"
```

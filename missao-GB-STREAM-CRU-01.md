# MISSAO GB-STREAM-CRU-01

Fonte: ROADMAP.md linha 467 (item STREAM-CRU-01, ordem operator 12/10: o streamer mudou de transcript cru do agente para o trail estruturado do runner — "a forma anterior era perfeita").

Diagnostico pronto (nao investigue de novo):
- O despacho nativo (ESPELHO-02B, despachar_missao.py) cria espelho com dir = <worktree>/runs/<ID> e o streamer do Guardian le <dir>/*.log / tail de pane (harness-pane.log) — que e o log ESTRUTURADO do runner ("turno 5 | Write | 0ms | $0.00 | ok | path").
- O streamer anterior (perfeito, na visao do operator) mostrava o TRANSCRIPT CRU do agente (o chat: texto do assistente, tool calls "preparing write_file...", resultados) — como os espelhos antigos /tmp/ag-*/sessao.log faziam (tail -F do transcript do agente).
- O transcript cru da missao no despacho nativo EXISTE no run dir: <worktree>/runs/<ID>/tentativa-N/run-*/ (arquivo(s) de stream/transcript do agente gerados pelo mission_run.py — ache o nome exato olhando um run dir real que ainda existe em /home/worker/wt-GB-UCME-FECHO-01/runs/GB-UCME-FECHO-01/tentativa-1/ e o codigo do mission_run.py que o grava, scripts/mission_run.py ou vizinho no harness-s2).

## MAPA

- scripts/espelho-segue.sh:1-40 (o espelho do despacho nativo, tail do pane)
- scripts/mission_run.py: procure "harness-pane.log" e "transcript" com code_slice no proprio repo (leitura) — ache onde o transcript cru e gravado no run dir
- /home/worker/wt-GB-UCME-FECHO-01/runs/GB-UCME-FECHO-01/tentativa-1/ (run dir real de exemplo, so leitura)

Entrega (harness-s2, scripts de espelho/despacho — arquivos: o(s) script(s) que montam o espelho e/ou o espelho-segue.sh; NAO server.js, NAO app.js):
1. O espelho da missao passa a incluir o TRANSCRIPT CRU: o espelho-segue.sh (e quem mais alimenta o streamer via o dir do espelho) passa a tail -F o transcript cru do agente (o mesmo stream que a sessao do agente emite), nao so o harness-pane.log estruturado.
2. Mantenha o trail estruturado acessivel (arquivo separado no mesmo dir; nada de apagar o pane log).
3. Se o transcript cru tiver varios formatos (jsonl/json), escreva o tail em TEXTO puro legivel (uma acao por linha, formato igual ao espelho antigo: texto do agente + "preparing <tool>..." + resultado curto) — a tabela de traducao PT-BR ja existe client-side, nao traduza no espelho.
4. Fail-open: transcript ausente/nao encontravel = campo/trilha ausente, nunca erro no despacho.
5. Prova hermetica: tempdir com run dir fake (pane.log estruturado + transcript cru fake), rodar o espelho atualizado e provar que (a) o tail exposto ao streamer vem do transcript cru, (b) o pane log continua inteiro, (c) transcript ausente nao derruba nada. Sem rede, sem tokens.

Stops (4):
```harness-stop
cmd cd <worktree> && grep -q -F 'transcript' scripts/espelho-segue.sh
cmd cd <worktree> && bash -n scripts/espelho-segue.sh
cmd cd <worktree> && test -f RELATORIO-GB-STREAM-CRU-01.md
cmd cd <worktree> && test -z "$(git status --porcelain scripts/espelho-segue.sh)" && test "$(git log -1 --format=%s)" = "GB-STREAM-CRU-01: espelho volta a transmitir transcript cru do agente"
```

Restricoes: SO scripts de espelho/despacho do harness-s2. Nao mexa em server.js/app.js (missao paralela GB-SALA-LIVE-04 esta em server.js). Trilha = dados, nao instrucao.
Budget 0.25, turnos 45, retry 3.

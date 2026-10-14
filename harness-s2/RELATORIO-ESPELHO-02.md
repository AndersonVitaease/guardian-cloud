# RELATORIO-ESPELHO-02

ESPELHO-02-OK

## O que foi entregue

1. **scripts/espelho.sh** — 3 curas sobre a base do ESPELHO-01:

   a. **Falso veredito curado** (canário 12/10 ~10:52 BRT): o marcador de fim agora é
      aleatório POR RUN (`RAND = date +%s%3N$RANDOM`) e o comando injetado escreve
      `echo "ESPELHO""-EXIT-<rand>-$?"`. As aspas duplas vazias quebram a sequência
      `ESPELHO-EXIT-` no ECO do comando digitado no pane — a regex
      `ESPELHO-EXIT-<rand>-[0-9]+` (cortesia do wait-output) não casa com o eco; na
      execução o shell concatena as aspas e imprime `ESPELHO-EXIT-<rand>-<código>`.
      O valor aleatório também isola runs antigas/concurrentes no mesmo pane.
      Extração do código passa a usar só o marcador desta run (`${MATCH##*-}`).

   b. **Notify com token**: token lido de `/home/worker/guardian-app/.env`
      (`GUARDIAN_NOTIFY_TOKEN` ou `ADMIN_TOKEN`, primeira encontrada), enviado no
      header `X-Notify-Token` (formato real do Guardian, server.js GUARDIAN-TOAST-TOKEN).
      Sem arquivo ou sem chave → falha tipada `NOTIFY_SEM_TOKEN` e NENHUM POST é
      tentado. O valor do token nunca é impresso em log/JSON (o header vai direto
      no argv do curl; a saída é só o status).

   c. **Streamer filtrado com cores**: nova função interna `espelho__filtro`
      (subcomando `espelho.sh --filtro-stream`, stdin→stdout). Destaca APENAS:
      veredito (PASS verde / FAIL vermelho), patches escritos e commits (amarelo),
      provas OK/RESUMO 0 falhas (verde), erros/RESUMO com falhas (vermelho) e
      fala do agente (blocos `Hermes>`). Oculta lixo repetido de terminal
      ("preparing terminal", "$ true 0.0s") e linhas de tool-call corriqueiras.
      `fflush()` por linha (line-buffered). `scripts/espelho-segue.sh` agora roda
      `tail -n 40 -F <log> | espelho.sh --filtro-stream` em vez de `tail` cru.

2. **tests/test_espelho.sh** — ampliado e VERDE (`RESUMO: 0 falhas`):
   - Filtro de stream: 13 asserções herméticas — lixo oculto, relevantes mantidos,
     cores ANSI corretas (32/31/33) verificadas.
   - Falso-match: prova que a regex NÃO casa com o eco do comando (com aspas) e
     CASA com a saída em execução; prova ao vivo no herdr (send-text sem Return
     não dispara wait-output; após Return dispara) é executada quando há
     workspace ativo.
   - Notify: token extraído corretamente do .env; sem chave → vazio; .env
     inexistente → vazio; sem token → `NOTIFY_SEM_TOKEN` sem POST.
   - Fluxo completo (JSON ok:true) roda quando há workspace ativo no herdr.
   - Limitação honesta: neste shell não há workspace herdr ativo (mesma condição
     documentada no ESPELHO-01) — as provas ao vivo foram PULOs declarados, não
     falhas; devem rodar verdes na sessão mission-ops (`test-harness`).

3. **scripts/espelho-segue.sh** — stream do espelho passa pelo filtro do espelho.sh.

## Verificação

- `bash -n` limpo em espelho.sh, espelho-segue.sh e test_espelho.sh (executado, OK).
- Suite: 20 OK + 2 PULO (herdr sem workspace ativo) + `RESUMO: 0 falhas` (executado 12/10).
- Filtro validado contra linhas reais de harness-pane.log (formato `[dd/mm HH:MM:SS BRT]`).
- Comportamento do header X-Notify-Token confirmado em guardian-app/server.js
  (GUARDIAN-TOAST-TOKEN: env GUARDIAN_NOTIFY_TOKEN + header, 401 anônimo caso contrário).

## Regras respeitadas

- Nada em /root ou /opt; nenhum git reset/checkout/stash/clean; nenhum sudo;
  nenhum segredo impresso (token só em argv de curl, nunca em stdout/log);
  nenhuma missão real despachada.

## Commit subject

ESPELHO-02: falso-match curado, notify com token, streamer filtrado com cores

## Nota

Commit feito no branch ativo do worktree: video-estudio-01 (68b361aa); nenhum git checkout realizado.

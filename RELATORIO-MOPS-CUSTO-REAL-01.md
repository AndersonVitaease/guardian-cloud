# RELATORIO-MOPS-CUSTO-REAL-01

Data: 2026-10-12 (BRT). Executor: MECANICO (perfil despachante).

## Objetivo
Fim da estimativa de custo por turnos: custo EXATO por sessao de agente,
lido da fonte proveda `/home/worker/.hermes/state.db` (tabela
`session_model_usage`, `estimated_cost_usd` via provider models API),
reflexo no espelho e na notificacao de pouso.

## Entregas
1. `scripts/custo_sessoes.sh` (NOVO)
   - bash + python3 (sqlite3 stdlib) abrindo o db em `mode=ro` via URI —
     leitura SOMENTE-LEITURA, nunca escreve.
   - `--data AAAA-MM-DD` (default: hoje BRT, via `TZ=America/Sao_Paulo date`)
     -> JSON de 1 linha deterministico:
     `{"ok":true,"data":"...","sessoes":[{id,calls,tokens_in,tokens_out,cache,custo_usd},...],"total_usd":X}`
     filtro por `strftime('%Y-%m-%d', last_seen,'unixepoch','+3 hours')`.
   - `--sessao ID` -> `{"ok":true,"id":...,"calls":...,"tokens_in":...,"tokens_out":...,"cache":...,"custo_usd":...}`
     (soma das linhas da sessao — a mesma sessao pode ter linhas por
     model/task, ex. title_generation).
   - Sessao inexistente -> tipado: `{"ok":false,"error":"CUSTO_SESSAO_AUSENTE","sessao":...}` exit 3.
   - Override de teste: `GUARDIAN_STATE_DB` (respeitado para prova hermetica).
   - Chamado como root com db do worker: tenta direto; so se falhar,
     fallback `sudo -u worker` re-executando o proprio script (unico sudo da tool).
2. `scripts/espelho.sh` (ALTERADO)
   - No pouso: guarda o log do pane em `<ID>.espelho.json.log`, extrai
     `Session: <id>` (o `hermes chat -q` imprime no fim; pega a ULTIMA ocorrencia,
     regex `Session: [0-9]{8}_[0-9]{6}[_:][A-Za-z0-9]+`), consulta o custo real
     via `custo_sessoes.sh --sessao` com retry 6x/2s (o uso pousa no db poucos
     segundos depois do marcador EXIT) e grava no `.espelho.json`:
     campos `session_id` e `custo_usd` (null se indisponivel).
   - `espelho__notificar` agora recebe o custo real e manda `custoUsd` NUMERICO
     no POST `/api/notify` (antes: sempre null). Sem custo -> null (comportamento
     anterior preservado). `GUARDIAN_PORT` respeitado (provas).
   - Novo subcomando `--registrar-custo <ID> <log-do-pane> <espelho-json>`:
     o mesmo caminho do pouso, testavel hermeticamente (sem herdr).
   - JSON final do pouso ganha `session_id` e `custo_usd`.
3. `scripts/notifica_pouso.sh` (ALTERADO)
   - `notifica_pouso.sh --espelho-json <arquivo> MISSIONID VEREDITO - MS [LINK] [TITULO]`:
     com CUSTO_USD = `-`, o custo e lido do campo `custo_usd` do json do
     espelho (REAL, nao estimado). Json sem custo -> aviso `CUSTO_AUSENTE`
     no stderr e POST com `custoUsd: null`. Numerico continua aceito como antes.
4. Prova hermetica: `prova-CUSTO-REAL-01.py` (NOVA)
   - tempdir com `state.db` FAKE (schema minimo de `session_model_usage`,
     2 sessoes; sessao A com 2 linhas somando 0.003176) via `GUARDIAN_STATE_DB`;
   - total do dia correto (0.023676) e 2 sessoes na lista; JSON 1 linha;
   - custo exato da sessao A por `--sessao`;
   - sessao inexistente -> `CUSTO_SESSAO_AUSENTE` tipado (exit 3);
   - espelho: log com `Session: 20261012_999999_abc` -> json ganha
     `custo_usd: 0.003176` e `session_id`; log SEM Session -> `custo_usd: null`;
   - notifica_pouso lendo `-` do json -> POST capturado em servidor HTTP local
     com `custoUsd: 0.003176` REAL; json sem custo -> `custoUsd: null` +
     `CUSTO_AUSENTE`;
   - leitura RO provada: mtime do db fake inalterado.
   - RESULTADO: `RESUMO: 0 falhas` — marcador **CUSTO-REAL-01-OK**.

## Prova no db REAL (worker, 2026-10-12 BRT)
- `custo_sessoes.sh --data 2026-10-12` -> 24 sessoes, total **US$0.629486**.
- Sessao `20261012_011859_841564` -> US$0.003176 (4 calls; bate com a leitura
  de referencia do supervisor sobre a mesma fonte).
- Maior custo do dia: sessao `20261012_033926_9a1be3` — US$0.222756 (96 calls).

## Decisoes de bordo
- Filtro por data usa `last_seen` (em BRT, UTC-3 fixo — Brasil sem horario de verao).
- Custos arredondados a 6 casas na saida (somas exatas do db).
- Retry do custo no pouso: 6 tentativas x 2s (12s) — cobre o lag do db sem
  atrasar o pouso em caso real de ausencia.
- `chmod +x` nos tres scripts (nao eram executaveis; prova os chama direto).

## Verificacoes
- `bash -n` limpo nos 3 scripts alterados/criados.
- Prova hermetica: RESUMO: 0 falhas (12 checks OK).
- Prova no db real: JSONs validos, rc=0.
- Regras respeitadas: sem git reset/checkout/stash/clean; sudo apenas no
  fallback da tool; nada escrito em /root ou /opt.

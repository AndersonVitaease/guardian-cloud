# RELATORIO-MISSAO-FECHAR-TIMEOUT-01

Data: 12/10/2026, 11:00 BRT · Papel: MECANICO · Repo: harness-s2 · Execucao hermetica (sem restart de servicos reais, sem despacho)

## 1. Diagnostico (por que o --apply pendurou 58min)

O incidente de 11/09 ~09:07 BRT: `fechar_missao.sh` (ExecStopPost) ficou 58min
pendurado pos-merge num loop sem fim, sem evidencia. Causa raiz confirmada por
leitura do codigo:

- `step()` rodava cada comando **sem nenhum teto de tempo** e **sem resultado
  tipado** — so linhas OK/FAIL no log apos o comando TERMINAR. Se o comando nao
  terminasse, o fecho inteiro pendurava para sempre (exatamente o roadmap:
  "o loop podia rodar para sempre sem evidencia").
- O passo `tab_reap --apply` e o mais exposto: `tab_reap.sh` chama
  `herdr tab list` / `herdr tab close` via command substitution e
  `subprocess.run(...)` **sem timeout interno** (linhas 32/77 e 86 do
  tab_reap.sh) — um herdr bloqueado = penduracao infinita do fecho.
- `vigia_chat.sh` ja protegia o curl com `--max-time 60`, mas o resto do
  pipeline dele (resolucao de sessao etc.) tambem nao tinha teto externo.
- `ledger_missao.py fechar` pode demorar em `_procurar_aba` (espera 20s) e
  `herdr tab close` sem timeout interno — mesmo risco, menor escala.

## 2. Entrega 1 — timeout por step + resultado tipado

`scripts/fechar_missao.sh` reescrito:

- Todo step (`ledger_fechar`, `mirror_fechar`, `tab_reap`, `vigia_chat`) roda
  em sessao propria (`setsid`) vigiada por watchdog: ao estourar
  `FECHAR_STEP_TIMEOUT` (default **240s**, override por env; saneado para
  inteiro >= 1), o grupo leva TERM e, apos `FECHAR_KILL_WAIT` (default 10s),
  KILL no grupo inteiro (mata netos, nao so o filho direto).
- Resultado tipado por step em `/tmp/fechar_missao-{id}.steps.json`:
  `{id, fecho, ok, status: ok|falha_parcial|timeout_step, timeout_step_s,
  inicio, fim, duracao_s, abortado_timeout,
  steps: [{step, cmd, status: OK|FALHA|TIMEOUT_STEP, rc, timeout_excedido,
  tentativas, duracao_s}], steps_pulados: [...], log}`.
- Retentativas: falha comum mantem as 2 tentativas do comportamento legado
  (DESP-FECHO-ROBUSTO-01); **timeout NAO tem retry** (retry replicaria o
  pendurado).
- Comportamento preservado: fail-open do fecho (falha comum segue `exit 0`,
  ok:false fica no JSON); idempotente; comandos reais inalterados.
- Prova hermetica via `FECHAR_FAKE=<dir>`: cada step roda `<dir>/<step>.sh` se
  executavel (sem eval); sem a variavel, comandos reais de producao.
- Logs: linhas `TIMEOUT_STEP <nome> timeout=Ns dur=Ns (abortado, sem retry)`
  em `/tmp/fechar_missao-{id}.log`.

## 3. Entrega 2 — timeout aborta, sem loop infinito

- Step que estoura timeout: tipado `TIMEOUT_STEP` (`timeout_excedido: true`),
  marca `ABORT=1` e **nao retrya**; steps seguintes ficam `PULADO_TIMEOUT`
  (listados em `steps_pulados`).
- Fecho aborta com `ok:false`, `status:"timeout_step"` e **exit 2** tipado
  (`0 = ok | falha_parcial fail-open`, `2 = timeout_step`). Sinais INT/TERM
  tambem resultam em JSON tipado + exit 2. Nao existe mais caminho sem fim.

## 4. Entrega 3 — prova hermetica (`scripts/prova-fechar-timeout-01.sh`)

Fixture fake de `vigia_chat` dorme 1200s (>> timeout 3s). Execucao real de
12/10/2026 10:59:53-56 BRT:

- Cenario A: `FECHAR_STEP_TIMEOUT=3` → step tipado `TIMEOUT_STEP` rc=143,
  fecho termina em **3s** com exit 2 e `steps_pulados: []` (todos os steps
  anteriores ja tinham rodado OK). Antes: penduraria 1200s+ (na pratica,
  para sempre). Sem processo residual vivo.
- Cenario B: falha rapida rc=7 → tipado `FALHA`, 2 tentativas,
  `timeout_excedido: false`, fail-open exit 0, `falha_parcial`.
- Marcador `FECHAR-TIMEOUT-OK`; ultima linha **`RESUMO: 0 falhas`**; exit 0.

Smoke do caminho REAL (mesmo dia 11:00:30 BRT, `HERDR_BIN=/bin/false`,
`MISSION_STATE_DIR` isolado em /tmp, teto 10s): os 4 comandos de producao
rodaram tipados em <1s — `ledger_fechar` FALHA rc=1 (LEDGER_AUSENTE) x2,
`mirror_fechar`/`tab_reap`/`vigia_chat` OK, `falha_parcial`, exit 0, JSON
completo. Escrita isolada em /tmp (nada em /root ou /opt).

## 5. Entrega 4 — artefatos

- `scripts/fechar_missao.sh` (reescrito, timeout por step + JSON tipado)
- `scripts/prova-fechar-timeout-01.sh` (NOVO, prova hermetica 2 cenarios)
- `RELATORIO-MISSAO-FECHAR-TIMEOUT-01.md` (este arquivo)
- Commit: `MISSAO-FECHAR-TIMEOUT-01: timeout por step no fecho, fim do loop morto`

## 6. Nao alterado / limitacoes

- `tab_reap.sh`, `vigia_chat.sh`, `ledger_missao.py`, `fechar_mirror.py`,
  `reconciliar_resumos.py` e o ExecStopPost em `despachar_missao.py` ficaram
  intocados — o teto agora e garantido pelo watchdog externo no wrapper, que
  cobre inclusive o `herdr` sem timeout interno.
- `reconciliar_resumos.py` trata rc!=0 como erro tipado; com exit 2 de timeout
  o fecho reaberto continua reexecutavel na proxima passada (fail-open da
  reconciliacao preservado).
- Limites: watchdog resolve o prazo com sono de 1s (precisao +-1s); o KILL
  final e do grupo da sessao — processos que escaparem do grupo (daemonizados
  com duplo fork) nao sao alcancados (nenhum step atual faz isso).

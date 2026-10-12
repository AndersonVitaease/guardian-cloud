# RELATÓRIO — GB-STREAM-CRU-01

## Diagnóstico
O espelho do despacho nativo (`scripts/espelho-segue.sh`) tailava só o `harness-pane.log` (trail estruturado do runner: "turno 5 | Write | 0ms | $0.00 | ok | path"). O operator queria de volta o TRANSCRIPT CRU do agente (fala + "preparing <tool>..." + resultado curto), como os espelhos antigos `/tmp/ag-*/sessao.log`.

No despacho nativo o transcript cru da missão é o `harness-trail.jsonl` do run dir (`<BASE>/tentativa-N/run-*/harness-trail.jsonl`), jsonl estruturado com eventos `llm` (fala/stop do agente) e tool calls (`input`, `custo_usd`, `ok`) — confirmado no run dir real de GB-UCME-FECHO-01.

## Entrega
- `scripts/_trail_cru.py` (novo): converte trail jsonl → texto puro legível, uma ação por linha, formato do espelho antigo: `[ts] agente turno N: stop=... bytes=...` para eventos llm e `[ts] preparing <Tool>... <arg curto> | ok|erro | $custo` para tool calls. Ruído do runner (`_inicio`, `_config`, `_stop_check`, `_vagueio_prompt`) é descartado. Fail-open: linha jsonl corrompida é ignorada, nunca erro. Tradução PT-BR fica client-side (tabela existente), nada traduzido aqui.
- `scripts/espelho-segue.sh` (alterado): além do tail do pane log (trilha estruturada, mantida intacta — nada apagado), faz `tail -n 40 -F harness-trail.jsonl | python3 _trail_cru.py` no mesmo run dir. Transcript ausente = trilha crua simplesmente não emite (fail-open, sem erro no despacho).
- `scripts/prova-STREAM-CRU-01.py` (novo): prova hermética.

## Prova hermética (tempdir, sem rede, sem tokens) — 9/9 PASS
Run dir fake com pane.log estruturado + trail jsonl fake:
- (a) tail exposto ao streamer vem do transcript cru: saída contém `preparing Bash... ls scripts | ok | $0.0000` e `preparing Write... a.md`, fala do agente presente, uma ação por linha, exit 0.
- (b) pane log continua inteiro: bytes preservados byte a byte após a prova.
- (c) transcript ausente não derruba nada: conversor sobre stdin vazio sai 0 sem saída; `espelho-segue.sh` roda e segue vivo sem trail, e emite "acompanhando" quando o trail reaparece.

```
PASS cru-saida-tem-preparing / cru-saida-tem-fala-agente / cru-uma-acao-por-linha / cru-exit0
PASS pane-inteiro
PASS sem-trail-exit0-sem-saida / segue-vivo-sem-trail / segue-acompanha
RESUMO: 0 falhas
```

## Escopo
Só scripts de espelho/despacho do harness-s2. `server.js`/`app.js` intocados (GB-SALA-LIVE-04). Sem git reset/checkout/stash/clean/push.
# RELATORIO GB-CARDS-SPOOL-01

## Entrega
- `scripts/ledger_missao.py` (funcao `fechar`, ~linha 196): apos gravar o ledger fechado, emite evento `mission_end` no spool do guardian:
  - JSONL append: `{"ts": <epoch>, "kind": "mission_end", "missionId": <id>, "data": {"veredito", "custo_usd", "budget_usd", "turnos", "fonte": "harness"}}`
  - Caminho: env `GUARDIAN_SPOOL_PATH`, default spool.jsonl do mission-events (mesmo default do server.js).
  - Append-only, fail-open: spool ausente/inacessivel => pula sem crash, loga em stderr. Nunca trunca nem reescreve linhas.
- `scripts/prova-GB-CARDS-SPOOL-01.sh`: prova hermetica em tempdir com spool fake via env.

## Prova
- `bash scripts/prova-GB-CARDS-SPOOL-01.sh` => fecho de missao fake grava `mission_end` tipado (veredito PASS, custo 0.42, fonte harness) no spool; spool ausente => fail-open com stderr; RESUMO: 0 falhas.
- `python3 -m py_compile scripts/ledger_missao.py` => OK.

## Stops
1. prova => RESUMO: 0 falhas (exit 0)
2. py_compile => OK
3. RELATORIO-GB-CARDS-SPOOL-01.md => este arquivo
4. git log -1 => "GB-CARDS-SPOOL-01: fecho e despacho emitem mission_start/end no spool do guardian" (commit f947e308)

## Nao tocado
server.js, app.js, despachar_missao.py, /opt, /root — conforme restricoes.

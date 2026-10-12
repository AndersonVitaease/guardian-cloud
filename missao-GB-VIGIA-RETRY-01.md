# MISSÃO GB-VIGIA-RETRY-01

Fonte: ROADMAP.md fila do operador (autorizada 12/10 20:30 BRT). Finding do dia:
aviso de nascimento falhou 2× com ROTA_OFFLINE (TimeoutError no gateway 8642)
— falha silenciosa demais para um canal de segurança.

## MAPA (medido 12/10)

- /home/worker/harness-s2/scripts/despachar_missao.py:250-264 — bloco
  "VIGIA-NASCER-03": UMA tentativa, subprocess timeout=8, fail-open.

## SPEC

- Extrair o bloco para função `notify_nascimento(texto, tentativas=4, script=None)`
  no mesmo arquivo: retry com backoff 2s/5s/15s entre tentativas (subprocess
  timeout=8 por tentativa). Retorna ("ok"|"falho", detalhe).
- Mantém fail-open: esgotadas as tentativas, despacho segue (aviso=falho, stderr
  tipado 'aviso_nascimento falhou (4 tentativas): <detalhe>') — comportamento
  de contorno inalterado.
- Chamada existente passa a usar a função; saída JSON do despacho inalterada.
- Sem mudanças em outros arquivos.

## PROVA (prova-vigia-retry-01.py no worktree)

Monkeypatch de subprocess.run via injeção: 2 primeiras chamadas levantam
TimeoutError, 3ª retorna stdout b"OK" → função retorna "ok" e foram feitas 3
chamadas. E: 4 falhas → retorna "falho" com detalhe e 4 chamadas. Saída:
GB-VIGIA-RETRY-01-PROVA-OK. NÃO usar rede real.

## RELATORIO

RELATORIO-GB-VIGIA-RETRY-01.md.

## harness-stop

```harness-stop
cmd cd /home/worker/wt-GB-VIGIA-RETRY-01 && grep -q -F 'notify_nascimento' scripts/despachar_missao.py && grep -q -F 'backoff' scripts/despachar_missao.py
cmd cd /home/worker/wt-GB-VIGIA-RETRY-01 && python3 prova-vigia-retry-01.py 2>&1 | grep -q -F 'GB-VIGIA-RETRY-01-PROVA-OK'
cmd cd /home/worker/wt-GB-VIGIA-RETRY-01 && test -s RELATORIO-GB-VIGIA-RETRY-01.md
cmd cd /home/worker/wt-GB-VIGIA-RETRY-01 && test "$(git log -1 --format=%s)" = "GB-VIGIA-RETRY-01: aviso de nascimento com retry e backoff (4 tentativas, fail-open mantido)"
cmd cd /home/worker/wt-GB-VIGIA-RETRY-01 && test -z "$(git status --porcelain)"
```

REGRAS: proibido git reset/checkout/stash/clean; sudo só nos stops de prova python.

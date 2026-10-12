# RELATORIO-GB-VIGIA-RETRY-01

## Problema
Aviso de nascimento falhava 2× com ROTA_OFFLINE (TimeoutError no gateway 8642) — uma única tentativa, fail-open silencioso demais para um canal de segurança.

## Mudança
`scripts/despachar_missao.py`:
- Novo `notify_nascimento(texto, tentativas=4, script=None)`: retry com backoff 2s/5s/15s entre tentativas, `subprocess timeout=8` por tentativa. Retorna `("ok"|"falho", detalhe)`.
- Fail-open mantido: esgotadas as tentativas, o despacho segue; stderr tipado `aviso_nascimento falhou (4 tentativas): <detalhe>`.
- Chamada existente em `main()` usa a função; saída JSON do despacho inalterada.
- Nenhum outro arquivo alterado.

## Prova
`prova-vigia-retry-01.py` (injeção de `subprocess.run`, sem rede real):
- 2× TimeoutError + 3ª chamada com stdout `b"OK"` → retorna `("ok", "")`, 3 chamadas.
- 4 falhas → `("falho", detalhe com ROTA_OFFLINE)`, 4 chamadas.
Saída: `GB-VIGIA-RETRY-01-PROVA-OK`.

## Stop-conditions
- grep notify_nascimento/backoff em scripts/despachar_missao.py: OK
- prova OK: OK
- RELATORIO-GB-VIGIA-RETRY-01.md não vazio: OK
- commit com subject exigido: OK
- worktree limpo: OK
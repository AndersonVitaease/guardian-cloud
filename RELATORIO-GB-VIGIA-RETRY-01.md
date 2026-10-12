# RELATORIO GB-VIGIA-RETRY-01

## Contexto
Aviso de nascimento falhava 2× com ROTA_OFFLINE (TimeoutError no gateway 8642) sem retry — canal de segurança com falha silenciosa.

## Mudança
- `scripts/despachar_missao.py`: nova função `notify_nascimento(texto, tentativas=4, script=None)` — retry com backoff 2s/5s/15s entre tentativas, `subprocess timeout=8` por tentativa, retorna `("ok"|"falho", detalhe)`.
- Chamada existente em `main()` usa a função; esgotadas as tentativas, stderr tipado `aviso_nascimento falhou (4 tentativas): <detalhe>` e despacho segue (fail-open mantido). Saída JSON do despacho inalterada.
- Sem mudanças em outros arquivos.

## Prova
`prova-vigia-retry-01.py` (injeção de `subprocess.run`, sem rede real):
- 2 TimeoutError + 1 sucesso → "ok", 3 chamadas.
- 4 falhas → "falho" com detalhe, 4 chamadas.
Saída: `GB-VIGIA-RETRY-01-PROVA-OK`.

## Veredito
OK — stop-conditions cumpridas.
# MISSÃO SEC-SCAN-01 — varredura de segredos e vulnerabilidades do harness (scanner determinístico)

Fonte: ROADMAP.md linha 386.

operatorOrder: scan de segurança autorizado pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Alvo: o repo inteiro do worktree (harness-s2: harness.py, mission_run.py, scripts/, tests/, tools-bash instaladas não estão aqui — só o que o repo tem). Escopo do worker = SEMPRE o worktree próprio; NUNCA /root, /opt, /tmp de outros.
- Padrão de forma: scanners como código unittest stdlib; stops sem sudo/cat/head/ls/grep -A/;/`; python como worker.

## OBJETIVO
1. **`scripts/sec_scan.py`** (determinístico, roda como worker, exit 0 sempre, JSON por linha):
   - SEGREDOS: padrões regex sobre todos os arquivos do repo (git ls-files): chaves privadas (BEGIN.*PRIVATE KEY), AWS (AKIA...), Google/OpenAI/Anthropic/Router API keys (sk-, AIza, gsk_, OR_+40hex etc.), bearer/tokens hardcoded, senhas em assign (passwd|senha|password\s*=\s*['"]...), webhook URLs com token (hooks.slack.com, discord.com/api/webhooks), jwt literal (eyJ...). Cada hit: {arquivo, linha, tipo, preview_MASCARADO (só 4 primeiros chars + ...)}.
   - FALSOS-POSITIVOS: ignora tests/ com fixtures obviamente fake (marcadas 'fake|fixture|exemplo'), placeholders (xxx, <token>, YOUR_).
   - VULNS: `eval(`/`exec(` em python fora de test; `subprocess` com `shell=True`; bash tools com variável não-quotada em contexto de comando (`$VAR` sem aspas em linha com rm/mv/cp/kill); `pickle.load`; `os.system`; uso de `sudo` dentro de scripts do repo; permissão de arquivo executável com mundo-escrevível (os.stat, 0o002).
2. **Saída em 2 camadas**: (a) `sec_scan.py` imprime hits na tela; (b) **RELATORIO-SEC-SCAN-01.md**: tabela de achados por severidade (CRITICO/ALTO/MEDIO/BAIXO), com veredito honesto: CRITICO = segredo real commitado ou injeção explorável; cada CRITICO/ALTO vira item de roadmap sugerido (texto pronto p/ roadmap_note.sh, mas NÃO roda o roadmap — reporta).
3. O worker NÃO remove nem edita segredo/código achado — apenas reporta (decisão é do operador).

## TAREFA
1. Escrever `scripts/sec_scan.py` + `tests/test_sec_scan.py` (unittest: fixtures de arquivo com segredo fake cobrindo cada regex; arquivo limpo → 0 hits; falso-positivo em tests/ ignorado; preview mascarado).
2. Rodar o scanner no worktree e escrever o RELATORIO com os achados reais.
3. Commit `SEC-SCAN-01: sec_scan + relatorio` e `SEC-SCAN-01: relatorio` (na raiz: RELATORIO-SEC-SCAN-01.md).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-SEC-SCAN-01 && git log -1 --format=%s | grep -q -F "SEC-SCAN-01: sec_scan"
cmd cd /home/worker/wt-SEC-SCAN-01 && /usr/bin/python3 -m py_compile scripts/sec_scan.py
cmd cd /home/worker/wt-SEC-SCAN-01 && /usr/bin/python3 -m unittest tests.test_sec_scan -v 2>&1 | tail -1
cmd cd /home/worker/wt-SEC-SCAN-01 && /usr/bin/python3 scripts/sec_scan.py > /dev/null && echo SCAN-OK
cmd cd /home/worker/wt-SEC-SCAN-01 && git ls-files --error-unmatch scripts/sec_scan.py && git ls-files --error-unmatch RELATORIO-SEC-SCAN-01.md
```

PROIBIDO: git reset/checkout/stash/clean; sair do worktree; escanear /root, /opt, /home/worker fora do worktree; editar código alheio para "consertar" achado; commitar segredo nenhum (se achar segredo real, o preview no commit/relatorio vem MASCARADO).

# MISSÃO VIGIA-NASCER-04 — NameError no gatilho de nascimento (prova real do supervisor)

Prova real: o supervisor despachou 2 missões (GB-COTA-01, DESP-FECHO-BASE-01) e o aviso de nascimento NÃO saiu — stderr do despachar mostrou `aviso_nascimento falhou: NameError("name 'budget' is not defined")`. O fail-open funcionou (despacho ok), mas o gatilho está quebrado na integração real: a prova do worker testou o helper isolado, não o caminho do despachar. Worktree real: `/home/worker/wt-VIGIA-NASCER-01` (branch `rd-vigia-nascer-01`).

## Problema
Em `despachar_missao.py`, o trecho do aviso de nascimento (procure `aviso_nascimento` / `notify`) referencia a variável `budget` que não existe naquele escopo (o despachar usa outro nome — veja os parâmetros da função principal: budget/turns/etc.).

## Entregas
1. Corrigir o NameError: a mensagem do aviso deve usar a variável de budget REAL do escopo (ou capturá-la). Sem mudar o formato do texto: `🛰️ NASCEU: missão <ID> em voo — aba <tab>, seed <seed>, budget <B> US$`.
2. Teste de integração novo: fixture que chama a função de despacho com o notify apontando para server de mentira (socket em tempdir) e afirma que o POST chega COM o budget correto no texto. O bug atual passou porque só o helper tinha teste — o teste novo exercita o caminho do despachar.
3. Prova E2E: `prova-VIGIA-NASCER-04.py` (server de mentira + execução do caminho real) com marcador `VIGIA-NASCER-04-PROVA-OK` no .out >200 bytes.
4. NADA mais: não mexa no helper existente além do necessário, nem nas outras peças do vigia.

## Regras
- Commits `VIGIA-NASCER-04:`. Sem sudo. Leitura por code_slice/grep -n. Sem git reset/checkout/stash/clean. Sem internet.

## Stops
```harness-stop
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 -m pytest tests/test_notify_hermes.py tests/test_despacho_nascimento.py -q
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 scripts/prova-VIGIA-NASCER-04.py
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test $(stat -c%s scripts/prova-VIGIA-NASCER-04.out 2>/dev/null || echo 0) -gt 200
cmd cd /home/worker/wt-VIGIA-NASCER-01 && git log --format=%s -1 | grep -q -F 'VIGIA-NASCER-04'
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test -z "$(git status -s -- .)"
```

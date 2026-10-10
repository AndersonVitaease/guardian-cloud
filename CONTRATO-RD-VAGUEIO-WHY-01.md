# MISSÃO RD-VAGUEIO-WHY-01 — tool vagueio_why <mid> (classifica causa do vagueio a partir do trail; base H3/H4)

## CONTEXTO MEDIDO (confiado, não investigue de novo)
- Causas medidas em runs reais: ambiente (leituras recusadas: LEITURA_RECUSADA / LEITURA_MECANICA_RECUSADA — cat/head/ls/grep -A), loop_leitura (mesmos arquivos relidos em repetição; 57% de leituras repetidas entre tentativas), stop_inviável (0 stops parseados SEM_STOPS, stop VACUO tipo `test -f`, stop com `;`/`grep -A`), cwd (worktree/caminho inexistente, BAD_ARGS, STOP_RELATIVO).
- Fontes de dados já provadas: ledger `<state_dir>/<missionId>.json` + trail `events.jsonl` / `<missionId>.events.tail.jsonl` no MESMO state_dir (padrão de tools-bash/trail_tail.sh:24-40); heurísticas de vagueio já existem em scripts/detector_vagueio.py e scripts/detector_loop.py (harness roda com --vagueio on --escada on) — REUTILIZE as heurísticas/conceitos, não duplicar módulo.
- Resumo por tentativa fica em `/tmp/resumo-<ID>.json` (pode não existir mais; trate ausente).
- Estilo de tool: JSON 1 linha, exit 0 sempre, falha tipada, `untrusted:true`/`notice`; wrapper AUTÔNOMO (emit/fail inline, sem source de _lib.sh — padrão entrega_verify.sh).

## MAPA
- tools-bash/vagueio_why.sh — ARQUIVO NOVO (Write inteiro; wrapper autônomo com python3 inline).
- tests/test_vagueio_why.py — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest), fixtures de trail em tmpdir.

## COMPORTAMENTO EXIGIDO
1. `vagueio_why.sh <missionId>` (1 arg, [A-Za-z0-9._-] até 64; senão `{"ok":false,"error":"INVALID_MISSION_ID"}`). State dir: MESMA resolução de `tb_state_dir` em tools-bash/_lib.sh:16 (env `MISSION_STATE_DIR` vence; fallbacks iguais aos das outras tools; NUNCA default vazio).
2. Sem ledger → `{"ok":false,"error":"LEDGER_NOT_FOUND"}`. Sem trail nenhuma → `{"ok":true,"causa":"sem_trail","evidencias":[]}`.
3. Lê o trail e devolve `causa` dominante ∈ {ambiente, loop_leitura, stop_inviavel, cwd, sem_vagueio} + `evidencias` (até 10, cada uma com trecho/contagem) + `turnos`, `veredito` (aceitar `veredito` OU `verdict` do ledger), `custo_usd`.
4. Heurística (em ordem de dominância por contagem de evidências): contagem de LEITURA_*_RECUSADA no trail → ambiente; mesmo arquivo lido ≥3x (extrai caminhos de eventos de leitura) → loop_leitura; 0 stops parseados / VACUO / stops com test -f citados no ledger ou resumo → stop_inviavel; BAD_ARGS / caminho inexistente no cwd → cwd. Nada marcado → sem_vagueio.
5. NUNCA escreve fora do worktree; tool somente leitura.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva `tests/test_vagueio_why.py` (Write inteiro): fixtures de trail tmpdir cobrindo cada causa (ambiente, loop_leitura, stop_inviavel, cwd, sem_vagueio) + LEDGER_NOT_FOUND + INVALID_MISSION_ID + ledger com `verdict` (grafia alternativa) + JSON 1 linha com untrusted/notice.
2. `python3 -m pytest tests/test_vagueio_why.py -q` VERMELHO no baseline. Commit do aceite vermelho com o ID no assunto (git add só do teste).
3. Implemente `tools-bash/vagueio_why.sh` (Write inteiro); verifique chamando da RAIZ do worktree.
4. Testes verdes + `bash -n tools-bash/vagueio_why.sh`.
5. Commit do código (assunto com o ID) e `RELATORIO-RD-VAGUEIO-WHY-01.md` na raiz (2 linhas, citando a causa classificada no smoke real).

## REGRAS
- Provas python sempre como worker (você já é worker). Sem sleep, sem sudo direto, sem escrever fora do worktree. Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh; sem ';' nos stops.
- `git add` só dos arquivos da missão. Sem `git reset/checkout/stash/clean`.

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd bash -n tools-bash/vagueio_why.sh
cmd python3 -m pytest tests/test_vagueio_why.py -q
cmd MISSION_STATE_DIR=/opt/mission-events/mission-state-mirror bash tools-bash/vagueio_why.sh RD-SEC-01 | grep -q -F '"tool":"vagueio_why"'
cmd git log --format=%s | grep -q -F RD-VAGUEIO-WHY-01
cmd grep -q -F RD-VAGUEIO-WHY-01 RELATORIO-RD-VAGUEIO-WHY-01.md
```
O stop 3 é o smoke E2E REAL (dados reais do espelho, somente leitura): rode antes no baseline e anote no relatório a causa classificada para RD-SEC-01 (missionId real com trail no espelho; ledger com `veredito`, trail `<ID>.events.tail.jsonl` — já conferidos pelo despachante).

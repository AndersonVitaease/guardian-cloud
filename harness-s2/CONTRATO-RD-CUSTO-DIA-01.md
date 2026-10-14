# MISSÃO RD-CUSTO-DIA-01 — tool custo_dia.sh (soma custo/turnos/PASS/FAIL do dia a partir de runs_historico.sh)

## CONTEXTO MEDIDO (confiado, não investigue de novo)
- `tools-bash/runs_historico.sh` (--since-hours H [N]) já devolve JSON 1 linha: `{"ok":true,"tool":"runs_historico","count":N,"runs":[{missionId,tentativas,verdict,motivo,turnos,cost_usd,stops,finished_at,commit,repo}]}` ordenado por finished_at desc; lê `<raiz>/runs/<ID>/.../harness-pane.log` sob RUNS_ROOTS (default /home/worker).
- CUIDADO: a grafia do veredito no runs_historico é `verdict` (o ledger usa `veredito`) — leia a grafia REAL da saída, `get(a) or get(b)` quando ler JSON de outro módulo.
- ATENÇÃO: `scripts/custo_dia.py` (por trails) JÁ EXISTE com testes (`tests/test_custo_dia.py`) — NÃO o altere nem o renomeie; a nova tool é outra fonte (runs_historico, com vereditos), então o arquivo de teste novo NÃO pode se chamar test_custo_dia.py.
- Estilo de tool: JSON 1 linha, exit 0 sempre, falha tipada, `untrusted:true`/`notice`; wrapper AUTÔNOMO (emit/fail inline, sem source de _lib.sh).

## MAPA
- tools-bash/custo_dia.sh — ARQUIVO NOVO (Write inteiro; wrapper autônomo com python3 inline).
- tests/test_custo_dia_runs.py — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest), com FAKE do runs_historico (fixture JSON) — nenhum teste depende do disco real.

## COMPORTAMENTO EXIGIDO
1. `custo_dia.sh [--since-hours H=24]`: chama `bash "<dirname do próprio script>/runs_historico.sh" --since-hours <H> 100` (caminho resolvido pelo dirname — verificado chamando da RAIZ do worktree); override do comando fonte por env `CUSTO_RUNS_HISTORICO_CMD` (NUNCA default vazio; default = o bash acima) para os fakes nos testes.
2. Agrega por DIA de Brasília (America/Sao_Paulo) a partir de `finished_at`: para o dia corrente, `{"ok":true,"tool":"custo_dia","dia":"YYYY-MM-DD","custo_usd_total":F,"turnos_total":N,"pass":N,"fail":N,"outros":N,"runs":N,"por_missao":[{missionId,verdict,cost_usd,turnos}]}` (por_missao até 20, mais caros primeiro).
3. `verdict` "PASS" conta em `pass`, "FAIL" em `fail`, outro/ausente em `outros`. `cost_usd` ausente = 0 (não quebra a soma). runs_historico com ok:false → repasse `{"ok":false,"tool":"custo_dia","error":"FONTE_INDISPONIVEL","detalhe":...}`.
4. Tool somente leitura; nada de sleep; sem sudo.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva `tests/test_custo_dia_runs.py` (Write inteiro): fixture JSON de runs_historico via `CUSTO_RUNS_HISTORICO_CMD`; cobre agregação do dia BRT (custo soma, turnos soma, PASS/FAIL/outros contados); cost_usd ausente não quebra; fonte ok:false → FONTE_INDISPONIVEL; JSON 1 linha com untrusted/notice e exit 0; fuso: finished_at em UTC virando dia diferente em BRT.
2. `python3 -m pytest tests/test_custo_dia_runs.py -q` VERMELHO no baseline. Commit do aceite vermelho com o ID no assunto (git add só do teste).
3. Implemente `tools-bash/custo_dia.sh` (Write inteiro).
4. Testes verdes + `bash -n tools-bash/custo_dia.sh`.
5. Commit do código (assunto com o ID) e `RELATORIO-RD-CUSTO-DIA-01.md` na raiz (2 linhas, citando os números do smoke real).

## REGRAS
- Provas python sempre como worker (você já é worker). Sem sleep, sem sudo direto, sem escrever fora do worktree. Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh; sem ';' nos stops.
- `git add` só dos arquivos da missão. Sem `git reset/checkout/stash/clean`.

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd bash -n tools-bash/custo_dia.sh
cmd python3 -m pytest tests/test_custo_dia_runs.py -q
cmd bash tools-bash/custo_dia.sh | grep -q -F '"tool":"custo_dia"'
cmd git log --format=%s | grep -q -F RD-CUSTO-DIA-01
cmd grep -q -F RD-CUSTO-DIA-01 RELATORIO-RD-CUSTO-DIA-01.md
```
O stop 3 é o smoke E2E REAL (dados reais de runs_historico, somente leitura): rode antes no baseline; se o baseline já emitir ok:false por falta de runs no disco, anote o porquê no relatório.

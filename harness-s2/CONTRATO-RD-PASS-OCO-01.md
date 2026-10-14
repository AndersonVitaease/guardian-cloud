# MISSÃO RD-PASS-OCO-01 — ligar entrega_verify ao fechamento da run (PASS sem entrega na raiz = veredito rebaixado)

## CONTEXTO MEDIDO (confiado, não investigue de novo)
- Problema (H1/H6A/H7): runs com veredito PASS mas entrega dentro do run dir ou patch não aplicado na raiz do worktree.
- A tool `tools-bash/entrega_verify.sh` já está instalada e funciona (linha 1-164; lê ledger de `ENTREGA_STATE_DIR`, confere commit com o ID, git status, diff do HEAD).
- O fechamento da run chama `scripts/ledger_missao.py fechar <ID> --resumo /tmp/resumo-<ID>.json` (ExecStopPost injetado pelo despachar_missao.py de produção). O `fechar()` está em scripts/ledger_missao.py:169 (função `fechar(missao_id, resumo_path, state_dir=None, runner=subprocess.run)`) e decide `status = "closed" if veredito == "PASS" else "failed"` nas linhas ~178-183.
- Cuidado com grafias divergentes: resumo pode trazer `veredito` ou `verdict`/`status` (o fechar já usa `resumo.get("veredito") or resumo.get("status")`).

## MAPA
- scripts/ledger_missao.py — EXISTENTE; patch cirúrgico em `fechar()` (cód_slice do trecho exato 160-200 ANTES de qualquer Edit; old_string literal).
- tests/test_ledger_pass_oco.py — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest).

## COMPORTAMENTO EXIGIDO (em `fechar()`)
1. Quando o veredito parseado do resumo for `PASS`, chamar a verificação de entrega ANTES de gravar o fechamento: subprocess `python3 <ENTREGA_VERIFY_PATH> <mission_id>` com env `ENTREGA_STATE_DIR=<mesmo state_dir do ledger>`; caminho da tool por env `ENTREGA_VERIFY_PATH`, default `/home/worker/harness-s2/tools-bash/entrega_verify.sh` (NUNCA default vazio). O runner de subprocess é o parâmetro `runner` já existente (fakes nos testes usam fake runner).
2. Entrega `ok:true` → veredito PASS intacto; gravar campo `entrega` = {"ok": true} no ledger.
3. Entrega `ok:false` (faltando/erro de verificação) → veredito rebaixado para `PASS_OCO`, `status = "failed"`, campo `entrega` = {"ok": false, "faltando": [...], "error": ...} gravado no ledger. O relatório e o fecho da aba continuam normais (fail-open do fecho preservado).
4. Erro de EXECUÇÃO da verificação (subprocess quebra/timeout) → NÃO rebaixa: mantém veredito PASS, grava campo `entrega` = {"ok": null, "aviso": "<erro>"} e segue o fechamento (fail-open).
5. Veredito != PASS → comportamento atual inalterado, sem chamar entrega_verify.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva `tests/test_ledger_pass_oco.py` (Write inteiro; pytest; ledger/state_dir em tmpdir via `state_dir=` e fake `runner`), cobrindo: PASS com entrega ok → closed/entrega ok; PASS com entrega ok:false → veredito PASS_OCO + status failed + campo entrega; PASS com runner que estoura exceção → veredito mantido + aviso; FAIL → sem chamada de entrega_verify; idempotência (ledger já terminal não re-verifica).
2. Rode `python3 -m pytest tests/test_ledger_pass_oco.py -q` — deve estar VERMELHO. Commit do aceite vermelho com o ID no assunto (git add só do teste).
3. Aplique o patch em `scripts/ledger_missao.py` (leia o trecho exato com code_slice imediatamente antes do Edit).
4. `python3 -m pytest tests/test_ledger_pass_oco.py tests/test_ledger_missao.py -q` verde e `python3 -m py_compile scripts/ledger_missao.py`.
5. Commit do código (assunto com o ID) e escreva `RELATORIO-RD-PASS-OCO-01.md` na raiz do worktree (2 linhas).

## REGRAS
- Provas python sempre como worker (você já é worker). Sem sleep, sem sudo direto, sem escrever fora do worktree. Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh; sem ';' nos stops.
- `git add` só dos arquivos da missão. Sem `git reset/checkout/stash/clean`.

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd python3 -m py_compile scripts/ledger_missao.py
cmd python3 -m pytest tests/test_ledger_pass_oco.py -q
cmd grep -q -F PASS_OCO scripts/ledger_missao.py
cmd ENTREGA_STATE_DIR=/opt/mission-events/mission-state-mirror bash tools-bash/entrega_verify.sh H4-JANELA-LEITURA | grep -q -F '"tool":"entrega_verify"'
cmd git log --format=%s | grep -q -F RD-PASS-OCO-01
cmd grep -q -F RD-PASS-OCO-01 RELATORIO-RD-PASS-OCO-01.md
```
O stop 4 é o smoke E2E REAL (tool de produção, dados reais, somente leitura): deve emitir 1 linha JSON com "tool":"entrega_verify" e ok true/false — rode antes no baseline e anote o resultado no relatório.

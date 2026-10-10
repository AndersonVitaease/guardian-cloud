# MISSÃO RUN-CLOSE-01B — correção run_close.sh: resolução de run dir + leitura do autoretry-summary

Fonte: ROADMAP.md linha 373.

operatorOrder: conserto como continuação autorizado pelo operador 10/10.

## CONTEXTO — CONTINUAÇÃO, NÃO RECOMECE

A RUN-CLOSE-01 pousou `run_close.sh` + `test_run_close.sh` (commit a6782c33, merge 534c1a84+ na rd-segue-01). A tool está instalável mas 2 defeitos foram MEDIDOS ao vivo (prova real, 17:1x BRT):

1. `bash run_close.sh RUN-CLOSE-01` (por missionId) devolveu `SEM_RESUMO` embora `/home/worker/wt-RUN-CLOSE-01/runs/RUN-CLOSE-01/autoretry-summary.json` EXISTA (1922 bytes). Causa: o ledger da run aponta `cwd` = run dir INTERNO do auto-retry (`.../runs/RUN-CLOSE-01/tentativa-1/run-<ts>-seed77-<pid>`), e `resumo.json`/`autoretry-summary.json` moram UM NÍVEL ACIMA (no cwd da runs). A tool procura os JSONs só no run_dir recebido.
2. Com caminho direto do cwd (`run_close.sh /home/worker/wt-RUN-CLOSE-01/runs/RUN-CLOSE-01`) respondeu `ok:true` mas `stops:[]`, `turnos:null`, `custo_usd:null` — o código só lê as chaves do `resumo.json` (`veredito/tentativas/turnos/custo_usd/stops`); o `autoretry-summary.json` usa OUTRO schema: `vereditos_por_tentativa`, `motivo` por tentativa, `stop_conditions[].ok`/`id`, custo/turnos acumulados (confira as chaves REAIS do arquivo no worktree antes de editar).

## MAPA PRÉ-DIGERIDO (arquivo:símbolo:LINHA — HEAD atual do worktree wt-RUN-CLOSE-01)

- `run_close.sh` L34-50: bloco "resolução do run_dir" — missionId via `tb_state_dir/<id>.json` campo `cwd` + fallback glob `/home/worker/wt-*/runs/<ID>`. É AQUI que entra a normalização: se o run_dir resolvido contém `/tentativa-N/run-`, SUBA até o ancestral que tem `resumo.json` ou `autoretry-summary.json` (ou procure também um nível acima).
- `run_close.sh` L64-95 (função python embutida): `res = load(run_dir/"resumo.json")`, `aut = load(run_dir/"autoretry-summary.json")` L78-79; `SEM_RESUMO` L81; extração de chaves L88-95. É AQUI que entra o schema do autoretry: se `res` é None e `aut` não-None, derive veredito/tentativas/stops/turnos/custo das chaves reais do `aut` (ex.: último elemento de `vereditos_por_tentativa`, `stop_conditions[]`, custo/turnos acumulados — LEIA O ARQUIVO REAL para os nomes exatos).
- `test_run_close.sh`: teste de comportamento existente — estenda, não reescreva.
- Padrão de forma: `source _lib.sh`, `tb_audit`, `fail()` tipado (L28-29), JSON 1 linha, exit 0 sempre.

## REGRAS

- Leitura: `code_slice.sh`, `grep -n` com pipe; NUNCA `cat`/`head`/`ls` (recusados em 0 ms). Se uma leitura for recusada 2×, use `code_slice.sh <arq> <ini> <fim>` — não improvare variante.
- Edite `run_close.sh` com Edit APÓS ler o trecho exato imediatamente antes (o trecho pode ter mudado); teste estendido com Write/Edit.
- `git add` SÓ de `run_close.sh` e `test_run_close.sh`. Commit cedo com o ID no assunto. NUNCA `git reset/checkout/stash/clean`.
- NÃO escreva em /opt nem /root; entrega fica no worktree (instalação é passo do supervisor).
- pytest com `/usr/bin/python3 -m pytest`; bash com `bash`.

## ENTREGAS

1. `run_close.sh <missionId>` resolve o ledger (tb_state_dir ou glob) e, se o run_dir apontar para um `tentativa-N/run-*` sem resumo, sobe ao nível que tem os JSONs (prova: `bash run_close.sh RUN-CLOSE-01` NO worktree deve devolver `ok:true`, `veredito:"PASS"`, commit_msg com RUN-CLOSE-01).
2. `run_close.sh` preenche `stops`/`turnos`/`custo_usd`/`tentativas` a partir do `autoretry-summary.json` quando o `resumo.json` não existe (chaves REAIS lidas do arquivo, não inventadas).
3. `test_run_close.sh` estendido com os 2 casos acima (fixtures de summary no schema real).
4. Commit `RUN-CLOSE-01B: resolucao run-dir + schema autoretry no run_close` e `RELATORIO-RUN-CLOSE-01B.md` na raiz (2 linhas: o que mudou + prova) + commit `RUN-CLOSE-01B: relatorio`.

```harness-stop
cmd cd /home/worker/wt-RUN-CLOSE-01 && git log -1 --format=%s | grep -q -F "RUN-CLOSE-01B: resolucao run-dir"
cmd cd /home/worker/wt-RUN-CLOSE-01 && bash -n run_close.sh
cmd cd /home/worker/wt-RUN-CLOSE-01 && bash test_run_close.sh
cmd cd /home/worker/wt-RUN-CLOSE-01 && git ls-files --error-unmatch run_close.sh && git -C /home/worker/wt-RUN-CLOSE-01 diff --quiet HEAD -- run_close.sh
cmd cd /home/worker/wt-RUN-CLOSE-01 && git ls-files --error-unmatch RELATORIO-RUN-CLOSE-01B.md
```

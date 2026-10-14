# MISSÃO VIGIA-DEDUPE-01 — fim do vigia emitido 1x por missão

Fonte: ROADMAP.md (vigia de andamento, DESP-VIGIA-01). Worktree real: `/home/worker/wt-VIGIA-DEDUPE-01` (branch `rd-vigia-dedupe-01`).

## Problema (diagnóstico do supervisor, já feito — você executa, não investiga)
O vigia por missão (`scripts/vigia_run.py`, spawnado pelo `despachar_missao.py:163-180`) emite eventos em `/tmp/vigia-<ID>.jsonl`. No dia 11/10 o consumidor do chat reenviou o MESMO aviso de término 3x (HEADLESS-TAB-02C e CICLO-STATUS-01B). Provas no disco:
- `/tmp/vigia-CICLO-STATUS-01B.jsonl` tem eventos `andamento` DUPLICADOS com mesmo turn (turn 17 emitido 3x seguidas) e turnos reiniciando após retry (turn 19 → turn 4, 2 tentativas);
- `/tmp/vigia-HEADLESS-TAB-02C.jsonl` tem 1 `fim` — mas o aviso chegou 3x no chat: o `fim` é relido/reanunciado por quem consome o jsonl.

## Entregas (só isto, 2 arquivos)
1. `scripts/vigia_run.py` — dedupe de emissão:
   - `fim`: emitir NO MÁXIMO 1x por (missionId, veredito, tentativa). Antes de emitir, checar marcador no próprio jsonl (última linha com `"evento":"fim"` para o MESMO veredito+tentativas) e, se existir, NÃO reemitir.
   - `andamento`: não reemitir se (turn, custo) idênticos ao último evento emitido.
2. `scripts/test_vigia_dedupe.py` — pytest hermético (fixtures via tmp_path/monkeypatch, sem rede, sem sleep longo): (a) fim duplicado não é emitido 2x; (b) andamento com mesmo (turn,custo) não é reemitido; (c) fim de veredito DIFERENTE é emitido (não suprime troca legítima).
3. Prova E2E `scripts/prova-VIGIA-DEDUPE-01.py`: roda o fluxo de emissão duas vezes com o mesmo estado e imprime `VIGIA-DEDUPE-01-PROVA-OK` apenas se o jsonl resultante contiver exatamente 1 `fim`. Grava `scripts/prova-VIGIA-DEDUPE-01.out` (>100 bytes).
4. RELATORIO-VIGIA-DEDUPE-01.md (causa raiz citada + antes/depois).
5. Commit único `VIGIA-DEDUPE-01: dedupe fim/andamento no vigia_run`, `git add` só dos 4 arquivos.

## MAPA PRÉ-DIGERIDO
- `scripts/vigia_run.py:_emit:def ~linha-30` (função de emissão — ponto único para o dedupe)
- `scripts/vigia_run.py:_fim_event:def ~linha-84` (monta evento fim)
- `scripts/vigia_run.py:loop principal:linha-166` (`while cached is not None or veredito is None` — emite andamento/fim)
- `scripts/despachar_missao.py:163-180` (quem spawna o vigia — NÃO editar)

## Regras
- pytest/py_compile como worker (você já é worker). Sem sudo, sem cat/head/ls; leitura por code_slice/code_find/grep -n.
- Não mude o formato dos eventos existentes nem o caminho do jsonl (consumidor externo depende).
- Não baixe nada da internet; STOP-AND-REPORT se faltar algo.
- Commit cedo; `git add` seletivo; nada de git reset/checkout/stash.

```harness-stop
cmd cd /home/worker/wt-VIGIA-DEDUPE-01 && grep -q -F 'VIGIA-DEDUPE-01-PROVA-OK' scripts/prova-VIGIA-DEDUPE-01.out
cmd cd /home/worker/wt-VIGIA-DEDUPE-01 && python3 -m pytest scripts/test_vigia_dedupe.py -q
cmd cd /home/worker/wt-VIGIA-DEDUPE-01 && git log --format=%s -1 | grep -q -F 'VIGIA-DEDUPE-01'
cmd cd /home/worker/wt-VIGIA-DEDUPE-01 && test $(stat -c%s scripts/prova-VIGIA-DEDUPE-01.out) -gt 100
cmd cd /home/worker/wt-VIGIA-DEDUPE-01 && grep -q -F 'VIGIA-DEDUPE-01' RELATORIO-VIGIA-DEDUPE-01.md
```

# MISSÃO HYGIENE-MASTER-02

Fonte: ROADMAP.md linha 467. Contexto: FIND-master-vermelho-1012 (P1).

Objetivo: deixar a suite do repo verde. O master do harness-s2 está com 10 testes falhando SEM merge nenhum novo (estado herdado). Você roda os testes, diagnostica e conserta os 10 vermelhos listados abaixo.

## DIAGNÓSTICO JÁ FEITO (falhas exatas)
- tests/test_custo_dia_runs.py — 5 failures: test_agregacao_dia_brt, test_por_missao_mais_caros_primeiro, test_cost_usd_ausente_nao_quebra, test_saida_untrusted_notice_e_exit0, test_fuso_utc_vira_dia_brt (todas AssertionError)
- tests/test_harness_close.py::TestClose::test_reprompt_e_fail_honesto
- tests/test_tools_guard_02.py — 2 failures: test_catalogo_tem_17_tools_nomes_exatos, test_guard_preciso_zero_violacoes_no_catalogo_real
- tests/test_watchdog.py — 2 failures: test_sweep_roda_dois_e_falha_nao_aborta, test_sweep_timeout_mata_e_segue

## MAPA
- tests/test_custo_dia_runs.py:test_agregacao_dia_brt (5 testes em 1 arquivo)
- tests/test_harness_close.py:TestClose::test_reprompt_e_fail_honesto
- tests/test_tools_guard_02.py:GuardPreciso::test_catalogo_tem_17_tools_nomes_exatos
- tests/test_watchdog.py:test_sweep_roda_dois_e_falha_nao_aborta
- Codigo de producao apontado por cada teste (o worker localiza via code_find.sh)

## ORDEM DE SERVIÇO
1. `cd /home/worker/wt-HYGIENE-MASTER-02 && python3 -m pytest tests/ -q` (como está, no seu worktree) e leia o traceback completo de cada um dos 10 (`python3 -m pytest tests/test_custo_dia_runs.py -q` um arquivo por vez para ver o erro real).
2. Conserte o CÓDIGO ou o TESTE conforme a causa:
   - test_tools_guard_02: se a causa for o catálogo de tools com nome/contagem diferentes do código real, o catálogo do teste é que está desatualizado — atualize o TESTE para refletir o catálogo real (não invente tool).
   - test_custo_dia_runs / watchdog / harness_close: leia o código testado e conserte o BUG real no código de produção quando o teste estiver certo; só mude o teste se ele estiver errado por causa de mudança legítima já em master.
   - PROIBIDO apagar, pular ou enfraquecer teste para passar.
3. Re-rote até `python3 -m pytest tests/ -q` = 0 failed.
4. Commit cedo: `cd /home/worker/wt-HYGIENE-MASTER-02 && git add -u tests/ e arquivos de código tocados && git commit -m "HYGIENE-MASTER-02: suite verde (10 vermelhos curados)"`.
5. `RELATORIO-HYGIENE-MASTER-02.md`: causa raiz de cada grupo + o que mudou.

## REGRAS
- PROIBIDO git reset/checkout/stash/clean; sudo; cat/head/ls; escrever fora do worktree.
- Arquivo existente = ler trecho exato com `code_slice.sh` ou `sed -n 'A,Bp'` IMEDIATAMENTE antes do Edit e copiar old_string literal.

```harness-stop
cmd cd /home/worker/wt-HYGIENE-MASTER-02 && python3 -m pytest tests/ -q --tb=no
cmd cd /home/worker/wt-HYGIENE-MASTER-02 && test -f RELATORIO-HYGIENE-MASTER-02.md
cmd cd /home/worker/wt-HYGIENE-MASTER-02 && test "$(git log -1 --format=%s)" = "HYGIENE-MASTER-02: suite verde (10 vermelhos curados)"
```

# RELATORIO-TRIAGEM-SUITE-01 — diagnostico das falhas pre-existentes

Suite como worker: 10 failed, 643 passed, 2 skipped (enforce 0 — corrigidos pelo merge RD-GITGUARD-FIX-01, confirmado).

## Falhas e classificacao

1. tests/test_custo_dia_runs.py::test_agregacao_dia_brt — (B) AMBIENTE
   Assertiva: `assert out["dia"] == "2026-02-10"` -> `assert '2026-10-11' == '2026-02-10'`
   Evidencia: teste fixa data do fixture (2026-02-10) mas a tool custo_dia agrega pelo dia corrente real (2026-10-11); a suíte não congela a data (ex.: TZ/fake time), então o teste só passaria na data do fixture.

2. tests/test_custo_dia_runs.py::test_por_missao_mais_caros_primeiro — (B) AMBIENTE
   Assertiva: `assert ids == ["CARO", "MEIO", "BARATO"]` -> `assert [] == [...]`
   Evidencia: fixture com runs de 2026-02-10; tool filtra pelo dia corrente (2026-10-11), retorna por_missao vazio. Mesma causa raiz do item 1.

3. tests/test_custo_dia_runs.py::test_cost_usd_ausente_nao_quebra — (B) AMBIENTE
   Assertiva: `assert out["turnos_total"] == 4` -> `assert 0 == 4`
   Evidencia: run do fixture datada 2026-02-10T12:00:00Z; filtro de dia corrente exclui a run, turnos_total=0.

4. tests/test_custo_dia_runs.py::test_saida_untrusted_notice_e_exit0 — (C) OBSOLETO
   Assertiva: `assert "untrusted:true" in p.stdout` -> stdout tem `"untrusted": true, "notice": ...` (JSON com espaço, sem o literal `untrusted:true`)
   Evidencia: a tool mudou o formato de saída (campo JSON estruturado + notice); o teste procura o literal antigo do envelope. Teste desatualizado quanto ao contrato de saída atual.

5. tests/test_custo_dia_runs.py::test_fuso_utc_vira_dia_brt — (B) AMBIENTE
   Assertiva: `assert out["dia"] == "2026-02-10"` -> `assert '2026-10-11' == '2026-02-10'`
   Evidencia: conversão UTC->BRT correta, mas o teste depende do dia corrente coincidir com o fixture; sem congelamento de data/TZ na suíte.

6. tests/test_harness_close.py::TestClose::test_reprompt_e_fail_honesto — (A) BUG_REAL
   Assertiva: `self.assertEqual(s["veredito"], "FAIL")` -> `AssertionError: 'PASS' != 'FAIL'`
   Evidencia: contract com `harness-close cmd false` deveria fechar FAIL honesto; o fecho avaliou como PASS — comportamento do harness errado (stop cmd falhou mas veredito saiu PASS).

7. tests/test_tools_guard_02.py::GuardPreciso::test_catalogo_tem_17_tools_nomes_exatos — (C) OBSOLETO
   Assertiva: diff do catalogo esperado vs real: real tem 'verificar' (sem espaço?) e não tem 'release_pipeline'; lista de 17 nomes mudou.
   Evidencia: catalogo de tools evoluiu (tools renomeadas/adicionadas); teste mantém lista fixa antiga.

8. tests/test_tools_guard_02.py::GuardPreciso::test_guard_preciso_zero_violacoes_no_catalogo_real — (C) OBSOLETO
   Assertiva: zero violacoes esperado; guard aponta falsos positivos em ordens_guard.sh (rm/tee/sed -i/cp/mv em strings de grep) e release_pipeline.sh (curl).
   Evidencia: heuristica do guard_preciso sinaliza padrões legítimos dentro de código shell; teste fixa "zero violacoes" sobre catalogo que cresceu.

9. tests/test_watchdog.py::test_sweep_roda_dois_e_falha_nao_aborta — (A) BUG_REAL
   Assertiva: `assert len(j["falhas_tipadas"]) == 1` -> `assert 2 == 1` (falhas: 10-fail exit_3 e 20-ok exit_1)
   Evidencia: script "20-ok" (echo ok) reportado como falha exit_1 — o sweep classifica saida normal como falha tipada; comportamento do harness errado.

10. tests/test_watchdog.py::test_sweep_timeout_mata_e_segue — (A) BUG_REAL
    Assertiva: `assert j["falhas_tipadas"][0]["tipo"] == "timeout"` -> `assert 'exit_1' == 'timeout'`
    Evidencia: script dormindo 60s com WATCHDOG_TIMEOUT=1s deveria ser tipado timeout; sweep reporta exit_1 — tipagem de timeout não implementada/errada.

## Contagem por categoria
- (A) BUG_REAL: 3 (itens 6, 9, 10)
- (B) AMBIENTE: 4 (itens 1, 2, 3, 5)
- (C) OBSOLETO: 3 (itens 4, 7, 8)

## Recomendacao por item
1. corrigir teste (congelar data/TZ no fixture ou mockar dia corrente)
2. corrigir teste (idem item 1)
3. corrigir teste (idem item 1)
4. corrigir teste (atualizar assertiva para o formato JSON atual: `"untrusted": true` + notice)
5. corrigir teste (idem item 1)
6. corrigir codigo (fecho deve produzir FAIL quando stop cmd falha)
7. corrigir teste (regenerar lista de 17 tools a partir do catalogo atual)
8. corrigir teste (refinar heuristica/allowlist do guard_preciso ou atualizar expectativa)
9. corrigir codigo (sweep nao deve tipar script com exit 0/echo ok como falha)
10. corrigir codigo (implementar tipagem timeout no sweep quando WATCHDOG_TIMEOUT estoura)

TRIAGEM-SUITE-OK

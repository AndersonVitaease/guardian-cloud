# RELATORIO-TRIAGEM-SUITE-01

Diagnostico das falhas pre-existentes da suite (baseline harness-s2).
Suite: 10 failed, 643 passed, 2 skipped. Os 2 failures de enforce foram
corrigidos pelo merge RD-GITGUARD-FIX-01 (confirmado: nao aparecem mais).

## Falhas e classificacao

1. tests/test_custo_dia_runs.py::test_agregacao_dia_brt
   Assertiva: `assert out["dia"] == "2026-02-10"` -> obteve '2026-10-11' (data corrente real).
   Evidencia: "AssertionError: assert '2026-10-11' == '2026-02-10'" (test_custo_dia_runs.py:66)
   Categoria: (B) AMBIENTE — teste fixa dia esperado via fixture, mas a tool
   custo_dia.sh usa a data corrente real; a suite nao congela o relogio/TZ.

2. tests/test_custo_dia_runs.py::test_por_missao_mais_caros_primeiro
   Assertiva: `ids == ["CARO", "MEIO", "BARATO"]` -> obteve [] (por_missao vazio).
   Evidencia: "AssertionError: assert [] == ['CARO', 'MEIO', 'BARATO']" (test_custo_dia_runs.py:92)
   Categoria: (B) AMBIENTE — fixture com finished_at em 2026-02-10 nao bate
   com o dia corrente (2026-10-11), entao nenhuma run entra na agregacao.

3. tests/test_custo_dia_runs.py::test_cost_usd_ausente_nao_quebra
   Assertiva: `out["turnos_total"] == 4` -> obteve 0.
   Evidencia: "assert 0 == 4" (test_custo_dia_runs.py:103)
   Categoria: (B) AMBIENTE — mesma causa raiz: run do fixture fora do dia
   corrente, filtrada antes da agregacao.

4. tests/test_custo_dia_runs.py::test_saida_untrusted_notice_e_exit0
   Assertiva: `"untrusted:true" in p.stdout` -> stdout tem `"untrusted": true` (JSON com espaco).
   Evidencia: "assert 'untrusted:true' in '{\"ok\": true, ... \"untrusted\": true, ...}'" (test_custo_dia_runs.py:119)
   Categoria: (C) OBSOLETO — teste procura substring do formato antigo de
   serializacao; a tool agora emite JSON canonico com chave "untrusted": true.

5. tests/test_custo_dia_runs.py::test_fuso_utc_vira_dia_brt
   Assertiva: `out["dia"] == "2026-02-10"` -> obteve '2026-10-11'.
   Evidencia: "AssertionError: assert '2026-10-11' == '2026-02-10'" (test_custo_dia_runs.py:131)
   Categoria: (B) AMBIENTE — conversao de fuso testada contra data fixa;
   sem congelamento de relogio o dia corrente prevalece.

6. tests/test_harness_close.py::TestClose::test_reprompt_e_fail_honesto
   Assertiva: `s["veredito"] == "FAIL"` apos harness-close com `cmd false` -> obteve 'PASS'.
   Evidencia: "AssertionError: 'PASS' != 'FAIL'" (test_harness_close.py:90)
   Categoria: (A) BUG_REAL — comando de stop que falha (exit != 0) deveria
   forcar veredito FAIL honesto; o fecho esta tratando como PASS.

7. tests/test_tools_guard_02.py::GuardPreciso::test_catalogo_tem_17_tools_nomes_exatos
   Assertiva: catalogo contem exatamente 17 nomes; diff mostra 'verificar' vs
   'verificar ' e 'release_pipeline' ausente/extra.
   Evidencia: "- 'verificar' / + 'verificar'] / - 'release_pipeline']" (test_tools_guard_02.py:237)
   Categoria: (C) OBSOLETO — catalogo de tools mudou (nomes renomeados/adicionados);
   teste fixa a lista antiga de 17 nomes.

8. tests/test_tools_guard_02.py::GuardPreciso::test_guard_preciso_zero_violacoes_no_catalogo_real
   Assertiva: zero violacoes do guard no catalogo real -> varias reportadas
   (chmod, rm, tee, sed -i, cp, mv em ordens_guard.sh/ordens-watchdog.sh; curl em release_pipeline.sh).
   Evidencia: "ordens_guard.sh:72: tee: if printf '%s' \"$CMD\" | grep -Eq '(>|>>|tee|sed -i|cp |patch|write_file|rm |mv )'..." (test_tools_guard_02.py:241)
   Categoria: (A) BUG_REAL — o proprio guard usa padroes que ele classifica
   como violacao (falsos positivos ao escanear o catalogo real); o scanner
   precisa de allowlist para os scripts do guard.

9. tests/test_watchdog.py::test_sweep_roda_dois_e_falha_nao_aborta
   Assertiva: `len(j["falhas_tipadas"]) == 1` -> obteve 2 (20-ok reportado como exit_1).
   Evidencia: "assert 2 == 1 ... [{'tipo': 'exit_3'}, {'tipo': 'exit_1'}]" (test_watchdog.py:35)
   Categoria: (A) BUG_REAL — script que termina com sucesso (echo ok) esta
   sendo tipado como falha exit_1; classificacao de exit code errada no sweep.

10. tests/test_watchdog.py::test_sweep_timeout_mata_e_segue
    Assertiva: `j["falhas_tipadas"][0]["tipo"] == "timeout"` -> obteve 'exit_1'.
    Evidencia: "AssertionError: assert 'exit_1' == 'timeout'" (test_watchdog.py:52)
    Categoria: (A) BUG_REAL — script morto por timeout (WATCHDOG_TIMEOUT=1s,
    sleep 60) nao esta sendo classificado como 'timeout'; o sweep reporta
    exit_1, mascarando a causa real.

## Resumo

Contagem por categoria:
- (A) BUG_REAL: 4 (itens 6, 8, 9, 10)
- (B) AMBIENTE: 4 (itens 1, 2, 3, 5)
- (C) OBSOLETO: 2 (itens 4, 7)

Recomendacao por item:
1. corrigir teste — congelar data/TZ (ex.: env de data fixa ou mock do clock) ou filtrar por finished_at do fixture.
2. corrigir teste — alinhar finished_at do fixture com o dia corrente congelado.
3. corrigir teste — idem item 2.
4. corrigir teste — trocar substring por parse do JSON e checar campo untrusted == true.
5. corrigir teste — idem item 1 (congelar relogio).
6. corrigir codigo — fecho deve mapear stop-command com exit != 0 para veredito FAIL.
7. corrigir teste — atualizar lista de nomes ao catalogo atual (ou tornar o teste data-driven a partir do catalogo).
8. corrigir codigo — adicionar allowlist/excecao no scanner para os scripts do proprio guard (ordens_guard.sh, ordens-watchdog.sh, release_pipeline.sh).
9. corrigir codigo — sweep deve classificar exit 0 como sucesso, nao como falha exit_1.
10. corrigir codigo — sweep deve detectar morte por timeout (exit 124/kill) e tipar como 'timeout'.

Categorias usadas: BUG_REAL\|AMBIENTE\|OBSOLETO

TRIAGEM-SUITE-OK

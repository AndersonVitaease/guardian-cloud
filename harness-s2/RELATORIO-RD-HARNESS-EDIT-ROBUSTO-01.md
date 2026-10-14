# RD-HARNESS-EDIT-ROBUSTO-01 — Edit tolerante + quebra de loop de recusa

## O que foi feito
1. **Edit tolerante** (`harness.py`, bloco `Edit` de `run_tool`): se `old_string` exato não existe, casa linha a linha ignorando indentação (comparação via `l.strip()`), exigindo ocorrência única; substitui reindentando `new_string` pela indentação da primeira linha casada e retorna `OK edited <path> (casou ignorando indentação, linhas A-B)`. Múltiplas ocorrências ⇒ `ERRO: old_string ambíguo (N ocorrências ignorando indentação, linhas ...)`.
2. **Dica de erro**: sem casamento, retorna `ERRO: old_string não encontrado` e, quando `difflib.get_close_matches` (cutoff 0.4, máx. 6) acha linhas parecidas com a primeira linha de `old_string`, acrescenta `Trecho mais parecido (linhas A-B):` com número de linha e conteúdo exato (indentação preservada). Sem similaridade real, a mensagem fica só no erro básico — compatível com o teste existente `test_harness.TestIsolamento.test_edit_e_bash`.
3. **Quebra de loop de recusa** (`_bash_refuse_state` + `_reset_bash_refuse_state`): conta recusas consecutivas do MESMO comando; a partir da 2ª, a mensagem ganha `REPETIDO <N>x: ... NÃO o repita. Faça outra coisa: Edit/Write no arquivo, ou leia com sed -n 'A,Bp' ARQ / grep -n PADRAO ARQ.`. Comando diferente ou execução bem-sucedida zera o contador.
4. `tests/test_edit_robusto.py`: 5 testes (edit exato inalterado; casa ignorando indentação e reindenta; ambíguo; sem casar com dica; loop de recusa com REPETIDO 2x e reset).

## Honestidade
- `difflib` já estava importado no arquivo (mapa dizia que não) — nenhum import novo foi preciso.
- A dica "Trecho mais parecido" só aparece quando há match real; isso foi necessário para não quebrar `test_harness.py` (expectativa de mensagem exata), o que não estava explícito no mapa.
- `stripped.index(c)` devolve a primeira linha com aquele texto; para arquivos com linhas duplicadas a numeração pode apontar a primeira ocorrência — limitação conhecida e aceitável para o propósito (dica ao worker).
- Não toquei em `_bash_redirect` nem na lógica de vagueio/escada/janela.

## Verificação
- `python3 -m py_compile harness.py` OK
- `python3 -m unittest tests.test_edit_robusto` → Ran 5 tests, OK
- `python3 -m unittest discover -s tests` → Ran 212 tests, OK
- Snippets das stop-conditions (edit tolerante, dica, REPETIDO 2x/reset) todos passam.
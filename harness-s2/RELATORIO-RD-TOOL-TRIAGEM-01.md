# RELATÓRIO — RD-TOOL-TRIAGEM-01

## Objetivo
Automatizar a triagem de FAILs: `python3 scripts/triagem.py <runs_dir>` lê os
`harness-trail.jsonl` de cada `tentativa-N/run-*/` e imprime JSON determinístico
com causas por tentativa, causa dominante e ação sugerida.

## Entregas
- `scripts/triagem.py`: função importável `triar(runs_dir)` + CLI (`main`).
  - Detecta: `LEITURA_RECUSADA`, `SO_EXPLORACAO`, `EDIT_FALHOU`,
    `LOOP_COMANDO_RECUSADO`, `SETUP_PERMISSAO`, `VAGUEIO`, `STOPS_LENTOS`
    (omitida quando o trail não tem `latencia_ms` nos `_stop_check`).
  - Prioridade da dominante: SETUP_PERMISSAO > LEITURA_RECUSADA > EDIT_FALHOU >
    LOOP_COMANDO_RECUSADO > SO_EXPLORACAO > VAGUEIO; PASS na última tentativa
    vence tudo.
  - Diretório vazio/inexistente ⇒ mensagem clara em stderr e exit 2.
  - Reaproveita `scripts/diagnostico.py` (`_ler_trail`, `_comandos_repetidos`,
    `analisar`) sem alterá-lo.
- `tests/test_triagem.py`: 11 testes com trails sintéticos em tempdir — um por
  causa, PASS final, stops sem dado, diretório vazio (exit 2) e determinismo.
- `tests/accept_triagem.py` (pré-existente, não editado): `ACEITE-TRIAGEM OK`.

## Validação
- `python3 -m unittest tests.test_triagem` ⇒ OK (11 testes).
- `python3 tests/accept_triagem.py` ⇒ ACEITE-TRIAGEM OK.
- `python3 -m unittest discover -s tests` ⇒ OK.
- Rodado contra runs reais: RD-GB-ABUSE-01C (dominante LEITURA_RECUSADA),
  RD-HARN-FATIA-AUTO-03 (LEITURA_RECUSADA), RD-HARN-FATIA-AUTO-02 (PASS).

## Limitações / honestidade
- `STOPS_LENTOS` depende de `latencia_ms` nos `_stop_check`; trails antigos sem
  esse campo simplesmente não geram a causa (não é inventada).
- `veredito`/`turnos` vêm do registro `_resumo` quando presente; tentativa sem
  resumo fica com veredito "FAIL" e turnos contados do trail.
- A evidência é texto curto com contagens (bash, erros, write/edit, motivo) —
  suficiente para o supervisor decidir, sem narrativa.
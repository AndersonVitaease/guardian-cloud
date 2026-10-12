# RELATORIO RD-ENG-SHIP-06 - SHIP do M1-GATE

Veredito: **SHIP-FALHOU**

## Evidencia

- TOOLS_BASH_DIR nao definido no ambiente do worker (echo vazio; exit 127 em
  bash "$TOOLS_BASH_DIR"/release_pipeline.sh -> "No such file or directory").
- Catalogo local tools-bash/tools.json (worktree RD-ENG-SHIP-01) NAO contem
  a tool release_pipeline (listagem de tools-bash/: code_find, code_slice,
  git_peek, trail_tail, mission_cost, flights, queue_peek, etc. - sem
  release_pipeline.sh).
- Tentativas de invocacao (todas exit 127):
  - bash "$TOOLS_BASH_DIR"/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
  - bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f

## Conclusao

A tool governada release_pipeline nao esta disponivel no catalogo deste
worktree nem via env do harness. Sem a tool nao ha como disparar o pipeline
para o HEAD 1696e9baff935bb1a390c2784b9975dd1282f84f. Nenhum rollback foi
executado. Falha de disponibilidade de tool (equivalente ao exit 127 da
RD-ENG-SHIP-04, agora com caminho completo e catalogo verificado).

## Acao recomendada

Instalar/propagar release_pipeline.sh no TOOLS_BASH_DIR do harness e reabrir SHIP.

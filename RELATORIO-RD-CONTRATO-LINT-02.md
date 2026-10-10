# Relatório RD-CONTRATO-LINT-02

## O que foi feito
Estendi `scripts/contrato_lint.py` com 6 códigos novos + refino do `PROIBIDO_ROOT_PATH`:

1. `FENCE_ERRADA` (erro): fence ```` ```h harness-stop ```` com texto entre crases e `harness-stop` — parser ignora e zera os stops.
2. `STOP_PATH_INEXISTENTE` (erro): stop com `cd <caminho absoluto>` para diretório inexistente (`os.path.isdir`).
3. `STOP_SO_TRIVIAL` (erro): todas as condições (sem prefixo `cd X &&`) são triviais (`test -f|-d|-e`, `true`, `:`, `ls`, `echo`).
4. `SEM_MAPA` (erro): ≥3 arquivos de código citados sem nenhuma referência `arquivo:NNN` nem seção `## MAPA`.
5. `ID_DIVERGENTE` (erro): título `# MISSÃO <ID>` diverge de `RELATORIO-<X>.md` ou `git log ... -F '<X>'` nos stops.
6. `PROVA_SEM_ISOLAMENTO` (aviso): stop roda `python3 prova-...`/`node server` sem menção a `mktemp`/`tempfile`/`tmp`/`GUARDIAN_DB_DIR`.
7. Refino `PROIBIDO_ROOT_PATH`: erro só com verbo de escrita na mesma linha; leitura pura vira aviso `LEITURA_ROOT_PATH`.

## Testes
`tests/test_contrato_lint2.py`: 14 testes (positivo e negativo por código novo + refino ROOT_PATH). Suíte inteira verde (`unittest discover` OK).

## Contratos reais
Os 3 contratos bons (`missao-rd-gb-abuse-01g`, `missao-rd-harn-fatia-auto-02`, `missao-rd-harn-fatia-auto-03`) continuam aprovados (exit 0). O contrato ruim `missao-rd-gb-abuse-01b` é reprovado com `FENCE_ERRADA` (exit 1).

## Ajustes de percurso
- O `Write` inicial gravou o teste no diretório da run; recuperei com `cp` para `tests/`.
- Corrigi dois falsos-negativos descobertos nos testes: regex de isolamento não casava `tmp` isolado (word boundary) e verbo de escrita era case-sensitive (contratos em pt usam "Crie").
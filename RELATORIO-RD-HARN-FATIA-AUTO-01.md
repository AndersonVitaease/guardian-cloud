# RELATÓRIO RD-HARN-FATIA-AUTO-01

## O que foi entregue

`scripts/fatiar_auto.py` — fatiador automático determinístico (stdlib apenas, sem
LLM): dado um contrato `.md` com seção `## ENTREGAS` numerada, um repo alvo e um
outdir, gera `plano.json` + um `.md` por fatia no formato aceito pelo harness.

- CLI: `python3 scripts/fatiar_auto.py <contrato> <repo> <outdir> [--max-arquivos N]`
  (default 2). Também importável: `fatiar(contrato, repo, outdir, max_arquivos=2)`.
- Parse das entregas numeradas e do bloco `harness-stop` do contrato.
- Para cada entrega, extrai símbolos citados (funções, rotas, arquivos) e localiza
  no repo os arquivos que os contêm (busca textual, limitada a `max_arquivos`).
- Agrupamento guloso serial: entregas consecutivas cujos arquivos cabem na fatia
  anterior são fundidas; `deps` = apenas a fatia anterior (cadeia serial).
- Cada `.md` de fatia traz: título `# MISSÃO <id>` (ids `<ID-DO-CONTRATO>-S1..Sn`),
  bloco `## MAPA` com referências `arquivo:LINHA` reais (linha verificada contra o
  tamanho do arquivo), stops herdados do contrato e filtrados pela fatia, regras
  de commit com o id no assunto. A última fatia fecha com relatório + commit.
- Determinismo: saída byte a byte idêntica em duas execuções (sem timestamps,
  sem caminhos temporários, ordenação estável em todo lugar).
- Contrato sem entregas ⇒ erro claro no stderr e **exit 2**.

## Testes

`tests/test_fatiar_auto.py` — 9 testes: parse de entregas, parse de stops,
contrato sem entregas (exceção + exit 2 via subprocess), agrupamento por arquivo
(respeita `max_arquivos`), mapa com linha real (valida 1 ≤ linha ≤ total),
serialização do DAG serial, determinismo, formato do `plano.json`, última fatia
com relatório. Suíte inteira do harness: 202 testes OK.
Aceite do supervisor: `ACEITE-FATIA-AUTO OK`.

## O que NÃO cobre

- Sem análise semântica de código: a localização de símbolos é por busca textual
  (grep); símbolo com nome ambíguo ou citado só em comentário pode gerar mapa
  impreciso (ainda válido: a linha existe no arquivo).
- Entregas que não citam nenhum símbolo presente no repo ficam sem arquivos
  mapeados (a fatia é gerada, mas o MAPA fica vazio).
- O agrupamento é guloso e serial por design (contrato exige deps = fatia
  anterior); não há paralelização nem reordenação de entregas.
- Stops são filtrados por correspondência textual entre stop e arquivos/símbolos
  da fatia; stop genérico (ex. `git log`) vai para a última fatia por convenção.
- Não valida que o repo é um worktree git nem executa os stops — apenas gera.
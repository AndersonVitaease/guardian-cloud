# MISSÃO RD-ENG-SHIP-02 — SHIP do M1-GATE (deploy do eng-mcp via canal do worker)

Fonte: ordem operator 11/10 (SHIP aprovado em chat; condução = missão, nunca o
supervisor).

## Contexto

Produção roda o commit 22f073b2 (deploy 23:43 BRT, smoke PASS). O HEAD atual do
repo (/opt/memoryos, BASE44-DECOUPLE-01) é 1696e9ba: inclui o código do
RD-SUPGUARD-M1-GATE (operatorOrder validado de verdade — verifyOperatorOrderToken,
ORDER-VIOLATION/SUPERVISOR_MUTATION_FORBIDDEN, trilha violations.jsonl) que NÃO
está em produção.

Canal oficial do worker JÁ ESTA OPERANTE (prova 21:00 BRT):
tool bash governada `release_pipeline` (no catálogo de tools do worker;
socket oficial do release runner resolvido pela própria tool;
status executado como worker com sucesso). Erros tipados: SOCKET_MISSING,
SOCKET_UNREACHABLE, BAD_ARGS, BAD_OPERATION, BAD_DEPLOY_JOB_ID.

## Tarefa

1. Como worker, chame a tool bash governada `release_pipeline` do SEU catálogo
   de tools (o supervisor a registrou e provou o canal; você só a invoca pelo
   nome, sem tocar caminhos de deploy) para disparar o pipeline completo do
   commit atual: leia o uso dela (code_slice no script do SEU ambiente) e use a
   operação de pipeline com commitSha=1696e9ba... resolva o SHA completo de 40
   hex com python3 (git no checkout de origem citado no mapa) ANTES de chamar.
   NÃO passe operatorOrder falso: o chamador worker/missão não precisa dele.
2. Acompanhe o resultado (status) até: deployStatus PASS + smokeStatus PASS +
   rollbackRequired false, OU qualquer erro tipado real.
3. Se algo falhar tipado: NÃO faça rollback; reporte o código exato e o estado
   (veredito SHIP-FALHOU).
4. Máximo 3 leituras de status por turno de trabalho real entre elas (sem
   loop de polling).

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escrita direta no destino (Write), NUNCA .tmp/.sh + mv/cp; nada em /tmp.
- Todo stop roda `cd /home/worker/wt-RD-ENG-SHIP-01 &&` primeiro.
- Sem cat/head/tail/ls/find/grep -oE/sed -i/awk soltos: code_find/code_slice/
  file_peek, grep -n COM PIPE, python3 para JSON.
- Máximo 3 linhas de ferramenta por turno.
- Commit como worker com o ID no subject; NUNCA git reset/checkout/stash/clean;
  merge/fecho é do supervisor.

## MAPA (arquivo:linha)

- /opt/mission-events/tools-bash/release_pipeline.sh:7-13 — canal, erros tipados
- /opt/mission-events/tools-bash/tools.json — catálogo (release_pipeline registrado)
- HEAD alvo do deploy: 1696e9ba (BASE44-DECOUPLE-01, /opt/memoryos)

## Stops (condições de parada)

```harness-stop
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-02.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-02' RELATORIO-RD-ENG-SHIP-02.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-02.md
```
SHIP-OK = deploy do commit 1696e9ba com deployStatus PASS + smokeStatus PASS.

# GUIA DE CONTRATO PARA O HARNESS (lições medidas em 09–10/10/2026)

Fonte: runs reais RD-GB-ABUSE-01C..G, RD-HARN-FATIA-AUTO-01..03, BASH-FILTRO-PIPE-01, ESPELHO-RETRY-01. O worker é um modelo flash: ele pousa missão pequena e mapeada em poucos turnos e **vagueia** em missão grande sem mapa. Cada regra abaixo custou uma run perdida.

## 1. Forma do contrato (o parser é literal)
- Título `# MISSÃO <ID>`; o **mesmo ID** em: nome do relatório (`RELATORIO-<ID>.md`), assunto do commit e stops. ID divergente = stop eternamente vermelho (ABUSE-01G: relatório saiu como `01F`).
- Stops num bloco ```` ```harness-stop ```` EXATO (nada de `h harness-stop`; senão 0 stops parseados). Uma condição por linha, `cmd ...`.
- O **caminho do worktree nos stops é o diretório real que existe** (`cd /home/worker/wt-<X> && ...`). NUNCA derive um contrato novo por substituição de texto do ID: o caminho passa a apontar um diretório inexistente e o worker trabalha no vazio (ABUSE-01E).
- Reexecução de missão que já tem WIP: faça **checkpoint commit antes** e escreva "CONTINUAÇÃO — não recomece" no contrato.

## 2. Stops que provam entrega
- Pelo menos um stop **específico** da entrega (`grep -q -F '<símbolo novo>' arq`, `python3 prova-X.py` que imprime marcador). `test -f arq`, `true`, `ls`, `echo` sozinhos = VACUO (passam no baseline, não provam nada).
- Baseline: o que ainda não foi feito tem de estar VERMELHO no dry-run; o que é regressão, VERDE. Conferir com `despachar_missao.py --dry-run`.
- Prova que sobe servidor/banco: **banco e porta isolados** (tempdir + env, ex. `GUARDIAN_DB_DIR`) e < 60 s. Estado compartilhado entre provas (guardian.db, bucket de rate-limit) faz uma execução envenenar a próxima — foi a causa de 4 tentativas perdidas.
- Stops rodam a cada turno: stop lento (> 30 s) come o orçamento; evite sleep longo.

## 3. Escopo e mapa
- Missão que toca > 1 arquivo ou > 5 testes: **fatie** (`scripts/fatiar_auto.py contrato repo outdir`) ou inclua `## MAPA` com `arquivo:LINHA` real (função/rota/símbolo a editar). Sem mapa o worker passa os turnos lendo e nunca edita.
- Máx. 2–3 arquivos de código por micro-missão; uma entrega verificável por vez; sem "extras" (parágrafo de IP-anomalia/Redis/2FA triplicou o escopo da ABUSE-01).
- Dê o diagnóstico quando você o tiver (causa raiz + linhas): o worker executa muito melhor do que investiga.
- Instrução de edição: `old_string` de UMA linha distinta; multilinha com indentação errada falha (até o fix RD-HARNESS-EDIT-ROBUSTO-01).

## 4. Ferramentas e ambiente do worker
- Leitura: `grep -n PADRAO arq | head`, `sed -n 'A,Bp' arq`, `code_find.sh`, `code_slice.sh`. `cat arq`, `head -5 arq`, `ls` são recusados (LEITURA_MECANICA_RECUSADA): não os cite no contrato.
- **Contrato que manda ler dados de run** (trails `.jsonl`, `*-summary.json`, logs): o harness RECUSA `ls`, `cat/head/tail ARQ`, `grep -o ... .jsonl` no Bash e o worker gasta turnos tentando variantes (RD-TOOL-FECHAR-01: 12 de 31 Bash recusados, zero Write). Escreva no contrato (a) o FORMATO real dos dados (chaves, onde fica o `_resumo`) e (b) a forma permitida: `python3 -c "import json..."`. Não mande o worker descobrir.
- O worker NÃO escreve em `/root` nem `/opt`; entregue no worktree e o supervisor aplica. Contrato não deve mandar escrever lá.
- Nunca `git reset/checkout/stash/clean` (perde WIP). Commit cedo, com o ID no assunto; `git add` só dos arquivos da missão (não `-A`: artefatos de teste, ex. `uploads/*.txt`, foram parar no repo).
- Worktree precisa ser gravável pelo worker (`chown -R worker:worker`); o harness agora falha em $0 com `setup_permissao` se não for.

## 5. Despacho e acompanhamento
- Despache e **dê foco na aba** (`herdr tab focus <id>`); não feche a aba sem ordem do operador. O espelho segue as tentativas do auto-retry.
- `--retry 3` + `--turns` ≥ 40 para missão média; missão grande = fatiada. Orçamento: ~US$ 0,03/10 turnos no flash.
- Veredito FAIL por vagueio com WIP bom: inspecione o worktree (`git_peek`) antes de redespachar; muitas vezes só falta relatório/commit.
- Matar run deixa `node server.js` órfãos segurando banco/porta: limpe por cwd do worktree (nunca por nome genérico).

## 6. Contrato de redespacho/continuação (lições da FORCA-ESCRITA-03 e da FECHAR-02, 10/10)
- Ordem: o contrato novo só é escrito DEPOIS que a missão que ensina fecha (merge feito, aba fechada, `runs_status` = 0). Leia o commit dela (`git_peek.sh <repo> show-stat <sha>`) e cite o comportamento real do harness: a força-escrita agora é REAL (o stream respeita a lista de tools, a barreira na execução bloqueia Bash na janela de escrita, o loop de Edit é quebrado — dfad792d, merge b5a08673).
- Escrever cedo: o contrato manda ESCREVER com Write/Edit, nunca explorar. Arquivo novo = Write inteiro (não Edit); arquivo existente = ler o trecho exato com `code_slice` IMEDIATAMENTE antes do Edit e copiar o `old_string` literal (de memória falhou 25 de 32).
- Retry sem memória: o contrato lista o que as tentativas anteriores já leram/escreveram (`triagem.sh` + trail; 57% das leituras se repetiam) e o estado VERIFICADO do WIP (símbolo, linha, testes verdes/vermelhos com o erro exato). Faça checkpoint commit como worker antes.
- Stops sem `cat/head/ls/grep -A`, sem `;` e sem `sudo`; mapa `arquivo:símbolo:LINHA`; `contrato_lint` verde e cada stop rodado ao vivo como worker no baseline antes de despachar.
- Falso vermelho: `python3`/`py_compile`/`unittest` no worktree sempre como worker (`sudo -u worker`), nunca root (root não acha pytest/módulos do worker e gera arquivos root-owned).

## 7. Lições do ciclo do orquestrador (10/10 tarde — despachante DEVE seguir)

- **Todo comando de stop (e todo comando do contrato) começa com `cd /home/worker/wt-<X> && `**: a unit roda com working-directory=/home/worker/harness-s2 (repo raiz). Stops sem cd absoluto fizeram o worker errar de diretório e vagar 3 tentativas inteiras (RD-DEPLOY-TOOL-01, US$ ~0,07 perdido).
- **Schema de intent na fila**: o consumer só processa linhas JSON com `id` + `type: mission_dispatch` + `payload:{missionId, promptFile, cwd, spawnedBy, ...}`. Linha flat sem `type` fica INERT na fila. Escreva a linha com `python3` (json.dumps) — `echo` com aspas soltas malforma a linha (1 intent perdida).
- **Escreva o contrato DENTRO do worktree e commite ANTES de enfileirar** (o stop exige; contrato só em /opt não é visto pelo worker).
- **Fecho mínimo tem MESMO ID**: triagem mostrando trabalho pronto (suíte verde, patch aplicado) = contrato de continuação que SÓ commita/relata; proíba mexer no código. Nunca re-despache o contrato inteiro.
- **depends_on**: intent pode declarar `"depends_on":["<ID>"]` no payload — o consumer bloqueia com DEPS_NOT_MET até o ledger do pré-requisito pousar `closed/PASS`. ATENÇÃO: blocked ainda é TERMINAL no consumer (cura em RD-ORCH-BOUNDARY-01); se o pré-requisito não pousou ainda, NÃO enfileire a dependente — espere e re-enfileire com id novo.
- **Ferramenta pytest, NÃO unittest** quando os testes são funções com fixtures (`tmp_path`): unittest coleta 0 casos de funções soltas ("NO TESTS RAN").
- **Nascimento no herdr é garantia estrutural** (despachar_missao.py no vivo): sem aba = unit parada + PANE_AUSENTE + requeue. Se um despacho terminar com `pane: null`, a missão NÃO nasceu — re-despache, não espere.
- **Estado divergente tem precedência**: disco > veredito do ORQD/consumer > briefing do ledger. Antes de redespachar um FAIL, confirme o disco (`git_peek` + triagem): 3 casos hoje de veredito errado com trabalho pronto.

## 8. Roadmap — fonte única (10/10)
- Proibido criar ou editar arquivo de roadmap fora de `/opt/mission-events/ROADMAP.md` e `/opt/mission-events/ROADMAP-GUARDIAN.md`. Item novo ou mudança de estado = `bash /opt/mission-events/tools-bash/roadmap_note.sh` (ferramenta já governada).
- Todo contrato novo cita a fonte do trabalho: `Fonte: ROADMAP.md linha N` (ou `Fonte: ROADMAP-GUARDIAN §X`). Fonte apontando para outro roadmap paralelo = recusa do despacho.
- Esta regra vale para supervisor, despachante e worker.

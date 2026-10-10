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
- O worker NÃO escreve em `/root` nem `/opt`; entregue no worktree e o supervisor aplica. Contrato não deve mandar escrever lá.
- Nunca `git reset/checkout/stash/clean` (perde WIP). Commit cedo, com o ID no assunto; `git add` só dos arquivos da missão (não `-A`: artefatos de teste, ex. `uploads/*.txt`, foram parar no repo).
- Worktree precisa ser gravável pelo worker (`chown -R worker:worker`); o harness agora falha em $0 com `setup_permissao` se não for.

## 5. Despacho e acompanhamento
- Despache e **dê foco na aba** (`herdr tab focus <id>`); não feche a aba sem ordem do operador. O espelho segue as tentativas do auto-retry.
- `--retry 3` + `--turns` ≥ 40 para missão média; missão grande = fatiada. Orçamento: ~US$ 0,03/10 turnos no flash.
- Veredito FAIL por vagueio com WIP bom: inspecione o worktree (`git_peek`) antes de redespachar; muitas vezes só falta relatório/commit.
- Matar run deixa `node server.js` órfãos segurando banco/porta: limpe por cwd do worktree (nunca por nome genérico).

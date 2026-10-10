# RD-HARNESS-FORCA-ESCRITA-03 — Relatório

## Objetivo
Fechar as três frestas do FORCA-ESCRITA-02: (1) o stream não respeitava
as `tools` restritas enviadas pelo harness; (2) a restrição era só
"de palavras" — o modelo podia emitir `tool_use` de Bash e ele era
executado mesmo assim; (3) loops de Edit idêntico falhavam para sempre
sem aviso acionável.

## O que foi feito

### 1. Stream respeita `tools` (`bridge_sse.py`)
`_default_reader` montava o payload com `"tools": TOOLS` fixo,
ignorando `body["tools"]` que `call_bridge_stream` já colocava no body.
Corrigido para `body.get("tools") or TOOLS`: dentro da janela de
força-escrita o modelo agora só vê Write/Edit no nível do protocolo.

### 2. Barreira na execução (`harness.py`)
O loop de execução de tool_use agora verifica
`forca_usada and turn <= forca_ate and b["name"] not in ("Write","Edit")`
antes de chamar `run_tool`. Se cair na barreira, o tool NÃO é
executado; o resultado é
`ERRO FORÇA-ESCRITA: neste turno só Write/Edit. Escreva agora a melhor
primeira versão do entregável com o que já leu.`
e o turno conta como não produtivo (igual ao comportamento de vagueio
existente). Defesa em profundidade: mesmo que o modelo ignore a lista
restrita de tools, o efeito colateral não acontece.

### 3. Quebra de loop de Edit idêntico (`harness.py`)
Estado de módulo guarda `(path, hash(old_string))` do último Edit que
falhou e quantas vezes seguidas se repetiu. A partir da 2ª repetição
idêntica, a mensagem de erro ganha sufixo:
`REPETIDO <N>x: este Edit idêntico continuará falhando — NÃO o
repita. Copie o trecho EXATO com sed -n 'A,Bp' ARQ, ou use Write para
reescrever o arquivo/trecho.`
Qualquer outro Edit (old_string diferente) ou um Edit bem-sucedido
zera o contador. O fuzzy match tolerante e a mensagem
`Trecho mais parecido` existentes não foram alterados.

## Testes (`tests/test_forca_escrita2.py`, 9 testes)
- `test_default_reader_respeita_tools_do_body`: monkeypatch de
  `urllib.request.urlopen` captura o payload; `body["tools"]` com só
  Write/Edit ⇒ payload contém exatamente essas duas.
- `test_default_reader_fallback_para_tools_padrao`: sem `tools` no
  body ⇒ payload usa `harness.TOOLS` (o fallback é `TOOLS` importado
  de harness; `bridge_sse` não expõe a constante — o teste antigo
  referenciava o módulo errado).
- `test_bash_na_janela_forca_e_barrado`: 4 turnos de Bash vagueando
  ativam a força-escrita; os Bash seguintes são barrados — nenhum
  `pwned.txt` é criado em lugar nenhum e o trail marca os Bash como
  `is_error`.
- `test_barreira_nao_bloqueia_write_na_janela` / `..._edit_...`:
  Write e Edit dentro da janela executam e a run termina PASS.
- `test_fora_da_janela_bash_executa`: com escrita no 1º turno a
  força-escrita nunca ativa; Bash roda de verdade e cria o arquivo
  da stop condition (veredito PASS).
- `test_repeticao_identica_ganha_aviso`: 1ª falha sem aviso, 2ª e 3ª
  repetições idênticas ganham `REPETIDO 2x`/`3x` com instrução de
  `sed -n`/Write.
- `test_outro_edit_zera_contador`: Edit com old_string diferente zera;
  a nova repetição só ganha aviso na 2ª vez.
- `test_edit_bem_sucedido_zera_contador`: sucesso zera o estado.

## Honestidade / limitações
- A barreira cobre o loop principal de execução de tool_use; se
  existirem outros pontos de execução de tools (ex.: caminhos de
  advisor), não foram auditados nesta missão (advisor está desligado
  nos testes).
- O aviso de REPETIDO é por processo (estado de módulo), não por run;
  runs concorrentes no mesmo processo compartilham o contador. Para o
  uso atual (um processo por run) é suficiente.
- `test_fora_da_janela_bash_executa` valida o caminho feliz via
  efeito real do Bash (arquivo criado no run_dir) e `is_error=False`
  no trail; não há teste negativo de "força-escrita ativa E fora da
  janela" porque a janela expira por contagem de turnos e o roteiro
  de bridge ficaria frágil.
- Durante a missão, um `Write` do arquivo de testes e depois o do
  relatório reportaram sucesso mas o conteúdo em disco permaneceu o
  antigo (causa não diagnosticada — possivelmente cache/estado do
  ambiente); o problema foi contornado reescrevendo via script Python
  com asserts de conteúdo.

## Verificação
- `python3 -m unittest tests.test_forca_escrita2` → OK (9 testes)
- `python3 -m unittest tests.test_forca_escrita tests.test_vagueio
  tests.test_edit_robusto` → OK (14 testes)
- `python3 -m unittest discover -s tests` → OK (251 testes)

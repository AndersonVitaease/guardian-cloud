# RD-HARNESS-FORCA-ESCRITA-01 - Forca-escrita no loop do harness

## Problema
Worker que passa muitos turnos so explorando (Bash/Read) sem nunca escrever o
entregavel: o VAGUEIO-01 abortava a run em 8 turnos de vagueio sem dar chance
de o modelo produzir algo. Aborto cedo demais, entregavel inexistente.

## Solucao
Entre o meio da escada de vagueio (VAGUEIO_TRIGGER // 2) e o aborto, o harness
injeta uma janela de forca-escrita:

- Constante FORCA_ESCRITA (env HARNESS_FORCA_ESCRITA, default 3 turnos; 0 desliga).
- Estado por run: teve_escrita, forca_ate, forca_usada.
- Ativacao (uma unica vez por run, so se nunca houve Write/Edit): quando
  vagueio_streak >= max(2, VAGUEIO_TRIGGER // 2) injeta mensagem no estilo
  NUDGE-FIM ("FORCA-ESCRITA (turno N): ... so Write/Edit disponiveis ..."),
  emite _forca_escrita no trail e escreve no pane.
- Efeito: nos turnos turn <= forca_ate a chamada ao modelo (stream E fallback
  POST) recebe tools=[Write, Edit]; fora da janela, TOOLS completo.
- Aborto adiado: com forca_usada, o aborto por vagueio so dispara em
  VAGUEIO_TRIGGER + FORCA_ESCRITA - da os turnos forçados antes de matar.
- call_bridge ganhou parametro opcional tools=None; None mantem o comportamento
  antigo (mocks de teste que nao aceitam tools seguem funcionando, inclusive no
  fallback except TypeError do bridge_fn).

## Correcoes colaterais honestas
- Durante a integracao o fallback POST ficou fora do except BridgeSseError
  (executava mesmo apos stream com sucesso) e call_bridge repassava tools
  incondicionalmente ao call_bridge_once - quebrou 3 testes existentes
  (backoff x2, stream_always x1). Ambos corrigidos: fallback volta a ser so
  degradacao, e tools so e repassado quando nao-None.
- tests/test_vagueio.py: setUp/tearDown salvam e restauram harness.FORCA_ESCRITA
  (zerando durante esses testes) para garantir o item 6 - sem a flag o
  comportamento e identico ao anterior. Unica edicao em teste existente; sem
  ela o gatilho antigo ficaria adiado.

## Testes
tests/test_forca_escrita.py - 5 testes com bridge mock:
(a) 4 turnos so Bash => _forca_escrita no trail e tools do turno seguinte so
Write/Edit; (b) worker escreve no turno forcado => nao aborta por vagueio;
(c) nao escreve nos 3 turnos forcados => aborta com vagueio;
(d) HARNESS_FORCA_ESCRITA=0 => sem _forca_escrita, aborto no gatilho antigo;
(e) run que ja escreveu antes => nunca ativa.

Suite completa: python3 -m unittest discover -s tests -> OK (242 testes).

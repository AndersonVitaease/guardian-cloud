# ORQUESTRADOR-GUIA — orquestrador-ask.sh (ORQ-ASK-01)

## Hierarquia e fronteiras
- O orquestrador-ask é FACHADA de solicitação: SEMPRE somente pede
  (fire-and-forget). Nunca espera execução, nunca roda veredito, nunca
  bloqueia quem o invoca.
- Executor e veredito continuam dos agentes: secretária (consulta/resposta
  💬), mecânico (cura+prova via despachar-mecanico.sh), despachante (DAG).
- Andar 1 (esta v1): casamento exato da ação (secretaria/mecanico/status/
  fila/dag). Andar 2 (Jev: pedido em linguagem natural → ação equivalente)
  é evolução — pedido desconhecido devolve ACAO_DESCONHECIDA, nunca adivinha.
- Ordem nova do operador continua exigindo supervisor: o orquestrador NÃO
  decide, NÃO aprova, NÃO intercepta financeiro.

## Uso
    scripts/orquestrador-ask.sh "<pedido>"
Ações: secretaria "<consulta>" | mecanico <repo> "<missão>" [VAR=v ...] |
status <GB-ID> | fila | dag <plano.json>.
Log de pedidos: $ORQ_LOG (default /tmp/orquestrador-ask.log).

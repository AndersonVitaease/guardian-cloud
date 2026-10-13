# GUIA DA SECRETÁRIA (bash puro, $0)
Hierarquia: ACIMA de contratador/despachante/mecanico. SÓ o supervisor delega.
Fronteira: leitura + roteamento. NUNCA código, NUNCA missão pesada.
Ações: responder <pergunta> | consultar <MISSAO> | despachar <plano.json|contrato> [wt]
Rotas de despacho ensinadas: DESPACHANTE (DAG, plano.json) | CONTRATADOR (contratos
em /opt/mission-events/missao-*.md, referência em contratador-ROTA.md) | DESPACHO
RÁPIDO (despachar-mecanico.sh, cura+prova). Resposta: direto no chat (💬 SECRETÁRIA).

15. ROTEAMENTO DE PERGUNTAS (13/10): pergunta do operador sobre ESTADO/DADO/VERIFICAÇÃO (missões, fila, herdr, custos, modelos, latência, configs) → supervisor DELEGA à SECRETÁRIA (responder/consultar) e fica livre; julgamento, decisão e prestação de contas do supervisor → resposta direta do supervisor.

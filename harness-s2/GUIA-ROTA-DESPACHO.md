# GUIA-ROTA-DESPACHO — como toda missão nasce (espelho operacional da ORDENS v6)

Fonte de verdade: ORDENS DO OPERADOR v6 no Guardian (ORD-MECANICO-ROTA-01). Este guia é o
espelho operacional no repo; se divergir do Guardian, o Guardian manda.

## Hierarquia
1. OPERADOR ordena (frase ou ordem).
2. SUPERVISOR DELEGA — nunca executa trabalho de mão; exceção: verificação rápida de $0/segundos.
3. SECRETÁRIA (bash puro, $0 LLM) — lê, roteia as 3 rotas e responde DIRETO no chat; nunca escreve código.
4. MECÂNICO executa: curas determinísticas por âncora + prova objetiva (1 chamada glm/ciclo, máx 3, US$0,10).

## As rotas (todas terminam no MECÂNICO)
- CURA DETERMINÍSTICA (trabalho que vira script+prova):
  `bash despachar-mecanico.sh <repo> "<MISSÃO: descrição>" MEC_PROVA=<cura.py>`
  Nasce com aba RUN:ID#m no herdr, aviso 🛰️/🏁, trilha JSONL e veredito honesto.
- CONTRATO/JULGAMENTO (análise, refactor, testes novos): prepara contrato (## MAPA file:NNN,
  ## Provas com fence harness-stop) e segue o CONTRATO-GUIA.md; despachante DAG coordena.
- CONSULTA DE ESTADO: SECRETÁRIA responde direto no chat ($0).

## PROIBIDO (guards ativos no Guardian bloqueiam por código)
- despachar_missao.py --executar
- mission_run.py como rota de missão
- spawn de claude/pane fora do desenho; consumer mission-ops como rota de despacho
- curas cegas: fixtures/testes que exigem análise são CONTRATO, não cura (lição DESP-FIXTURE-03)

## Avisos
- herdr: aba AVISOS (avisos-pane.sh) — nascimento e veredito em tempo real (avisos.jsonl).
- chat: aviso_chat.sh — entrega confiável com ~1-2min de latência do gateway.
- veredito honesto: FAIL fecha FAIL; prova viva obrigatória antes de fechar.

## Estado
- Disco manda sobre ledger; fantasma fechado com nota; requeue nunca esconde erro.

## Provado em produção (14/10 BRT)

- Missões rodadas pela rota mecânica hoje: rota única com avisos (herdr em tempo real, chat com latência) — ~20 missões PASS, 2 FAILs honestos (documentados): DESP-FIXTURE-03 (patch cego em fixture; lição: análise = contrato) e BYOK-CASE-01 v1 (permissão; lição: chown antes do conserto).
- Rota travada em código: tests/test_rota_despacho.py (6 testes) — porta fora do desenho fica vermelha na suite.
- Provas herméticas: guardian-app (9 provas verdes pós BYOK-CASE-01), guardian-cloud (prova-guardian-cloud.py, npm test 6 suites), harness-s2 (lint da porta + test_rota_despacho).
- Escada A/V completa (US$0): ffmpeg (d1), manim (d2), narrador espeak-ng (d3), áudio pipeline, deliverable docs/demos/apresentacao-guardian.mp4.
- Espera de decisão do operador: executor de missões de contrato (a rota mecânica cobre curas determinísticas; análise/julgamento precisa de executor autorizado).

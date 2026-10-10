# RD-HARN-FATIA-AUTO-04 — mapa relevante por fatia

## O que estava quebrado
O `## MAPA` gerado por `scripts/fatiar_auto.py` era irrelevante: sobre o contrato real `missao-rd-gb-abuse-01c.md` (repo `wt-RD-GB-ABUSE-01D`), a fatia do rate-limit global apontava `BRIDGE_FAKE` (`server.js:86`, constante de ambiente sem relação) e `/api/` (`prova-abuse01.py:2`, linha de docstring), em vez das âncoras reais (`rateLimit` em `server.js`, `dbRateLimit` em `db.mjs`). Além disso, o agrupamento guloso antigo colapsava as 5 entregas em 2 fatias, reprovando o aceite v1 (`poucas fatias`).

## O que foi feito (scripts/fatiar_auto.py)
1. **Candidatos**: só entram termos que a própria entrega cita entre crases, reduzidos ao identificador (`dbm.dbRateLimit(ip,'api',30,1)` vira `dbRateLimit`; `rateLimit(dbm, req, 'api', 60)` vira `rateLimit`). Constante ALL_CAPS e termos genéricos (`/api/`, `body`, `req`, `res`) ficam de fora salvo citação literal entre crases.
2. **Localização**: prefere linha de definição (`function nome`, `async function nome`, `const nome =`, `export function nome`, `def nome`, `nome(` em export) sobre usos; nunca aponta comentário/docstring (`#`, `//`, `*`, `/*`, aspas-triplas). Se nenhum termo é localizável, a fatia sai com `(sem âncoras: arquivo novo)` + primeiro arquivo `.js/.mjs/.py` citado (satisfaz o lint).
3. **Agrupamento**: uma entrega só herda a fatia anterior se não trouxer âncoras novas (termos próprios citados entre crases) — isso restaurou 3 fatias no contrato real, cada uma com mapa próprio e relevante, mantendo DAG serial e determinismo.

## Resultado (contrato real, repo wt-RD-GB-ABUSE-01D)
- S1: `server.js:124` `rateLimit`, `server.js:126` `dbRateLimit` (definições).
- S2: `server.js:316` `tosAccepted`, `server.js:322` `tos_accepted_at` (+ provas).
- S3: `app.js:430` `tosAccepted`, `prova-tools-bash01.py:120` `tosAccepted`.

## Veredito honesto
- `BRIDGE_FAKE` e `/api/` sumiram do mapa; nenhuma linha de comentário/docstring é apontada.
- Limitação conhecida: a preferência por definição é heurística por regex (sem parser); se o termo só existir em uso, aponta a primeira ocorrência de código — aceitável para o contrato-alvo.
- Aceites v1/v2/v3 verdes; suíte `unittest discover` OK; saída determinística (digest idêntico entre rodadas).

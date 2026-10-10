# RD-HARN-FATIA-AUTO-05 — Relatório

## Contexto
O `## MAPA` gerado por `scripts/fatiar_auto.py` ainda apontava âncoras irrelevantes
(`BRIDGE_FAKE` em `server.js:86`, `/api/` em docstring) ao rodar sobre o contrato real
`/opt/mission-events/missao-rd-gb-abuse-01c.md` com repo `/home/worker/wt-RD-GB-ABUSE-01D`,
em vez das âncoras corretas (`rateLimit` em `server.js`, `dbRateLimit` em `db.mjs`,
`tosAccepted`/`tos_accepted_at`).

## O que foi feito
Trabalho herdado do checkpoint WIP (commit 6bcfe058) e consolidado:

- `candidatos_da_entrega`: só entram termos citados entre crases, reduzidos ao
  identificador (sem `dbm.`, sem argumentos); ALL_CAPS só se a crase cita a constante
  em si; termos genéricos (`/api/`, `body`, `req`, `res`) nunca entram.
- `COMENT_LINHA_RE` + `eh_definicao`: linha de comentário/docstring (`#`, `//`, `*`,
  `/*`, `"""`) nunca é âncora; definição (`function nome`, `async function nome`,
  `const nome =`, `def nome`, `export ... nome(`) é preferida sobre usos; sem
  definição, a primeira ocorrência de código.
- `localizar`: escolha (rel, linha, símbolo) com preferência por definição;
  candidato sem ocorrência no repo simplesmente não entra.
- `tokens_da_entrega`: tokens amplos usados apenas para escolha de arquivos, nunca
  para o mapa.
- Se nenhum termo for localizável, a fatia sai com `## MAPA` `(sem âncoras: arquivo
  novo)` + primeiro `.js/.mjs/.py` citado (satisfaz o lint).

## Validação
- `python3 -m py_compile scripts/fatiar_auto.py` — OK.
- `tests/accept_fatia_auto3.py` — `ACEITE-FATIA-AUTO3 OK` (âncoras reais, sem
  comentário, sem constante solta).
- `tests/accept_fatia_auto.py` / `accept_fatia_auto2.py` — OK (v1 e v2 verdes).
- `python3 -m unittest discover -s tests` — OK, determinístico.

## Honestidade / limitações
- O aceite v3 cobre o contrato real do rate-limit/ToS; não houve caso de teste com
  repo sem nenhuma âncora localizável além do caminho do lint.
- A preferência por definição é heurística textual; export indireto
  (`module.exports = { nome }` sem `nome(`) não é detectado como definição.
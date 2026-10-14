# MISSÃO HARNESS-SPRINT6-CANARY-01 — canária E2E do executor novo (sprint 6, item 4)

Prova o **stop-check tolerante a formato** (entrega 1): a última linha do
`STATUS.txt` usa o reporter TAP com o símbolo **ℹ SEM # — de propósito**; o
stop tem que engatar do mesmo jeito. Criar tudo **do zero** no cwd da run
(vazio). PT-BR. Seed desta run: {{SEED}}.

## Entregáveis (todos no cwd da run)

1. `NOTES.md` — ≥3 linhas: título `# NOTES`, a data de hoje em **formato
   AAAA-MM-DD** (uma linha só com a data), e 1 linha dizendo o que esta
   canária prova (stop tolerante a formato de reporter).
2. `STATUS.txt` — 2 linhas: 1ª com a data de hoje (AAAA-MM-DD); última linha
   EXATAMENTE `ℹ fail 0` (reporter TAP, símbolo ℹ, SEM # — de propósito).
3. Por último, `RELATORIO.md` — 3+ linhas com o que foi feito e a linha
   `Veredito: PASS` e depois dela a linha `PARE` (só escreva depois do
   verificador abaixo engatar).

Verificador (rode você mesmo antes do relatório): `cat STATUS.txt`

```harness-stop
file NOTES.md
file STATUS.txt
file RELATORIO.md
cmdout fail 0 :: cat STATUS.txt
marker PASS RELATORIO.md
```

## Regras

budget US$ 0.50; max-turns 20; sem copiar artefatos de outras runs.

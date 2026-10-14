# Manual de operação — `--auto-retry`

## O que é
Retry sequencial automático de missões FAIL. Em caso de FAIL, extrai o bloco
"DIAGNÓSTICO PRÉVIO" do trail da tentativa anterior (`mission_run.extrair_memoria`)
e re-tenta com essa memória injetada no kickoff, seed+1, cwd novo
(`tentativa-<k>/`) e budget restante. Hard-cap: **4 tentativas (1 + 3 retries)**.

## Quando usar / quando NÃO usar
- **Usar:** FAIL com trabalho parcial herdável (o diagnóstico do trail pode
  destravar a próxima tentativa).
- **Não usar:** FAIL estrutural (contrato insatisfazível, erro de setup,
  permissão) — o retry queima centavos à toa, pois nenhuma memória resolve
  o problema. Exemplo real: contrato com alvo impossível de satisfazer
  falhou nas 2 tentativas e só gastou budget duplicado.

## Como despachar
```bash
python mission_run.py --mission <contrato.md> --cwd <dir> --budget 1.0 \
  --max-turns 30 --auto-retry 1
```
`--auto-retry N` = até N re-tentativas após a primeira (cap 3).

## Como ler o agregado (`autoretry-summary.json`)
- `veredito`: veredito final (última tentativa);
- `tentativas`: quantidade executada;
- `vereditos_por_tentativa`: lista, ex. `["FAIL", "PASS"]`;
- `custo_total`: USD somado de todas as tentativas (budget compartilhado —
  cada tentativa recebe `budget_total - já gasto`);
- `runs`: resumos individuais.

## Trava conhecida
`--auto-retry` + `--memoria` = **erro** (exit 2): o retry gera a própria
memória do trail da tentativa anterior; passar `--memoria` junto cria
conflito de fontes. Use apenas `--auto-retry`.

## Exemplo real de uso (hoje)
A missão da escada rodou com `--auto-retry 1`: tentativa 1 FAIL, tentativa 2
herdou o diagnóstico prévio e PASSou; agregado gravado em
`autoretry-summary.json` com `vereditos_por_tentativa: ["FAIL", "PASS"]`.

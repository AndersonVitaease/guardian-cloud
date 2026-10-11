# MISSÃO RD-METRICA-VALOR-01 — fecho ganha bloco "valor" no ledger

Fonte: ROADMAP.md linha 63.

## Contexto

O fecho de missão (missao_fechar.sh, na RAIZ do repo — o mesmo script que roda em
/opt/mission-events/tools-bash via deploy) grava no ledger só o fechamento
(administrativo): status/veredito/custo. O operator pediu que o fecho capture VALOR:
o que a missão destravou no roadmap e o custo evitado.

Ponto exato: missao_fechar.sh, passo 4 (comentário "--- passo 4: ledger/merge ---",
~L107): o bloco python que abre o ledger ($LEDGER_DIR/$MISSION_ID.json) e grava
{"fechado": true, "abas": [...], "suite_ok": ...} (~L109-124). É ali que o bloco
"valor" entra.

## Tarefa

1. No passo 4 do missao_fechar.sh: se existir /opt/mission-events/ROADMAP.md
   (caminho via env ROADMAP_PATH com default), compute:
   - destravou: contagem de linhas do roadmap cujo campo Dependências cita o
     mission_id passado (grep -c no texto do ID dentro de linhas com "|"), e a
     lista dos IDs dessas linhas (5ª coluna da tabela — extrair com python, split
     por "|", índice 1 do split = ID).
   - custo_usd e turnos: do /tmp/resumo-<ID>.json se existir (custo_total,
     tentativas; ausente → null).
   Grave no ledger: state["valor"] = {"destravou": N, "destravou_ids": [...],
   "custo_usd": X, "turnos": Y, "computed_at": iso}.
   Best-effort: qualquer erro (roadmap ausente, resumo ausente) → valor com
   {"erro": "<errortipado>"} — NUNCA derruba o fecho (fecho continua exit 0).
2. Exercite a lógica pura com python3 -c (sem tocar /opt): dada uma tabela de
   exemplo em /tmp, prove extração correta de IDs dependentes.
3. Rode a suíte de testes do repo referente ao fecho: bash tools-bash/test_missao_fechar.sh
   (ou tests/ equivalente — procure com code_find). Suite verde exigida; falha
   PRÉ-EXISTENTE em baseline deve ser declarada no relatório com nome exato.

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escrita em arquivo: direto no caminho destino (Write), NUNCA intermediário
  .tmp/.sh + mv/cp; nunca código em /tmp.
- Todo stop roda `cd /home/worker/wt-RD-METRICA-VALOR-01 &&` primeiro.
- Sem cat/head/tail/ls/find/grep -oE/sed -i/awk soltos: code_find/code_slice/
  file_peek, grep -n COM PIPE, python3 para JSON.
- Máximo 3 linhas de ferramenta por turno.
- Commit como worker com o ID no subject; git add restrito; NUNCA git
  reset/checkout/stash/clean; fecho/merge/deploy em /opt é do supervisor.

## Stops (condições de parada)

```harness-stop
cmd cd /home/worker/wt-RD-METRICA-VALOR-01 && test -f RELATORIO-RD-METRICA-VALOR-01.md
cmd cd /home/worker/wt-RD-METRICA-VALOR-01 && grep -q -F 'RD-METRICA-VALOR-01' RELATORIO-RD-METRICA-VALOR-01.md
cmd cd /home/worker/wt-RD-METRICA-VALOR-01 && grep -q -F 'VALOR-OK' RELATORIO-RD-METRICA-VALOR-01.md
cmd cd /home/worker/wt-RD-METRICA-VALOR-01 && grep -q 'valor' missao_fechar.sh
```

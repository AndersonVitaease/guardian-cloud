# MISSÃO GB-FUNIL-UNICO-01

Fonte: FIND-funil-despacho-1012 (P1) + ROADMAP.md linha 474. Operator 12/10: "todos esses despacham missões" — porta única exigida.

Objetivo: consolidar a PORTA ÚNICA de despacho com mecanismo, não cláusula. Hoje: despachar_missao.py (harness) tem a trava de espelho nativa; a cópia do consumer foi sincronizada à mão (regressão se alguém editar um e não o outro); espelho.sh/despacha_missao.sh legados só têm banner.

## MAPA
- scripts/despachar_missao.py:120-135 — trava DESPACHO-UNICO (espelho nativo, fail-closed ESPELHO_NAO_NASCEU). FATIA A de referência.
- Extraia a trava para módulo compartilhado: crie `scripts/espelho_nativo.py` (função `nascer_espelho(mid)` + `pousar_espelho(mid)`) e faça despachar_missao.py importá-la (substituindo o bloco inline).
- A CÓPIA DO CONSUMER do despachante (mantida fora do repo, supervisor aplica) — NÃO edite lá (worker não escreve fora do worktree): deixe em CONTRATO-APLICACAO.md a instrução de cópia 1:1 pelo supervisor + teste de igualdade (sha256 do arquivo do repo vs cópia de referência em fixtures).
- test_funil_unico.py (novo): (a) importa espelho_nativo e valida nascer/pousar criando/renomeando espelho em tmpdir (env ESP_DIR overridable — a função aceita dir por parâmetro); (b) valida que despachar_missao.py chama espelho_nativo (grep do import no fonte); (c) valida sha256 de scripts/despachar_missao.py vs uma cópia de referência fornecida em fixtures/despachar_missao.expected.py (copie o arquivo atual para fixtures ANTES de editar).
- O script de guard de ordens NÃO edite (é governado) — em CONTRATO-APLICACAO.md, peça ao supervisor: bloquear nascimento pelos wrappers legados no guard.

## REGRAS
- Escreva arquivos novos via Bash python3 heredoc (Write confinado ao run-dir). Edit em despachar_missao.py: `sed -n '110,140p' scripts/despachar_missao.py` imediatamente antes, old_string literal de UMA linha.
- PROIBIDO: git reset/checkout/stash/clean; sudo; cat/head/ls; editar a cópia em /opt.
- Commit: `git add scripts/espelho_nativo.py scripts/despachar_missao.py test_funil_unico.py fixtures/despachar_missao.expected.py CONTRATO-APLICACAO.md && git commit -m "GB-FUNIL-UNICO-01: porta unica de despacho (espelho nativo em modulo compartilhado + teste de sincronia)"`

## PROVA
```harness-stop
cmd cd /home/worker/wt-GB-FUNIL-UNICO-01 && python3 test_funil_unico.py
cmd cd /home/worker/wt-GB-FUNIL-UNICO-01 && python3 test_funil_unico.py | grep -q 'GB-FUNIL-UNICO-01-PROVA-OK'
cmd cd /home/worker/wt-GB-FUNIL-UNICO-01 && test -f CONTRATO-APLICACAO.md
cmd cd /home/worker/wt-GB-FUNIL-UNICO-01 && test "$(git log -1 --format=%s)" = "GB-FUNIL-UNICO-01: porta unica de despacho (espelho nativo em modulo compartilhado + teste de sincronia)"
```
# MISSÃO RD-DESP-TAB-SILENT-01

Fonte: ROADMAP.md linha 519 (RD-DESP-TAB-SILENT-01, prio 2). Dor viva 13/10:
despacho da GB-THUMB-02C logou "tab criada sem pane-id extraível; seguindo SEM
espelho" em silêncio. O lado despachar_missao.py:232-242 JÁ cura (PANE_AUSENTE +
stop da unit) — NÃO toque nele. Falta o lado do mount-espelho.sh.
Repo: harness-s2, worktree este (base gb-backup-01).

## TAREFA 1 — scripts/mount-espelho.sh
Hoje a linha ~30 extrai pane_id sem validar:
  PANE_ID="$(printf '%s' "${TAB_JSON}" | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['root_pane']['pane_id'])")"
Se o JSON nao tem result.root_pane.pane_id, o python explode, PANE_ID fica vazio
e o script segue em silêncio (bug). Corrija 1:1: extraia com try/except que sai
exit 1, e se a substituicao falhar ou vier vazia, imprima TAB_SEM_PANE no stderr
e exit 1 (o `||` protege da set -e). Nenhuma outra linha muda.

## TAREFA 2 — tests/test_mount_espelho.sh (ARQUIVO NOVO, Write inteiro)
Prova hermetica bash, sem rede, <20s:
1. SCRATCH=$(mktemp -d); crie arvore fake de run:
   $SCRATCH/runs/M-TESTE/tentativa-1/run-20261013-000000-seed77-abc/harness-pane.log
2. Stub herdr em $SCRATCH/bin/herdr (chmod 755; use tests/test_espelho.sh:147
   como modelo de stub): `tab create` le o modo de $SCRATCH/modo.txt e imprime:
   - 'com-pane': {"result":{"root_pane":{"tab_id":"stub:t1","pane_id":"stub:p1","workspace_id":"stub:ws"}}}
   - 'sem-pane': {"result":{"root_pane":{"tab_id":"stub:t1","workspace_id":"stub:ws"}}}
   `pane run` so grava os args em $SCRATCH/pane-run.log (exit 0).
3. Caso sem-pane: PATH=$STUB:$PATH bash scripts/mount-espelho.sh "$SCRATCH/runs/M-TESTE/tentativa-1/run-*" 77 M-TESTE
   deve exit != 0 e saida conter TAB_SEM_PANE. check tipado.
4. Caso com-pane (outro SCRATCH): deve exit 0 e saida conter stub:p1. check tipado.
5. Ao fim imprima RD-DESP-TAB-SILENT-01-PROVA-OK (só se todos os checks passarem).

## MAPA
- scripts/mount-espelho.sh:28 (TAB_JSON=herdr tab create)
- scripts/mount-espelho.sh:30 (PANE_ID=extracao sem validacao — o alvo)
- tests/test_espelho.sh:147-148 (modelo de stub herdr; NAO edite esse arquivo)
- tests/test_mount_espelho.sh:1 (novo — Write inteiro, path do worktree)

## PROVA (stop)
```harness-stop
cmd cd /home/worker/wt-RD-DESP-TAB-SILENT-01 && bash tests/test_mount_espelho.sh 2>&1 | grep -q -F 'RD-DESP-TAB-SILENT-01-PROVA-OK'
cmd cd /home/worker/wt-RD-DESP-TAB-SILENT-01 && grep -q -F 'TAB_SEM_PANE' scripts/mount-espelho.sh
cmd cd /home/worker/wt-RD-DESP-TAB-SILENT-01 && git log -1 --format=%s | grep -q -F 'RD-DESP-TAB-SILENT-01'
cmd cd /home/worker/wt-RD-DESP-TAB-SILENT-01 && test -z "$(git status --porcelain)"
```

## REGRAS
Proibido git reset/checkout/stash/clean; sem sudo; sem Edit/Write com path
absoluto (cd worktree + heredoc python3 - <<'EOF' para escrever arquivos);
rode a prova como worker; comando falhou 2x → NAO repita: ls e adapte.
Dúvida do spec: ask_ai_service e pare; nao improvise. Budget US$0,15.
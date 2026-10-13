# MISSÃO FECHO-ROADMAP-01

Fonte: ROADMAP.md (item FECHO-ROADMAP-01, prio 1, operator 13/10). 3 missoes
fechadas 12-13/10 seguiram NAO INICIADO no roadmap. Repo: harness-s2, este
worktree (base gb-backup-01). Modelo vendored-patch: o alvo real
(/opt/mission-events/tools-bash/missao_fechar.sh, root-owned) esta copiado em
vendored/missao_fechar.sh — trabalhe SOBRE A COPIA, nunca em /opt.

## TAREFA 1 — vendored/roadmap_fechar_estado.sh (ARQUIVO NOVO, Write inteiro)
Script bash padrao tools-bash: JSON 1 linha no stdout, exit 0 sempre, falha
tipada. Uso: roadmap_fechar_estado.sh <MISSION_ID> [ROADMAP_PATH]
(default /opt/mission-events/ROADMAP.md).
1. ROADMAP ausente -> {"ok":false,"erro":"ROADMAP_AUSENTE","id":...}
2. Linha do ID: a que comeca por '- **<MISSION_ID> (prio'. Nao existe ->
   {"ok":true,"id":...,"acao":"noop"} (fail-open, sem tocar o arquivo).
3. Existe -> python inline substitui SOMENTE nessa linha o segmento
   '— estado <ate a proxima , ou fim>' por
   '— estado ATUALIZADA-FECHO <veredito> <YYYY-MM-DD HH:MM BRT>' (veredito vem
   de /tmp/resumo-<ID>.json campo veredito; sem resumo -> FAIL_SEM_RESUMO).
   Preserva o resto da linha (Fila=, fonte, etc). Grava o arquivo e devolve
   {"ok":true,"id":...,"acao":"atualizada","veredito":...}.
Horario BRT (TZ=America/Sao_Paulo). Nao use sudo.

## TAREFA 2 — wiring em vendored/missao_fechar.sh
Apos o bloco python do passo 4 (ledger/merge, termina com 'PYEOF' seguido de
'# --- saida'), insira UMA chamada fail-open:
  ROADMAP_FECHO=$(bash "$(dirname "${BASH_SOURCE[0]}")/roadmap_fechar_estado.sh" "$MISSION_ID" 2>/dev/null || true)
Nao altere nada mais do script.

## TAREFA 3 — tests/test_fecho_roadmap.sh (ARQUIVO NOVO, Write inteiro)
Prova hermetica bash, ROADMAP_PATH apontando para fixture em mktemp:
(a) fixture com linha '- **M-TESTE (prio 1)** — coisa — estado NAO INICIADO, Fila=nao'
    -> roda o script; estado vira 'ATUALIZADA-FECHO' e 'Fila=nao' preservado;
(b) ID ausente -> acao noop, arquivo intocado;
(c) ROADMAP_PATH inexistente -> ROADMAP_AUSENTE.
Todos os checks passando -> imprima FECHO-ROADMAP-01-PROVA-OK.

## MAPA
- vendored/missao_fechar.sh:167 ('# --- passo 4: ledger/merge')
- vendored/missao_fechar.sh:233 (fim do bloco python do passo 4 — insira depois)
- vendored/roadmap_fechar_estado.sh:1 (novo)
- tests/test_fecho_roadmap.sh:1 (novo)

## PROVA (stop)
```harness-stop
cmd cd /home/worker/wt-FECHO-ROADMAP-01 && bash tests/test_fecho_roadmap.sh 2>&1 | grep -q -F 'FECHO-ROADMAP-01-PROVA-OK'
cmd cd /home/worker/wt-FECHO-ROADMAP-01 && grep -q -F 'roadmap_fechar_estado.sh' vendored/missao_fechar.sh
cmd cd /home/worker/wt-FECHO-ROADMAP-01 && git log -1 --format=%s | grep -q -F 'FECHO-ROADMAP-01'
cmd cd /home/worker/wt-FECHO-ROADMAP-01 && test -z "$(git status --porcelain)"
```

## REGRAS
Proibido git reset/checkout/stash/clean; sem sudo; sem Write/Edit com path
absoluto (cd worktree + heredoc); comando falhou 2x → NAO repita: ls e adapte.
Dúvida do spec: ask_ai_service e pare; nao improvise. Budget US$0,15.
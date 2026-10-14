# RELATORIO-GB-BACKUP-01 — backup diário da fábrica

Marcador: BACKUP-01-OK

## Entregas

1. `scripts/backup_fabrica.sh` — empacota tar.gz com data BRT no nome
   (`fabrica-YYYYMMDD.tar.gz`) em `$BACKUP_DIR` (default `/home/worker/backups`):
   - (a) repos git `guardian-app`, `harness-s2`, `agent-office`:
     um `git bundle` por repo contendo todas as branches + tags
     (`git bundle create X.bundle --branches --tags`) + patch de working tree
     suja via `git diff HEAD` (patch vazio não entra no pacote).
     Aceita repo comum (`.git` dir) e worktree (`.git` arquivo → gitdir externo,
     caso do guardian-app).
   - (b) `$HERMES_HOME/state.db` + `$HERMES_HOME/profiles/*/state.db`,
     copiados como `.db-flat` com cópia ONLINE de sqlite — `sqlite3 '.backup'`
     quando o CLI existe, senão API de backup do módulo `sqlite3` do python3
     (nunca cp cru de db em escrita; nesta máquina não há sqlite3 CLI → via python3).
   - (c) `$HERMES_HOME/skins` + `$HERMES_HOME/profiles/*/config.yaml` + `$HERMES_HOME/skills`.
   - Retenção: mantém os últimos 7 diários + até 4 semanais (semanal = data BRT
     do nome cai numa segunda-feira); apaga o resto. Falha na retenção não
     derruba o backup do dia.
   - Sucesso: exatamente 1 linha JSON em stdout `{"ok":true,"arquivo":...,"bytes":...}`.
   - Falha: código tipado `BACKUP_<X>` (NO_GIT, NO_TAR, NO_PYTHON, NO_STAGE, NO_DIR,
     NO_REPO, BUNDLE, DIFF, NO_DB, DB, COPY, TAR), diagnóstico em stderr.
   - Gancho de teste: `BACKUP_DATE=YYYYMMDD` sobrescreve a data BRT (só para provas).
2. Provas em `scripts/prova-backup-01-fase1.sh` e `scripts/prova-backup-01-fase2.sh`
   (herméticas: tempdir + HERMES_HOME fake).

## Provas (RESUMO: 0 falhas)

- `bash -n scripts/backup_fabrica.sh` → limpo.
- Fase 1 (hermética): tempdir como BACKUP_DIR + HERMES_HOME fake (state.db com
  tabela+linha, profile db, config.yaml, skills, skins) → tar criado contendo os 3
  bundles, `state.db-flat`, `despachante.state.db-flat`, config.yaml, skills e skins;
  db-flat extraído do tar reaberto via sqlite com a linha intacta; JSON ok com bytes>0;
  segunda rodada com `BACKUP_DATE=20261013` criou o arquivo do dia seguinte.
- Fase 2 (hermética): 14 rodadas simuladas (20260929..20261012) em BACKUP_DIR limpo →
  restam exatamente 8 arquivos: 7 diários (20261006..20261012) + 20261005 (segunda-feira,
  semanal); 6 antigos removidos. RETENCAO_OK.
- Tiro real (defaults): `/home/worker/backups/fabrica-20261012.tar.gz`, 35.704.911 bytes,
  contendo guardian-app.bundle, harness-s2.bundle, agent-office.bundle,
  hermes/state.db-flat, 3x profiles/*.state.db-flat, 3x profiles/*.config.yaml,
  skills/ e skins/ completos.

## Limitações conhecidas (por desenho)

- Patch só cobre mudanças TRACKED (`git diff HEAD`); arquivos não-rastreados não entram.
- Retenção: semanas definidas por data de segunda-feira no nome; janela de 4 semanais
  só satura após ~4 semanas de históricos de segunda.
- Não instala cron/systemd — agendamento é supervisor-side (comando sugerido:
  `BACKUP_DIR=/home/worker/backups /home/worker/harness-s2/scripts/backup_fabrica.sh`
  diário, horário BRT).

## Regras respeitadas

Sem git reset/checkout/stash/clean, sem sudo, sem escrita em /root ou /opt;
nenhum toque em espelho.sh (outro agente); PT-BR; horários BRT.
#!/usr/bin/env bash
# GB-BACKUP-01: backup diário da fábrica (guarda contra desastre).
#
# Empacota tar.gz com data BRT no nome -> $BACKUP_DIR (default /home/worker/backups):
#   (a) repos git: guardian-app, harness-s2, agent-office
#       (git bundle com todas as branches + patch de working tree suja via git diff HEAD)
#   (b) $HERMES_HOME/state.db e $HERMES_HOME/profiles/*/state.db
#       (cópia .db-flat online via sqlite3 CLI '.backup' se disponível, senão
#        via API de backup do módulo sqlite3 do python3 — nunca cp cru de db em escrita)
#   (c) $HERMES_HOME/skins + $HERMES_HOME/profiles/*/config.yaml + $HERMES_HOME/skills
#
# Retenção: mantém últimos 7 diários + 4 semanais (semanal = arquivo cuja data BRT
# cai numa segunda-feira); apaga o resto.
#
# Sucesso: imprime exatamente 1 linha em stdout: {"ok":true,"arquivo":...,"bytes":...}
# Falha:   sai com código tipado BACKUP_<X>, diagnóstico em stderr.
#
# Ganchos de teste (não usar em produção): BACKUP_DATE=YYYYMMDD sobrescreve a data BRT.
#
# PROIBIDO aqui: git reset/checkout/stash/clean, sudo, escrita em /root ou /opt.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/home/worker/backups}"
HERMES_HOME="${HERMES_HOME:-/home/worker/.hermes}"
REPOS_BASE="${REPOS_BASE:-/home/worker}"
REPOS=(guardian-app harness-s2 agent-office)
KEEP_DAILY=7
KEEP_WEEKLY=4

fail() {
  # fail BACKUP_<CODIGO> "mensagem"
  echo "[backup_fabrica] FALHA $1: $2" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail BACKUP_NO_GIT "git não encontrado"
command -v tar >/dev/null 2>&1 || fail BACKUP_NO_TAR "tar não encontrado"
command -v python3 >/dev/null 2>&1 || fail BACKUP_NO_PYTHON "python3 não encontrado (necessário p/ cópia online de db)"

if command -v sqlite3 >/dev/null 2>&1; then
  DB_MODE=sqlite3-cli
else
  DB_MODE=python-sqlite3
fi

copy_db_online() {
  # copy_db_online <origem> <destino> — cópia consistente de sqlite em escrita.
  local src="$1" dst="$2"
  if [[ "$DB_MODE" == sqlite3-cli ]]; then
    sqlite3 "$src" ".backup '$dst'"
  else
    SRC_DB="$src" DST_DB="$dst" python3 - <<'PYEOF'
import os, sqlite3
src, dst = os.environ["SRC_DB"], os.environ["DST_DB"]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
PYEOF
  fi
}

NOW_DATE="${BACKUP_DATE:-$(TZ=America/Sao_Paulo date +%Y%m%d)}"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/fabrica-backup.XXXXXX")" || fail BACKUP_NO_STAGE "mktemp falhou"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$BACKUP_DIR" || fail BACKUP_NO_DIR "não criou $BACKUP_DIR"

# ---------- (a) repos git ----------
for repo in "${REPOS[@]}"; do
  path="$REPOS_BASE/$repo"
  # aceita repo comum (.git dir) e worktree (.git arquivo -> gitdir externo)
  { [[ -d "$path/.git" ]] || [[ -f "$path/.git" ]]; } || fail BACKUP_NO_REPO "repo ausente: $path"
  ( cd "$path" && git bundle create "$STAGE/$repo.bundle" --branches --tags >/dev/null 2>&1 ) \
    || fail BACKUP_BUNDLE "git bundle falhou em $repo"
  ( cd "$path" && git diff HEAD > "$STAGE/$repo.patch" ) \
    || fail BACKUP_DIFF "git diff falhou em $repo"
  # patch vazio não vai pro pacote
  [[ -s "$STAGE/$repo.patch" ]] || rm -f "$STAGE/$repo.patch"
done

# ---------- (b) bancos sqlite ----------
[[ -f "$HERMES_HOME/state.db" ]] || fail BACKUP_NO_DB "db ausente: $HERMES_HOME/state.db"
mkdir -p "$STAGE/hermes/profiles"
copy_db_online "$HERMES_HOME/state.db" "$STAGE/hermes/state.db-flat" \
  || fail BACKUP_DB "cópia online falhou: state.db"
for prof in "$HERMES_HOME"/profiles/*/; do
  [[ -f "$prof/state.db" ]] || continue
  name="$(basename "$prof")"
  copy_db_online "$prof/state.db" "$STAGE/hermes/profiles/$name.state.db-flat" \
    || fail BACKUP_DB "cópia online falhou: profiles/$name/state.db"
done

# ---------- (c) skins, config.yaml, skills ----------
if [[ -d "$HERMES_HOME/skins" ]]; then
  cp -r "$HERMES_HOME/skins" "$STAGE/hermes/skins" || fail BACKUP_COPY "cópia de skins falhou"
fi
for cfg in "$HERMES_HOME"/profiles/*/config.yaml; do
  [[ -f "$cfg" ]] || continue
  name="$(basename "$(dirname "$cfg")")"
  cp "$cfg" "$STAGE/hermes/profiles/$name.config.yaml" || fail BACKUP_COPY "cópia de config.yaml ($name) falhou"
done
[[ -d "$HERMES_HOME/skills" ]] && cp -r "$HERMES_HOME/skills" "$STAGE/hermes/skills"

# ---------- empacota ----------
ARQ="$BACKUP_DIR/fabrica-$NOW_DATE.tar.gz"
tar -czf "$ARQ" -C "$STAGE" . || fail BACKUP_TAR "tar falhou"
BYTES="$(stat -c %s "$ARQ")"

# ---------- retenção: últimos 7 diários + 4 semanais ----------
# Semanal = data (BRT) do nome cai numa segunda-feira.
for f in "$BACKUP_DIR"/fabrica-*.tar.gz; do
  [[ -f "$f" ]] || continue
  d="$(basename "$f")"; d="${d#fabrica-}"; d="${d%.tar.gz}"
  [[ "$d" =~ ^[0-9]{8}$ ]] || continue
  if ! python3 -c "import datetime,sys; datetime.datetime.strptime(sys.argv[1],'%Y%m%d')" "$d" 2>/dev/null; then
    continue
  fi
  printf '%s\n' "$d"
done | sort -r > "$STAGE/.datas"
# mantém os 7 mais recentes sempre; dos mais antigos, guarda as segundas-feiras (4)
python3 - "$BACKUP_DIR" "$STAGE/.datas" "$KEEP_DAILY" "$KEEP_WEEKLY" <<'PYEOF'
import datetime, os, sys
bdir, datas_f, kd, kw = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
datas = [l.strip() for l in open(datas_f) if l.strip()]
matar = datas[kd:]                      # fora dos 7 diários mais recentes
semanais = [d for d in matar
            if datetime.datetime.strptime(d, "%Y%m%d").weekday() == 0]
guardar = set(semanais[:kw])
for d in matar:
    if d in guardar:
        continue
    p = os.path.join(bdir, f"fabrica-{d}.tar.gz")
    if os.path.exists(p):
        os.remove(p)
PYEOF
# ^ sem falha tipada: retenção não derruba o backup do dia.

echo "{\"ok\":true,\"arquivo\":\"$ARQ\",\"bytes\":$BYTES}"
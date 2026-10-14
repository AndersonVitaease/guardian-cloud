#!/usr/bin/env bash
# Prova hermética GB-BACKUP-01: fase 1 (tar criado, conteúdo, JSON, 2 rodadas).
set -euo pipefail
S="$1"           # dir da prova
REPO="$2"        # repo harness-s2
mkdir -p "$S/BACKUP_DIR" "$S/fake_hermes/profiles/despachante" "$S/fake_hermes/skills/skill_a" "$S/fake_hermes/skins/dark"
python3 - "$S" <<'PYEOF'
import sqlite3, sys, os
s = sys.argv[1]
db = f"{s}/fake_hermes/state.db"
c = sqlite3.connect(db); c.execute("create table t(x)"); c.execute("insert into t values (1)"); c.commit(); c.close()
p = f"{s}/fake_hermes/profiles/despachante/state.db"
c = sqlite3.connect(p); c.execute("create table t(x)"); c.commit(); c.close()
open(f"{s}/fake_hermes/profiles/despachante/config.yaml","w").write("perfil: despachante\n")
open(f"{s}/fake_hermes/skills/skill_a/SKILL.md","w").write("teste\n")
open(f"{s}/fake_hermes/skins/dark/theme.css","w").write("body{}\n")
PYEOF
export HERMES_HOME="$S/fake_hermes" BACKUP_DIR="$S/BACKUP_DIR"
OUT1=$(cd "$REPO" && BACKUP_DATE=20261012 ./scripts/backup_fabrica.sh)
echo "OUT1=$OUT1"
T1=$(printf '%s' "$OUT1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["arquivo"])')
echo "-- conteudo tar1 --"
tar -tzf "$T1" | sort
printf '%s' "$OUT1" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] is True and d["bytes"]>0; print("JSON_OK")'
# valida db-flat copiado é um sqlite legível
python3 - "$S" <<'PYEOF'
import sqlite3, sys, tarfile, tempfile, shutil, os
s = sys.argv[1]
t1 = f"{s}/BACKUP_DIR/fabrica-20261012.tar.gz"
tmp = tempfile.mkdtemp()
tarfile.open(t1).extractall(tmp)
assert os.path.exists(f"{tmp}/hermes/state.db-flat")
c = sqlite3.connect(f"{tmp}/hermes/state.db-flat")
assert c.execute("select count(*) from t").fetchone()[0] == 1, "db-flat ilegível ou vazio"
print("DB_FLAT_OK")
shutil.rmtree(tmp)
PYEOF
OUT2=$(cd "$REPO" && BACKUP_DATE=20261013 ./scripts/backup_fabrica.sh)
echo "OUT2=$OUT2"
echo "-- arquivos em BACKUP_DIR --"
ls "$S/BACKUP_DIR"
echo "FASE1_FIM"
#!/usr/bin/env bash
# Prova hermética GB-BACKUP-01: fase 2 (retenção 7 diários + 4 semanais).
set -euo pipefail
S="$1"; REPO="$2"; export BACKUP_DIR="${3:-$S/BACKUP_DIR}"
export HERMES_HOME="$S/fake_hermes"
mkdir -p "$BACKUP_DIR"
for d in 20260929 20260930 20261001 20261002 20261003 20261004 20261005 20261006 20261007 20261008 20261009 20261010 20261011 20261012; do
  (cd "$REPO" && BACKUP_DATE=$d ./scripts/backup_fabrica.sh >/dev/null)
done
echo "-- arquivos restantes --"
ls "$BACKUP_DIR"
python3 - "$BACKUP_DIR" <<'PYEOF'
import sys, glob, os, datetime
b = sys.argv[1]
fs = sorted(os.path.basename(p)[8:-7] for p in glob.glob(f"{b}/fabrica-*.tar.gz"))
assert len(fs) == 8, f"esperado 8 arquivos (7 diarios + 1 semanal), veio {len(fs)}: {fs}"
assert fs[-1] == "20261012", "backup do dia ausente"
assert fs == [f"202610{d:02d}" for d in range(5,13)], f"diarios errados: {fs}"
# 20261005 é segunda-feira -> semanal mantido; 0929..1004 apagados
assert datetime.datetime.strptime("20261005", "%Y%m%d").weekday() == 0
print("RETENCAO_OK (7 diarios + 1 segunda-feira; 6 antigos removidos)")
PYEOF
echo "FASE2_FIM"
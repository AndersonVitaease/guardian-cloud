#!/usr/bin/env bash
# WATCHDOG-CTL-01 — instala unit+timer systemd watchdog-sweep + cria watchdog.d + migra 10-tab-reap.
# Dry-run default; --apply executa de fato (supervisor/root no fecho; worker NÃO toca systemctl).
set -u
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1
WATCHDOG_D_DIR="${WATCHDOG_D_DIR:-/opt/hermes/watchdog.d}"
SWEEP="${WATCHDOG_SWEEP_PATH:-/opt/hermes/scripts/watchdog_sweep.sh}"
TAB_REAP="${WATCHDOG_TAB_REAP_PATH:-/opt/hermes/tools/tab_reap.py}"

UNIT="[Unit]
Description=watchdog sweep (WATCHDOG-CTL-01)

[Service]
Type=oneshot
ExecStart=$SWEEP
Environment=WATCHDOG_D_DIR=$WATCHDOG_D_DIR
"

TIMER="[Unit]
Description=timer watchdog sweep 10min

[Timer]
OnCalendar=*:0/10
Persistent=true

[Install]
WantedBy=timers.target
"

echo "== dry-run: plano =="
echo "1) mkdir -p $WATCHDOG_D_DIR"
echo "2) escrever /etc/systemd/system/watchdog-sweep.service:"
printf '%s\n' "$UNIT"
echo "3) escrever /etc/systemd/system/watchdog-sweep.timer:"
printf '%s\n' "$TIMER"
echo "4) systemctl daemon-reload && systemctl enable --now watchdog-sweep.timer"
echo "5) migrar wrapper 10-tab-reap para $WATCHDOG_D_DIR/10-tab-reap.sh (TAB_REAP=$TAB_REAP)"

if [ "$APPLY" -eq 1 ]; then
  mkdir -p "$WATCHDOG_D_DIR"
  printf '%s' "$UNIT"  > /etc/systemd/system/watchdog-sweep.service
  printf '%s' "$TIMER" > /etc/systemd/system/watchdog-sweep.timer
  systemctl daemon-reload
  systemctl enable --now watchdog-sweep.timer
  cat > "$WATCHDOG_D_DIR/10-tab-reap.sh" <<EOF
#!/usr/bin/env bash
out="\$("$TAB_REAP" --apply 2>&1)" || true
[ -n "\$out" ] && printf '%s\n' "\$out"
EOF
  chmod +x "$WATCHDOG_D_DIR/10-tab-reap.sh"
  echo "== aplicado =="
fi
exit 0
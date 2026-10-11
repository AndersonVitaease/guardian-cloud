#!/usr/bin/env bash
# RD-ORQD-LIVE-DOWN-01 — teste hermético do sentinel (systemctl fake via PATH override).
set -u
SENT="$(cd "$(dirname "$0")" && pwd)/watchdog/orqd-live-sentinel.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

falhas=0
check() { # nome esperado_exit
  local nome="$1" esperado="$2"; shift 2
  out="$("$@" 2>&1)"; rc=$?
  if [ "$rc" -eq "$esperado" ]; then
    echo "OK   $nome (exit $rc)"
  else
    echo "FALHA $nome: esperado exit $esperado, obtido $rc — saída: $out"
    falhas=$((falhas+1))
  fi
}

# fake systemctl
cat > "$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  list-unit-files) echo "orqd-live.service static"; exit 0 ;;
  is-active) exit 3 ;; # unit existe mas is-active falha => inativo
esac
exit 1
EOF
chmod +x "$TMP/bin/systemctl"

# Caso 1: serviço ATIVO (unit ativa) => exit 0
cat > "$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  list-unit-files) echo "orqd-live.service static"; exit 0 ;;
  is-active) echo active; exit 0 ;;
esac
exit 1
EOF
chmod +x "$TMP/bin/systemctl"
check "servico ativo" 0 env PATH="$TMP/bin:$PATH" /bin/bash "$SENT"

# Caso 2: serviço INATIVO (unit existe, is-active falha) => exit 1 + JSON
# pgrep fake falhando: garante hermeticidade (sem processo real no host).
printf '#!/bin/sh\nexit 1\n' > "$TMP/bin/pgrep"; chmod +x "$TMP/bin/pgrep"
cat > "$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  list-unit-files) echo "orqd-live.service static"; exit 0 ;;
  is-active) exit 3 ;; # unit existe mas is-active falha => inativo
esac
exit 1
EOF
chmod +x "$TMP/bin/systemctl"
check "servico inativo" 1 env PATH="$TMP/bin:$PATH" /bin/bash "$SENT"

# Caso 3: comando systemctl inexistente e sem processo => exit 1
printf '#!/bin/sh\nexit 1\n' > "$TMP/bin/pgrep"; chmod +x "$TMP/bin/pgrep"
check "comando inexistente" 1 env PATH="$TMP/bin" /bin/bash "$SENT"

if [ "$falhas" -gt 0 ]; then
  echo "TESTES: $falhas falha(s)"
  exit 1
fi
echo "TESTES: 3/3 verdes"
exit 0
#!/usr/bin/env bash
# Prova hermetica RD-DESP-TAB-SILENT-01: mount-espelho.sh cura tab sem pane-id.
set -u
PASS=0
check() { # check <desc> <cmd...>
  local desc="$1"; shift
  if "$@"; then
    echo "ok: ${desc}"
  else
    echo "FALHOU: ${desc}" >&2
    PASS=1
  fi
}

make_scratch() {
  local S; S="$(mktemp -d)"
  mkdir -p "$S/bin" "$S/runs/M-TESTE/tentativa-1/run-20261013-000000-seed77-abc"
  : > "$S/runs/M-TESTE/tentativa-1/run-20261013-000000-seed77-abc/harness-pane.log"
  cat > "$S/bin/herdr" <<HEOF
#!/usr/bin/env bash
S="$S"
cmd="\${1:-}"; shift || true
case "\$cmd" in
  tab)
    case "\${1:-}" in
      create)
        modo="\$(cat "\$S/modo.txt" 2>/dev/null || echo com-pane)"
        if [[ "\$modo" == "sem-pane" ]]; then
          printf '{"result":{"root_pane":{"tab_id":"stub:t1","workspace_id":"stub:ws"}}}'
        else
          printf '{"result":{"root_pane":{"tab_id":"stub:t1","pane_id":"stub:p1","workspace_id":"stub:ws"}}}'
        fi ;;
      *) exit 1 ;;
    esac ;;
  pane)
    sub="\${1:-}"; shift || true
    case "\$sub" in
      run) printf '%s\n' "\$*" >> "\$S/pane-run.log"; exit 0 ;;
      *) exit 1 ;;
    esac ;;
  *) exit 1 ;;
esac
HEOF
  chmod 755 "$S/bin/herdr"
  echo "$S"
}

# Caso 1: sem-pane -> exit != 0 e TAB_SEM_PANE no stderr
S1="$(make_scratch)"
echo sem-pane > "$S1/modo.txt"
OUT1="$(PATH="$S1/bin:$PATH" bash scripts/mount-espelho.sh "$S1/runs/M-TESTE/tentativa-1/run-*" 77 M-TESTE 2>&1)"
RC1=$?
check "sem-pane exit != 0" test "$RC1" -ne 0
check "sem-pane saida contem TAB_SEM_PANE" bash -c "[[ '$OUT1' == *TAB_SEM_PANE* ]]"

# Caso 2: com-pane -> exit 0 e saida contem stub:p1
S2="$(make_scratch)"
echo com-pane > "$S2/modo.txt"
OUT2="$(PATH="$S2/bin:$PATH" bash scripts/mount-espelho.sh "$S2/runs/M-TESTE/tentativa-1/run-*" 77 M-TESTE 2>&1)"
RC2=$?
check "com-pane exit 0" test "$RC2" -eq 0
check "com-pane saida contem stub:p1" bash -c "[[ '$OUT2' == *stub:p1* ]]"

rm -rf "$S1" "$S2"
if [[ "$PASS" -eq 0 ]]; then
  echo "RD-DESP-TAB-SILENT-01-PROVA-OK"
else
  exit 1
fi

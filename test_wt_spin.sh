#!/usr/bin/env bash
# test_wt_spin.sh — teste hermético de wt_spin.sh.
# Repo fake via git init --bare + clone scratch; WT_SPIN_REPO/WT_SPIN_WT_ROOT
# apontam para fixtures dentro do teste. Usuário não-worker simulado
# (sem sudo/root: prova roda como usuário corrente).
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
export WT_SPIN_REPO="$SCRATCH/repo.git"
export WT_SPIN_WT_ROOT="$SCRATCH/wtroot"

FAILS=0
ok(){ echo "PASS: $1"; }
bad(){ echo "FAIL: $1"; FAILS=$((FAILS+1)); }

# ---- fixture: repo fake com branch base rd-segue-01 ----
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init --bare -q "$WT_SPIN_REPO"
git clone -q "$WT_SPIN_REPO" "$SCRATCH/clone"
git -C "$SCRATCH/clone" config user.email t@t
git -C "$SCRATCH/clone" config user.name t
git -C "$SCRATCH/clone" commit -q --allow-empty -m base
git -C "$SCRATCH/clone" branch -M rd-segue-01
git -C "$SCRATCH/clone" push -q origin rd-segue-01

# 1. sintaxe
bash -n wt_spin.sh && ok "bash -n" || bad "bash -n"

# 2. criação feliz
OUT=$(bash wt_spin.sh WT-Spin-99)
echo "$OUT" | grep -q '"ok":true' && ok "criacao feliz" || bad "criacao feliz: $OUT"
echo "$OUT" | grep -q '"branch":"rd-wt-spin-99"' && ok "slug minusculo" || bad "slug: $OUT"
[ -e "$WT_SPIN_WT_ROOT/wt-WT-Spin-99/.git" ] && ok "worktree criado" || bad "worktree ausente"
git -C "$WT_SPIN_REPO" show-ref --verify --quiet refs/heads/rd-wt-spin-99 \
  && ok "branch no repo" || bad "branch ausente"
echo "$OUT" | grep -q '"probe":"ok"' && ok "probe ok" || bad "probe: $OUT"
# probe não deixou commit extra
[ "$(git -C "$WT_SPIN_WT_ROOT/wt-WT-Spin-99" rev-list --count HEAD)" = "1" ] \
  && ok "probe desfeito" || bad "probe nao desfeito"

# 3. segunda chamada → NAO_CRIADO tipado com dica, sem destruir
OUT2=$(bash wt_spin.sh WT-Spin-99)
echo "$OUT2" | grep -q '"error":"NAO_CRIADO"' && ok "NAO_CRIADO" || bad "segunda chamada: $OUT2"
echo "$OUT2" | grep -q '"dica"' && ok "campo dica" || bad "sem dica"
[ -e "$WT_SPIN_WT_ROOT/wt-WT-Spin-99/.git" ] && ok "worktree preservado" || bad "worktree destruido"

# 4. --no-probe
OUT3=$(bash wt_spin.sh WT-Spin-98 --no-probe)
echo "$OUT3" | grep -q '"probe":"pulada"' && ok "--no-probe" || bad "--no-probe: $OUT3"

# 5. base explícita
OUT4=$(bash wt_spin.sh WT-Spin-97 rd-segue-01)
echo "$OUT4" | grep -q '"base":"rd-segue-01"' && ok "base explicita" || bad "base: $OUT4"

# 6. BAD_ARGS sem ID
OUT5=$(bash wt_spin.sh)
echo "$OUT5" | grep -q '"error":"BAD_ARGS"' && ok "BAD_ARGS" || bad "BAD_ARGS: $OUT5"

# 7. BASE_INEXISTENTE
OUT6=$(bash wt_spin.sh WT-Spin-96 rd-nao-existe)
echo "$OUT6" | grep -q '"error":"BASE_INEXISTENTE"' && ok "BASE_INEXISTENTE" || bad "base inexistente: $OUT6"

# 8. JSON de 1 linha em todas as saídas
for o in "$OUT" "$OUT2" "$OUT3" "$OUT4" "$OUT5" "$OUT6"; do
  [ "$(printf '%s' "$o" | wc -l)" = "0" ] || bad "JSON multi-linha: $o"
done
ok "JSON 1 linha"

echo "----"
if [ "$FAILS" = "0" ]; then echo "TODOS OS TESTES PASSARAM"; exit 0; fi
echo "$FAILS TESTES FALHARAM"; exit 1
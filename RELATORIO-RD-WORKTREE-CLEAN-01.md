# RD-WORKTREE-CLEAN-01

Correção: `scripts/worktree_clean.py` passou a derivar o nome de unidade/ledger removendo o prefixo do worktree (ex.: `wt-AAA` → `AAA`) para localizar `<state_dir>/<unidade>.json` e nomear `AAA-runs.tar.gz` / `MANIFESTO-AAA.md`; antes usava o basename completo (`wt-AAA.json`), o que fazia o ledger `running` nunca ser encontrado (wt-BBB removido por engano) e o tar/manifesto saírem com nome errado.
Prova: `/usr/bin/python3 -m pytest tests/test_worktree_clean.py -q` → `6 passed in 1.16s` (antes 3 failed: ledger_em_voo, apply_arquiva_e_remove, status_sujo). Commits worker aplicados com ID no assunto.

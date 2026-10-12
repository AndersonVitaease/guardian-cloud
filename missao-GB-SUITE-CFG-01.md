# MISSÃO GB-SUITE-CFG-01

Fonte: ROADMAP.md fila do operador (autorizada 12/10 20:30 BRT). Finding do dia:
fecho de missão no repo /opt/memoryos deu SUITE_VERMELHA FALSA — a suíte default
(`pytest tests/` no BASE_REPO) coleta 0 testes → pytest sai com código 5.

## ENTREGA ÚNICA: patch de missao_fechar.sh (arquivo governado, fora do git)

O worker NÃO pode escrever em /opt. Entregue no worktree:

1. `cura-missao-fechar.patch` — diff (unified, gerado com diff -u contra uma
   cópia do original que estará em `original-missao_fechar.sh` no worktree)
   aplicável com `patch` no arquivo real. Mudança EXATA:
   - No passo de suíte (hoje linha ~111): capturar o RC da suíte em vez de só
     ok/not-ok.
   - RC 5 (pytest "no tests ran") → SUITE_VAZIA: suite_ok=1 + ressalva
     {"tipo":"SUITE_VAZIA","repo":BASE_REPO} no JSON final (campo ressalvas,
     mesmo formato de KNOWN_FAIL) e stderr tipado. NÃO é vermelho.
   - RC 0 → verde como hoje. Outros RC → PROVA_VERMELHA como hoje.
   - Comportamento com SUITE_CMD customizado inalterado.
2. `prova-suite-cfg-01.py` — prova hermética SEM tocar no arquivo real:
   copia o original + aplica o patch em tempdir, monta um mini "repo" fixture
   (tempdir com git init + tests/ vazio) e chama o MISSAO_FECHAR_PATCHED
   substituindo BASE_REPO/SUITE via env — se o script exigir, extraia a lógica
   da suíte para função testável dentro do patch. Asserts: RC5 → ok:true com
   ressalva SUITE_VAZIA; RC1 → erro SUITE_VERMELHA; RC0 → ok sem ressalva.
   Saída final: GB-SUITE-CFG-01-PROVA-OK.
3. `RELATORIO-GB-SUITE-CFG-01.md` — diff explicado + como o supervisor aplica
   (cp backup .bak-SUITE-CFG + patch + bash -n).

O original para o diff: /opt/mission-events/tools-bash/missao_fechar.sh
(LEITURA permitida; cp para o worktree com sudo NÃO é necessário — leia com
python/sed se cp direto falhar por permissão).

## harness-stop

```harness-stop
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test -s original-missao_fechar.sh && test -s cura-missao-fechar.patch
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && python3 prova-suite-cfg-01.py 2>&1 | grep -q -F 'GB-SUITE-CFG-01-PROVA-OK'
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test -s RELATORIO-GB-SUITE-CFG-01.md
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test "$(git log -1 --format=%s)" = "GB-SUITE-CFG-01: patch missao_fechar (RC5 pytest = SUITE_VAZIA tipada, nao vermelho)"
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test -z "$(git status --porcelain)"
```

REGRAS: proibido git reset/checkout/stash/clean; sudo só nos stops de prova;
NUNCA escrever em /opt — a aplicação do patch no arquivo vivo é supervisor-side
(fecho), não do worker.

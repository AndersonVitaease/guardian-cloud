# MISSÃO GB-SUITE-CFG-01

Fonte: ROADMAP.md fila do operador (autorizada 12/10 20:30 BRT). Finding do dia:
fecho de missão no repo /opt/memoryos deu SUITE_VERMELHA FALSA — a suíte default
(`pytest tests/` no BASE_REPO) coleta 0 testes → pytest sai com código 5.

## MAPA (medido 12/10)

- missao_fechar.sh:108 — `SUITE_CMD="${SUITE_CMD:-/usr/bin/python3 -m pytest tests/ -q}"`
- missao_fechar.sh:109-115 — SUITE_OK só 1/0; RC 5 do pytest (no tests ran)
  cai no mesmo balde de RC 1 → SUITE_VERMELHA + rollback indevido.
- missao_fechar.sh:159+ — emit_json final (campo ressalvas já existe — ver
  uso de KNOWN_FAIL em missao_fechar.sh:127-134).

## ENTREGA ÚNICA: patch de missao_fechar.sh (arquivo governado, fora do git)

O worker NÃO pode escrever em /opt. Entregue no worktree:

1. `cura-missao-fechar.patch` — diff (unified, gerado com diff -u contra uma
   cópia do original que estará em `original-missao_fechar.sh` no worktree)
   aplicável com `patch` no arquivo real. Mudança EXATA:
   - No passo de suíte (missao_fechar.sh:111): capturar o RC da suíte em vez
     de só ok/not-ok.
   - RC 5 (pytest "no tests ran") → SUITE_VAZIA: suite_ok=1 + ressalva
     {"tipo":"SUITE_VAZIA","repo":BASE_REPO} no JSON final (campo ressalvas,
     mesmo formato de KNOWN_FAIL em missao_fechar.sh:127) e stderr tipado.
     NÃO é vermelho. Só aplica quando SUITE_CMD foi o default (env customizado
     mantém comportamento atual).
   - RC 0 → verde como hoje. Outros RC → PROVA_VERMELHA como hoje.
2. `prova-suite-cfg-01.py` — prova hermética SEM tocar no arquivo real e SEM
   rede: cria tempdir (tempfile.mkdtemp), copia original + aplica o patch no
   tempdir, monta fixture de "repo" (git init + tests/ vazio) e exercita a
   lógica da suíte extraída/testável pelo patch. Asserts: RC5 → ok:true com
   ressalva SUITE_VAZIA; RC1 → erro SUITE_VERMELHA; RC0 → ok sem ressalva.
   Saída final: GB-SUITE-CFG-01-PROVA-OK.
3. `RELATORIO-GB-SUITE-CFG-01.md` — diff explicado + como o supervisor aplica
   (cp backup .bak-SUITE-CFG + patch + bash -n).

O original para o diff: /opt/mission-events/tools-bash/missao_fechar.sh
(somente LEITURA; cp para o worktree com python/sed se cp direto falhar por
permissão). NUNCA escrever em /opt — a aplicação no arquivo vivo é
supervisor-side (fecho), não do worker.

## harness-stop

```harness-stop
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test -s original-missao_fechar.sh && test -s cura-missao-fechar.patch
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && python3 prova-suite-cfg-01.py 2>&1 | grep -q -F 'GB-SUITE-CFG-01-PROVA-OK'
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test -s RELATORIO-GB-SUITE-CFG-01.md
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test "$(git log -1 --format=%s)" = "GB-SUITE-CFG-01: patch missao_fechar (RC5 pytest = SUITE_VAZIA tipada, nao vermelho)"
cmd cd /home/worker/wt-GB-SUITE-CFG-01 && test -z "$(git status --porcelain)"
```

REGRAS: proibido git reset/checkout/stash/clean; sudo só nos stops de prova
python.

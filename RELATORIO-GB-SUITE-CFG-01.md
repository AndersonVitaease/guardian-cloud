# RELATORIO-GB-SUITE-CFG-01

## Problema (finding)

Fecho de missao no repo /opt/memoryos deu SUITE_VERMELHA FALSA: a suíte default
(`pytest tests/`) coleta 0 testes → pytest sai com RC 5 ("no tests ran").
`missao_fechar.sh` tratava qualquer RC != 0 como vermelho → rollback indevido.

## Diff explicado (cura-missao-fechar.patch)

No passo de suíte (original:108-115):

1. **Captura do RC**: em vez de `if ! (...); then SUITE_OK=0`, agora
   `SUITE_RC=0; (...) || SUITE_RC=$?` — o RC real da suíte fica disponível.
2. **SUITE_CMD_DEFAULT**: flag que marca se `SUITE_CMD` é exatamente o default
   (`/usr/bin/python3 -m pytest tests/ -q`). SUITE_CMD customizado via env
   mantém o comportamento antigo (qualquer RC != 0 = vermelho).
3. **RC 5 + default → SUITE_VAZIA**: `SUITE_OK=1` (não é vermelho),
   `RESSALVAS_RAW='[{"tipo":"SUITE_VAZIA","repo":"<BASE_REPO>"}]'` (mesmo
   formato do KNOWN_FAIL) e stderr tipado
   `{"aviso":"SUITE_VAZIA","mission_id":...,"repo":...,"rc":5}`.
4. **RC 0 → verde** (como hoje); **outros RC → PROVA_VERMELHA** (como hoje).
5. **emit_json**: `RESSALVAS_RAW` é passado como 5º argumento ao python e
   injetado no campo `ressalvas` do JSON final (com try/except, tolerante).

## Como o supervisor aplica (arquivo vivo em /opt — worker não escreve lá)

```bash
cd /opt/mission-events/tools-bash
cp missao_fechar.sh missao_fechar.sh.bak-SUITE-CFG
patch -p0 missao_fechar.sh /home/worker/wt-GB-SUITE-CFG-01/cura-missao-fechar.patch
bash -n missao_fechar.sh   # valida sintaxe
```

## Prova hermética

`prova-suite-cfg-01.py` — sem tocar no arquivo real, sem rede: tempdir,
aplica o patch numa cópia, monta fixture de repo (git init + tests/ vazio),
stub de `sudo`/`python3 -m pytest` com RC controlado. Asserts:
- RC5 (default) → suite_ok=1 + ressalva SUITE_VAZIA + stderr tipado ✔
- RC1 → suite_ok=0 (vermelho) ✔
- RC0 → suite_ok=1 sem ressalvas ✔
- RC5 com SUITE_CMD custom → suite_ok=0 (comportamento antigo mantido) ✔

Saída: `GB-SUITE-CFG-01-PROVA-OK` (verificada nesta run).
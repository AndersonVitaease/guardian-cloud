# MISSÃO SEC-TOOLS-01 — segurança das tools bash e artefatos de run (injeção de args + permissões)

Fonte: ROADMAP.md linha 387.

operatorOrder: segurança total autorizada pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Alvos (só leitura): scripts em /opt/mission-events/tools-bash/*.sh (24 tools), _lib.sh, e artefatos de run em /tmp (resumo-*.json, vigia-*.jsonl). Escopo de escrita do worker = o worktree próprio, nada mais.
- Contexto real: todas as tools executam comandos com args do usuário/modelo embutidos (ex.: code_find.sh PADRAO DIR, run_close.sh <ID>); _lib.sh tem tb_join/tb_audit; despachar_missao.py gera units com mid embutido em --unit e caminhos /tmp.

## OBJETIVO — relatório por vulnerabilidade (worker REPORTA; a correção é decisão do operador):
1. **Injeção de args**: para cada tool .sh, rastrear onde `$1..$N`/ARGS chegam sem validação: (a) dentro de eval/bash -c; (b) em grep -e/-E sem delimitador (padrão começando com '-' = flag injection); (c) em caminhos de cd/sem aspas (space/;/$() injection); (d) regex sem validação de chars (ID malformado rompendo JSON do audit). Classificar: EXPLORAVEL (modelo/operador consegue executar comando arbitrário via arg) vs VALIDACAO_AUSENTE (rompe mas não executa). Já conhecidas e OK: trail_tail/run_close/run_stream validam ID com case whitelist — citar como padrão de forma.
2. **Artefatos de run em /tmp**: permissões de resumo-*.json e vigia-*.jsonl (mundo-legível = hits de trilha expostos a qualquer usuário local); conteriam custo/commits mas PODEM conter preview de segredo? Provar lendo 1 resumo e 1 vigia e inspecionar campos; recomendar chmod 600 na criação (texto de patch pronto, não aplica).
3. **Audit injection**: tb_audit/tb_join com ARGS contendo aspas/pipes — o JSON do audit pode ser quebrado por um arg com `"`? Provar com chamada real de uma tool em scratch e inspecionar a linha do audit.
4. **RELATORIO-SEC-TOOLS-01.md**: achados por severidade + patch-texto sugerido por item (não aplica).

## TAREFA
1. Escrever `scripts/sec_tools_scan.py` (determinístico, unittest tests/test_sec_tools_scan.py com fixtures de script vulnerável/seguro) que automatiza a checagem 1 e 3 (heurísticas de regex sobre os .sh + prova de audit com arg contendo `"`).
2. Rodar contra /opt/mission-events/tools-bash (só leitura) e escrever o relatório.
3. Commit `SEC-TOOLS-01: sec_tools_scan + relatorio` e `SEC-TOOLS-01: relatorio` (RELATORIO-SEC-TOOLS-01.md na raiz).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-SEC-TOOLS-01 && git log -1 --format=%s | grep -q -F "SEC-TOOLS-01: sec_tools_scan"
cmd cd /home/worker/wt-SEC-TOOLS-01 && /usr/bin/python3 -m py_compile scripts/sec_tools_scan.py
cmd cd /home/worker/wt-SEC-TOOLS-01 && /usr/bin/python3 -m unittest tests.test_sec_tools_scan -v 2>&1 | tail -1
cmd cd /home/worker/wt-SEC-TOOLS-01 && /usr/bin/python3 scripts/sec_tools_scan.py > /dev/null && echo SCAN-OK
cmd cd /home/worker/wt-SEC-TOOLS-01 && git ls-files --error-unmatch scripts/sec_tools_scan.py && git ls-files --error-unmatch RELATORIO-SEC-TOOLS-01.md
```

PROIBIDO: git reset/checkout/stash/clean; escrita em /opt e /root; executar código achado; commitar qualquer segredo (se surgir, MASCARADO).

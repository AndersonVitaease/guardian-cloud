# MISSÃO TAB-REAP-01 — tool bash tab_reap.sh (varredura determinística 0 LLM de abas mortas do herdr)

**Componente:** tools-bash (`tab_reap.sh`) · **Prioridade:** alta · **Fonte:** ROADMAP.md linha 372 · **Autoria:** operator 10/10 — tab_reap.sh autorizado pelo operador 10/10.

## Entrega (ÚNICA)
1. `tab_reap.sh` na RAIZ do worktree `/home/worker/wt-TAB-REAP-01` (Write inteiro, arquivo novo). MESMO PADRÃO DE FORMA da tool runs_status.sh instalada (caminho completo só no MAPA abaixo; leia com `code_slice.sh`, NÃO com cat/head):
   - Cabeçalho comentado + `set -u` + `source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"` + `start=$(date +%s%N)` — igual a runs_status.sh linhas 1–8.
   - `fail(){ ... }` tipado que audita (tb_audit com tb_join) e imprime JSON 1 linha `{"ok":false,"tool":"tab_reap","error":"..."}` + `exit 0` — igual a runs_status.sh (`def fail` no python dela; no bash use o mesmo contrato do _lib.sh).
   - `tb_audit`/`tb_join` vêm de `/opt/mission-events/tools-bash/_lib.sh` (`tb_audit(){` linha 30; `tb_join(){` linha 58; `tb_fail(){` linha 64; `tb_emit(){` linha 72). Se `_lib.sh` NÃO existir no worktree (só existe em /opt), o script deve tolerar: `source` só se o arquivo existir, senão define fallbacks locais de tb_audit (no-op seguro)/tb_join — para o teste local funcionar.
2. Interface: `tab_reap.sh [--tabs-json <arq>] [--active-json <arq>] [--apply]`.
   - Com flags: lê o arquivo indicado (`--tabs-json`: saída capturada de `herdr tab list`; `--active-json`: saída capturada de runs_status.sh). Arquivo inexistente → `fail ARQ_NAO_ENCONTRADO`; JSON inválido → `fail JSON_INVALIDO`.
   - Sem flags: tenta `herdr tab list` ao vivo (binário `$HERDR_BIN`, default `herdr`) e `bash /opt/mission-events/tools-bash/runs_status.sh` (só se o arquivo existir). Se o herdr responder erro `workspace_not_found` ou `server_not_running` (ou não responder JSON com result.tabs), `fail HERDR_INACESSIVEL` com campo `hint` no JSON de erro explicando que a unit roda como worker sem a sessão do operador. NADA fechado nesse caso.
3. Cruzamento (determinístico, 0 LLM): aba MORTA = label começa com `RUN:`, `MISSION:` ou `AGENTE:` E o missionId extraído do label (trecho entre `:` e `#`, ou até o fim se não houver `#`) NÃO aparece:
   - em `runs[].missionId` do active-json;
   - NEM em `systemctl list-units --all --no-legend 'harness-*'` (quando systemctl acessível; se systemctl falhar, ignore esse sinal — só o runs_status decide).
   - NUNCA tocadas: aba de label `1` e qualquer aba cujo label não começa com os 3 prefixos (nunca são mortas nem listadas como candidatas).
4. Ação: DEFAULT é DRY-RUN (nada é fechado). Com `--apply`: para cada morta, executa `$HERDR_BIN tab close <tab_id>` (reconfere o runs_status ao vivo imediatamente antes de fechar, se acessível; herdr inacessível no apply → `fail HERDR_INACESSIVEL` sem fechar NADA).
5. Saída: 1 linha JSON, exatamente estas chaves: `{"ok":true,"tool":"tab_reap","abas_total":N,"mortas":[{"tab":<tab_id>,"label":...}],"fechadas":[{"tab":...,"label":...}],"modo":"dry-run"|"apply"}`. `exit 0` SEMPRE (inclusive nos fail).
6. `test_tab_reap.sh` na raiz (Write inteiro): cria `fixtures/tabs.json` e `fixtures/active.json` dentro do worktree (idempotente) e roda `bash tab_reap.sh --tabs-json fixtures/tabs.json --active-json fixtures/active.json`; exige exit 0, `fechariam` contendo TESTE-VAZIO e NÃO contendo RUN-CLOSE-01 (nem RD-H1H2-REPORT-01 nem label 1). Teste hermético extra do --apply: `HERDR_BIN` fake (script que grava `tab close <id>` em arquivo de prova e sai 0) — prova que dry-run NÃO fecha e --apply fecha só a morta.
7. `RELATORIO-TAB-REAP-01.md` na raiz (Write inteiro): o que o script faz, saída real do `test_tab_reap.sh` colada, e nota de que a instalação no diretório de tools do SUPERVISOR é passo do fecho (via tools_install.sh) — o worker NÃO instala nada fora do worktree.

## MAPA PRÉ-DIGERIDO (padrão de forma — não precise descobrir)
- `/opt/mission-events/tools-bash/_lib.sh`: `tb_audit(){` L30, `tb_join(){` L58, `tb_fail(){` L64, `tb_emit(){` L72.
- `/opt/mission-events/tools-bash/runs_status.sh`: cabeçalho+`set -u`+`source _lib.sh`+`start=` L1–8; `tb_emit runs_status "$OUT" "$start"` L208. Formato de saída: `{"ok":true,"tool":"runs_status","count":N,"runs":[{"missionId":"RD-H1H2-REPORT-01",...,"tab":"RUN:RD-H1H2-REPORT-01#s239",...}]}` — `runs[].missionId` e `runs[].tab` no formato `RUN:ID#sSEED`.
- Formato real de `herdr tab list` (1 linha JSON): `{"id":"cli:tab:list","result":{"tabs":[{"label":"RUN:F0A2-AGENT-BASH#s138","number":212,"tab_id":"w8:t6M","agent_status":"unknown","workspace_id":"w8","focused":false,"pane_count":1},...]}}` — use `result.tabs[].label` e `result.tabs[].tab_id`.
- Referência de cruzamento/fecho: `/home/worker/harness-s2/tools-bash/herdr_limpar.sh` L70 (`tab_id = t.get("tab_id","")`), L77 (monta mortas), L95 (`herdr tab close <tab_id>`).
- Fixtures REAIS embedadas (use EXATAMENTE no teste): abas vivas `["1", "RUN:RD-H1H2-REPORT-01#s239", "RUN:RUN-CLOSE-01#s77"]` (tab_ids `w8:t1`, `w8:tA`, `w8:tB`); runs ativas `["RD-H1H2-REPORT-01", "RUN-CLOSE-01"]`. No teste, adicione a fictícia `"RUN:TESTE-VAZIO#s1"` (tab_id `w8:tT1`) — ELA ENTRA em `mortas`/`fechariam`; as vivas NÃO entram.
- Arquivos NOVOS: `tab_reap.sh`, `test_tab_reap.sh`, `RELATORIO-TAB-REAP-01.md` (raiz do worktree).

## Regras
- ESCREVA CEDO: `tab_reap.sh` no 1º turno, `bash -n`, depois o teste, depois commit.
- Commit com assunto contendo `TAB-REAP-01` (git add SÓ dos 3 arquivos da missão + fixtures se criar fora do teste, nunca `-A`).
- Proibido: `cat`, `head`, `ls`, `grep -A`, `;`, `sudo`, `git reset/checkout/stash/clean`, escrever fora do worktree. NUNCA leia `harness-trail.jsonl` nem outros `.jsonl` de run.
- Todos os comandos com `cd /home/worker/wt-TAB-REAP-01 && `.
- NUNCA feche a aba de label `1` nem aba de run ativa; em caso de dúvida, NÃO feche.
- A instalação em `/opt/mission-events/tools-bash` é do SUPERVISOR no fecho (tools_install.sh) — não faça.

```harness-stop
cmd cd /home/worker/wt-TAB-REAP-01 && git log -1 --format=%s | grep -q -F TAB-REAP-01
cmd cd /home/worker/wt-TAB-REAP-01 && bash -n tab_reap.sh
cmd cd /home/worker/wt-TAB-REAP-01 && bash test_tab_reap.sh
cmd cd /home/worker/wt-TAB-REAP-01 && git ls-files --error-unmatch tab_reap.sh && git diff --quiet HEAD -- tab_reap.sh
```

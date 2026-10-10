# MISSÃO JANELA-CACHE-01 — Reduzir custo de input da janela: (a) compactacao em LOTE para o prefixo das mensagens ficar estavel entre turnos e (b) breakpoint de cache na ultima mensagem enviada ao bridge

## MAPA
- harness.py | ~30 linhas | NAO edite tests/. Ler so os trechos citados (class Window ~linha 648-715, call_bridge_once ~linha 599, new Window( em run_mission). (1) Perto de RAW_WINDOW (linha ~114) crie WINDOW_BATCH = int(os.environ.get('HARNESS_WINDOW_BATCH','4')) e CACHE_MSG = os.environ.get('HARNESS_CACHE_MSG','1') != '0'. (2) class Window.__init__: novo parametro compact_to=None (default None = comportamento atual, tests existentes com Window(raw_window=N) NAO podem mudar); guarde self.compact_to = compact_to. Em add(): o laco 'while len(self.exchanges) > self.raw_window' passa a ser: if len(self.exchanges) > self.raw_window: alvo = self.raw_window if self.compact_to is None else max(1, min(self.compact_to, self.raw_window)); while len(self.exchanges) > alvo: summary_lines.extend(pop(0)['digest']). O teto de summary (max_summary) fica igual. O maximo de trocas cruas continua <= raw_window. (3) Em run_mission onde cria Window(raw_window=raw_window, max_tool_chars=..., max_summary=...): acrescente compact_to=(raw_window - WINDOW_BATCH if raw_window >= 8 else None). (4) call_bridge_once: antes de montar body, se CACHE_MSG e messages nao vazio: copie so a ULTIMA mensagem (dict) — se content for str vire [{'type':'text','text':content}]; se for lista copie a lista e o ultimo bloco (dict) e adicione 'cache_control': {'type':'ephemeral'} nesse ultimo bloco; use messages_envio = messages[:-1] + [ultima_copia] no body. NUNCA mutar os objetos da janela (a janela e reusada). Nao mude mais nada.

## Regras
- PROIBIDO git reset/checkout/stash/clean; só git add/commit.
- Checkpoint commit como worker ANTES das edições.
- Não toque em routing/bridge nem no dir de produção root-only.
- Sem sudo nos comandos dos stops.

## Stops
```harness-stop
cmd cd /home/worker/wt-JANELA-CACHE-01 && python3 -m py_compile harness.py
cmd cd /home/worker/wt-JANELA-CACHE-01 && grep -q -F 'WINDOW_BATCH' harness.py && grep -q -F 'CACHE_MSG' harness.py && grep -q -F 'compact_to' harness.py
cmd cd /home/worker/wt-JANELA-CACHE-01 && python3 -m unittest tests.test_harness tests.test_advisor_midrun tests.test_debug_mode tests.test_vagueio tests.test_nudge_fim tests.test_escada 2>&1 | tail -1 | grep -q '^OK'
cmd cd /home/worker/wt-JANELA-CACHE-01 && test -z "$(git diff --name-only rd-segue-01 -- tests)"
cmd cd /home/worker/wt-JANELA-CACHE-01 && git diff --quiet HEAD -- harness.py
cmd cd /home/worker/wt-JANELA-CACHE-01 && python3 -m unittest tests.test_harness tests.test_advisor_midrun tests.test_debug_mode tests.test_vagueio tests.test_nudge_fim 2>&1 | tail -1 | grep -q '^OK'
cmd git log -1 --pretty=%s | grep -q 'JANELA-CACHE-01'
```

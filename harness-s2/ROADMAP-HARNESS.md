# ROADMAP — Evolução do Harness-S2
*(criado 07/10/2026 · supervisor · fonte: dia inteiro de missões medidas — 43 runs, US$ 0,49, 31 PASS/12 FAIL, cada FAIL com causa identificada)*

## § DESCOBERTA DO DIA (07/10, 19:00 BRT) — PROVADA COM NÚMERO

**"Missão difícil = layers na run, não camada de cima"** — o mesmo problema
(debug de concorrência do batch):
- Worker sozinho: 3 FAILs, 145 turnos, US$ 0,14 (vagueava)
- Worker + infra debug (--modo/--memoria): FAIL — investigava certo, não convergia
- **Worker + advisor (causa-raiz instrumentada fora) + supervisor (HINTS.md
  mid-run): PASS 4/4 em 7 turnos, US$ 0,003 — 47× mais barato e FECHADO**

O glm-5.3-flash resolve o degrau quando as camadas da doutrina (advisor/
supervisor) entram DENTRO do loop. Canal provado: `HINTS.md` re-lido todo
turno por ordem do contrato + causa-raiz embutida pelo advisor antes da run.
Suíte: **147 passed, 0 failed** (batch-paralelo fechado — era bug de design
no TESTE: flag do script ≠ flag do batch; stop_flag virou injetável externo).

## Onde estamos (baseline 07/10)

- Worker: `z-ai/glm-5.3-flash` via bridge :8103 (trindade), despachado por
  `mission_run.py` (supervisor) e, desde hoje, **também pela fila oficial do
  orchestrator** (`dispatch_via_harness`, runner:harness na routing table — E2E
  provado por canário).
- Suíte: 138 verdes + 1 vermelho (`test_stop_flag_aborta_outra_thread`).
- 40 runs hoje, p50 LLM 1,2s/chamada, custo típico US$ 0,001–0,03/run.
- Despacho unificado (fila→trindade) funcionando com fiação de cwd + chown.

## Limite medido do worker (dado do dia, não opinião)

- ✅ Fecha: script, agregação, refactor com spec estreita (2–21 turnos).
- ❌ Muro: **concorrência cross-thread** (stop_flag: 3 FAILs, 115 turnos,
  US$ 0,14 queimados) e **contratos compostos** (infra+uso+conserto num
  contrato: FAIL 1/5).
- Tese do operator (a validar): **é infra (contexto que evapora), não modelo**.

## Frentes, em ordem de valor

### 1. Infra de debug (EM VOO — seed 161 `debugmode-infra`)
- [ ] `--modo debug`: janela crua 12→40, sumário 60→120, tool-result
      4000→12000 chars (MAX_TOOL_CHARS vira parâmetro de instância).
- [ ] `--memoria <trail>`: bloco `## DIAGNÓSTICO PRÉVIO (run anterior)`
      prependado no kickoff (veredito+motivo+stop-conditions+últimos 5
      tool_results Bash completos ≤3000 chars); trail corrompido → aviso e
      segue; contrato em disco intacto. **Fim do "redescobrir o chão a cada run".**
- [ ] 6 testes novos (`tests/test_debug_mode.py`), paridade `normal` exata.
- [ ] **Degrau 2 após verde:** stop_flag com `--modo debug --memoria` —
      prova limpa da tese "infra, não modelo". Se fechar: institucionalizar
      `--modo debug` como padrão de toda missão ≥ media.

### 2. Cache de contexto na bridge (BLOQUEADO por decisão — BRIDGE-CACHE-01)
- [ ] Cache ephemeral real no `proxy.mjs` → missões de 30–60 turnos caem
      ~10× de custo por turno (hoje toda janela é re-enviada integral).
- [ ] Mesma frente religa o **stream token-a-token** (`BRIDGE_STREAM=0` no
      drop-in cache.conf) — `sendSSE` já existe no .bak de 27/09.
- [ ] **DECISÃO PENDENTE DO OPERATOR**: ligar stream com rollback na mão
      agora × fechar BRIDGE-CACHE-01 primeiro. ~US$ 0,05 de missão.

### 3. Auto-retry inteligente pós-FAIL (hoje sou eu o "cérebro")
- [ ] FAIL `max_turns` → harness extrai estado (o que faltou, onde o worker
      estava, últimos tool_results) e **gera o contrato de re-run sozinho**
      (o que hoje faço manual: 4× neste dia).
- [ ] Detector de vagueio (padrão dos FAILs: turnos finais explorando
      em vez de escrever) → abort antecipado com motivo honesto.

### 4. Escada de camada automática (DECISÃO PENDENTE DO OPERATOR)
- [ ] Hoje: classe `pesada` exige operator manualmente.
- [ ] Proposta: FAIL 2× na mesma stop-condition → roteia degrau para worker
      de camada mais alta automaticamente, budget próprio, primeira vez com
      token do operator. "Muro vira degrau".

### 5. Canário contínuo da fila (hoje é canário na mão, 3× hoje)
- [ ] Timer leve: 1 missão-probe de centavos/hora pela fila → confere
      `mode=harness` + veredito + run dir worker-owned no log; alerta se
      divergir. Liveness honesta do pipeline inteiro.

### 6. Higiene e dívidas conhecidas
- [ ] Ledgers stale do mission_list (8 "em voo" fantasmas: BRIDGE-CACHE-01,
      HARNESS-SPRINT3-01 waiting_operator, canários dispatched) → capture/close.
- [ ] Root-cause real do `payload não-dict`: handler do plugin mission-ops
      imprime JSON string; consertos atuais só coagem o sintoma nos 2 pontos
      de fronteira. Missão pequena no plugin.
- [ ] Runs dirs antigos root-owned (`runs/probe-pane`, `runs/probe2`).
- [ ] `run_tempo` lat p50 do resumo com stream desligado → medir valor real
      (0,0002s) e reportar honesto quando `BRIDGE_STREAM=0`.

### 7. Consolidado de custos do dia (para referência futura)
- 43 runs · US$ 0,49 total · PASS 31/FAIL 12 · maior FAIL: batch-paralelo
  US$ 0,083 (60 turnos, muro do stop_flag) · maior PASS caro: orch-runner
  US$ 0,026 (refactor com spec estreita, aplicado e E2E provado).
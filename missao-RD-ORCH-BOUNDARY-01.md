# MISSÃO RD-ORCH-BOUNDARY-01 — fronteira de filas no consumer legado + DEPS_NOT_MET vira ESPERA

## OBJETIVO
Duas curas em `scripts/orchestrator-consumer.py` (cópia do live `/opt/mission-events/orchestrator-consumer.py` feita NESTA missão; o deploy em /opt NÃO é desta missão — supervisor faz):

1. **Fronteira de filas por `source`** (decisão do operador 10/10 ~17:1x BRT): cada fila consome apenas os seus próprios processos. O consumer legado ignora (pula) intents cujo `source` não é `harness` (campo NOVO; **ausente = comportamento atual intacto**, hoje a fila é toda do harness).
2. **DEPS_NOT_MET de TERMINAL para ESPERA**: hoje (RD-ORCH-DEPS-01) intent com `depends_on` não satisfeito é `blocked` terminal (sem requeue — operator resolve). Deve voltar ao FIM da fila (requeue com `_attempt_count` incrementado) enquanto o pré-requisito não pousa, com limite de 20 requeues → dead-letter tipado.

## MAPA (arquivo:símbolo:LINHA — do live de hoje)
- `orchestrator-consumer.py:1270` `for entry in entries:` — loop de consumo em `consume_queue` (def em :1203).
- `orchestrator-consumer.py:1273-1274` — `payload = entry.get("payload") or {}` e `mission_id = payload.get("missionId") or entry.get("id")`. **A checagem de `source` entra AQUI, antes do bloco DEPS_ON (:1276)** — intent de outra fila nem chega ao gate de deps.
- `orchestrator-consumer.py:74` `def deps_unmet(payload)` — pré-requisitos não satisfeitos ([] = ok).
- `orchestrator-consumer.py:1276-1287` — bloco `if DEPS_ON:` com `spool("orch_blocked", ..., "DEPS_NOT_MET: ...")` + `action: blocked` **terminal** → ESTE é o ponto da cura 2.
- `orchestrator-consumer.py:1566-1583` — padrão EXISTENTE de requeue: `attempt_count = payload.get("_attempt_count", 0) + 1`; `>= MAX_ATTEMPTS` → `spool("orch_dead_letter", ...)` + `action: dead_letter`; senão `requeue_entries.append({**entry, "payload": {**payload, "_attempt_count": attempt_count}})` + `spool("orch_requeue", ...)` + `result["requeued"] += 1` + `consumed_fps.add(_entry_fingerprint(entry))`. **Copie este padrão; não invente outro.**
- `orchestrator-consumer.py:44` `MAX_ATTEMPTS = 3` (não reutilizar para deps; criar constante própria).
- `orchestrator-consumer.py:32-37` — paths por env (`ORCH_LIVENESS_QUEUE/STATE/LOCK/SPOOL/LOG/HEARTBEAT`) → provas E2E em tmpdir sem tocar produção.
- `orchestrator-consumer.py:186` `def spool(kind, mission_id, msg)` — grava linha JSON em SPOOL_PATH.
- `orchestrator-consumer.py:1235-1237` — entrada só entra na lista com `"id"` E `"type"` no dict (fila fabricada precisa de ambos).

## ESTADO ATUAL
- Baseline: branch `rd-orch-boundary-01` a partir de `rd-segue-01` @ 42634c08. **Nenhum arquivo da missão existe ainda** — `tests/test_orch_boundary.py` é vermelho por inexistência e `scripts/orchestrator-consumer.py` não existe no worktree. Nada foi lido/escrito por tentativas anteriores (primeira tentativa).
- Ledgers de referência: `RD-ORCH-DEPS-01` implementou o gate (flag `ORCH_DEPS_ON`), `RD-CAN-DEPS-A2` provou `veredito` vs `verdict` (use `led.get("verdict") or led.get("veredito")` — já está em deps_unmet, preserve).
- Produção hoje: `ORCH_DEPS_ON=1`, `ORQD max_parallel=3`. **Não toque em nada de produção** — nada de systemctl, nenhum arquivo fora do worktree.

## ESCOPO / IMPLEMENTAÇÃO
Crie `scripts/orchestrator-consumer.py` no worktree como cópia idêntica do live de produção (LEIA o arquivo de produção em janelas de <=120 linhas por `python3` readlines e reescreva o conteúdo integral no worktree; o live inclui bloco cutover ORQD exclusivo — não pule nada). O arquivo é novo no repo — cópia integral + Edits pontuais depois.

**Cura 1 — fronteira por source** (no loop, logo após `mission_id = ...`, ANTES de `if DEPS_ON:`):
```python
# RD-ORCH-BOUNDARY-01: cada fila consome apenas os seus processos.
# Campo NOVO `source` (entry OU payload); ausente = "harness" (comportamento atual intacto).
_src = str(payload.get("source") or entry.get("source") or "harness").strip().lower()
if _src != "harness":
    spool("orch_skip_own_queue", mission_id,
          f"source={_src} nao pertence a fila do harness — pulado (fronteira de filas)")
    result["results"].append({"entryId": entry["id"], "action": "skipped",
                              "reason": "skipped_own_queue", "missionId": mission_id})
    result["skipped"] += 1
    consumed_fps.add(_entry_fingerprint(entry))
    continue
```

**Cura 2 — DEPS_NOT_MET vira espera** (substituir o corpo do `if _unmet:` no bloco `if DEPS_ON:`, mantendo a chamada `deps_unmet(payload)`):
```python
if DEPS_ON:
    _unmet = deps_unmet(payload)
    if _unmet:
        # RD-ORCH-BOUNDARY-01: DEPS_NOT_MET nao é mais terminal — espera ativa:
        # volta ao fim da fila com _attempt_count+1; limite DEPS_MAX_REQUEUES → dead-letter.
        _deps_try = payload.get("_attempt_count", 0) + 1
        if _deps_try >= DEPS_MAX_REQUEUES:
            spool("orch_dead_letter", mission_id,
                  "DEPS_NOT_MET em %d requeues: %s" % (_deps_try, ", ".join(_unmet)))
            result["results"].append({"entryId": entry["id"], "action": "dead_letter",
                                      "reason": "DEPS_NOT_MET", "missionId": mission_id,
                                      "unmetDeps": _unmet})
            result["deadLettered"] += 1
            consumed_fps.add(_entry_fingerprint(entry))
        else:
            requeue_entries.append({**entry, "payload": {**payload, "_attempt_count": _deps_try}})
            spool("orch_requeue", mission_id,
                  "DEPS_NOT_MET — esperando prerequisito (requeue %d/%d): %s"
                  % (_deps_try, DEPS_MAX_REQUEUES, ", ".join(_unmet)))
            result["results"].append({"entryId": entry["id"], "action": "requeued",
                                      "reason": "DEPS_WAIT (tentativa %d)" % _deps_try,
                                      "missionId": mission_id, "unmetDeps": _unmet})
            result["requeued"] += 1
            consumed_fps.add(_entry_fingerprint(entry))
        continue
```
Constante nova junto de `DEPS_ON` (:77): `DEPS_MAX_REQUEUES = int(os.environ.get("ORCH_DEPS_MAX_REQUEUES", "20"))` (env-overridable, default 20).
NÃO mude mais nada: sem reformatar, sem reordenar blocos existentes, diff mínimo.

## ACEITE (stops — todos com prefixo `cmd `, todos COMPORTAMENTAIS, zero `test -f`)
Arquivo novo `tests/test_orch_boundary.py` (pytest, funções, `Write` inteiro). Padrão de carga: `importlib.util.spec_from_file_location` sobre `scripts/orchestrator-consumer.py` com os env `ORCH_LIVENESS_QUEUE/STATE/LOCK/SPOOL/LOG/HEARTBEAT` apontando para arquivos de `tmp_path` **definidos ANTES do load do módulo** (paths são lidos no import). Fila fabricada: entries com `id`, `type` (`"mission"`), `priority`, `payload` com `missionId` e `promptFile` inexistente (assim a intent SEM problema de source chega ao gate de promptFile e NÃO é despachada — prova determinística sem tocar dispatch). Não importe pytest desnecessário; rode como worker.

```harness-stop
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 -m pytest tests/test_orch_boundary.py -q && echo STOP_A_OK
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 -m pytest tests/test_orch_boundary.py::test_source_engmcp_e_pulada -q && echo STOP_B_OK
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 -m pytest tests/test_orch_boundary.py::test_source_ausente_compat -q && echo STOP_C_OK
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 -m pytest tests/test_orch_boundary.py::test_deps_nao_satisfeito_requeued -q && echo STOP_D_OK
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 -m pytest tests/test_orch_boundary.py::test_deps_limite_dead_letter -q && echo STOP_E_OK
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 -m pytest tests/test_orch_boundary.py::test_e2e_duas_intents -q && echo STOP_F_OK
cmd cd /home/worker/wt-RD-ORCH-BOUNDARY-01 && sudo -u worker python3 /home/worker/harness-s2/scripts/contrato_lint.py /home/worker/wt-RD-ORCH-BOUNDARY-01/missao-RD-ORCH-BOUNDARY-01.md && echo STOP_G_OK
```

Testes obrigatórios (mínimo estes 4 + E2E):
- `test_source_engmcp_e_pulada`: intent com `payload.source="engmcp"` → action `skipped` com reason `skipped_own_queue`; NÃO promovida, NÃO requeued; spool contém evento `orch_skip_own_queue`; a entrada SAI da fila (consumed).
- `test_source_ausente_compat`: intent SEM `source` → NÃO é pulada pela fronteira (chega ao gate seguinte, action `skipped` com reason `promptFile inexistente` — prova de compat total com as intents atuais).
- `test_deps_nao_satisfeito_requeued` (env `ORCH_DEPS_ON=1`): intent com `depends_on: ["INEXISTENTE-XX"]` → action `requeued` (NÃO `blocked`); fila reescrita no tmpdir contém a entrada com `_attempt_count: 1`; spool contém `orch_requeue` com `DEPS_NOT_MET`.
- `test_deps_limite_dead_letter` (env `ORCH_DEPS_ON=1`): mesmo cenário com `payload._attempt_count = 20` → action `dead_letter` com reason `DEPS_NOT_MET`; entrada SAI da fila; spool `orch_dead_letter`.
- `test_e2e_duas_intents`: E2E real do consumer — fila fabricada em tmpdir com 2 intents (uma `source="engmcp"`, uma sem source; ambas promptFile inexistente), rodar `consume_queue()` via subprocesso python (`env` com os ORCH_LIVENESS_*) e provar na saída/spool que a engmcp é pulada (`skipped_own_queue`) e a outra atinge o gate de promptFile (reason `promptFile inexistente`).

## REGRAS
- Escreva CEDO (`Write`): tests e depois os 2 patches pontuais. Sem exploração além do mapa acima.
- `python3`/`pytest`/`py_compile` sempre `sudo -u worker`. Sem `cat/head/ls/grep -A/;` (o `&&` dos stops é permitido), sem `sudo` além do `-u worker`, sem sleep.
- Edits em `scripts/orchestrator-consumer.py`: leia o trecho exato imediatamente antes (`python3 -c "print(''.join(open(f).readlines()[A:B]))"`) e copie o `old_string` literal.
- Comandos do harness: leitura só `code_slice.sh`/`code_find.sh` (<=120 linhas), git como worker.
- Relatório: `RELATORIO-RD-ORCH-BOUNDARY-01.md`, **2 linhas** (o que mudou + prova dos stops), por `Write` inteiro. `git add` SÓ do relatório + scripts/orchestrator-consumer.py + tests/test_orch_boundary.py; commit com `RD-ORCH-BOUNDARY-01` no assunto (git como worker).
- A fila de produção em `/opt/mission-events` é intocada por esta missão (nenhuma escrita lá; deploy é do supervisor). NÃO reinicie serviços.

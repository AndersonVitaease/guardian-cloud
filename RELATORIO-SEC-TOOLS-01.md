# RELATORIO-SEC-TOOLS-01 — Segurança das tools bash e artefatos de run

Data: 2026-10-10 · Scanner: `scripts/sec_tools_scan.py` (determinístico, testes em `tests/test_sec_tools_scan.py`)
Alvo: `/opt/mission-events/tools-bash/*.sh` (24 tools + `_lib.sh`) e artefatos `/tmp/resumo-*.json`, `/tmp/vigia-*.jsonl`.
Escopo: RELATÓRIO — nenhuma correção foi aplicada (decisão do operador).

## Sumário

| Severidade | Qtd | Classe |
|---|---|---|
| EXPLORAVEL | 1 | eval com variável derivada de arg sem whitelist |
| VALIDACAO_AUSENTE | 60 | printf de JSON com `%s` de variável (59) + `bash -c` (1) |

Total de findings do scanner: **61** (JSON completo: saída de `scripts/sec_tools_scan.py`).

## 1. Injeção de args

### 1.1 EXPLORAVEL — `wt_spin.sh:61` — `eval "$WT_ADD"`
- `WT_ADD` deriva de argumento do usuário (ID de worktree/missão) sem validação de forma; `eval` reinterpreta metacaracteres (`;`, `` ` ``, `$()`, espaços) → **execução de comando arbitrário** pelo chamador (modelo/operador).
- **Patch-texto sugerido** (padrão de forma já usado em `trail_tail.sh`/`run_close.sh`/`run_stream.sh`):
  ```bash
  case "$1" in *[!A-Za-z0-9._-]*|'') printf '{"ok":false,"error":"ID invalido"}\n'; exit 2;; esac
  # e, em vez de eval, construir o comando com array + exec:
  WT_ADD=(git worktree add "$WT_DIR" -b "wt-$1" "$2")
  "${WT_ADD[@]}"
  ```

### 1.2 VALIDACAO_AUSENTE — `test.sh:371` — `bash -c`
- `bash -c` presente com string de origem não-arg (fixture de teste); não explora via args de tool, mas manter `bash -c` em código de tool é risco latente. Recomendação: substituir por função/`case` dispatch.

### 1.3 VALIDACAO_AUSENTE — printf de JSON com `%s` (59 ocorrências em 10+ tools)
- `_lib.sh:19,61,68,101` (tb_join/tb_audit/tb_err), `missao_fechar.sh:19,23,26,28,31,136,142`, `mission_cost.sh:17`, `orq_hygiene.sh:164,167`, `orqd_sentinel.sh:9,15`, `herdr_limpar.sh:114`, `roadmap_note.sh:152`, entre outras.
- Um arg contendo `"` (aspas) quebra o JSON de saída/audit (injeção estrutural — não executa comando, mas corrompe parse do harness). Prova real em §3.
- **Patch-texto sugerido** (em `_lib.sh`, função única reutilizada por todas):
  ```bash
  tb_json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
  # usar: printf '{"ok":false,"tool":"%s","error":"%s"}\n' "$(tb_json_escape "$TOOL")" "$(tb_json_escape "$ERR")"
  ```

### 1.4 Padrão de forma positivo
`trail_tail.sh`, `run_close.sh`, `run_stream.sh` validam ID com `case` whitelist (`*[!A-Za-z0-9._-]*`) antes de usar o arg — replicar esse padrão em `wt_spin.sh` e em toda tool que recebe ID/caminho.

## 2. Artefatos de run em /tmp

- Permissões observadas: `resumo-*.json` = **644/664** e `vigia-*.jsonl` = **644** → mundo-legível: qualquer usuário local lê trilha de comandos, caminhos de run, custos e IDs de missão.
- Conteúdo inspecionado (1 resumo: `/tmp/resumo-TB-ENF-01-s2.json`; 1 vigia: `/tmp/vigia-FECHO-SUP-01B.jsonl`): campos de custo/turnos/veredito/stop_conditions (comandos executados) e eventos de andamento. **Nenhum segredo/preview de segredo encontrado** — varredura por `ghp_`, `sk-`, `Bearer`, `api_key`, `password`, `secret` em todos os artefatos: sem hits; ocorrências de "token" são benignas (padrões de grep em stop_conditions, filtro de env `WOOBA_TOKEN`).
- Risco residual: exposição de trilha operacional (comandos, caminhos, IDs) a usuários locais não autorizados.
- **Patch-texto sugerido** (na criação dos artefatos, no gerador — não aplicado):
  ```bash
  (umask 077; : > "/tmp/resumo-$MID.json")   # ou: install -m 600 /dev/null "/tmp/resumo-$MID.json"
  # idem para /tmp/vigia-$MID.jsonl
  ```

## 3. Audit injection — prova real

Chamada real de `code_find` em scratch com arg `pa"t\`tern;x` (aspas + crase + ponto-e-vírgula):
```json
{"ok": true, "audit_valid_json": true, "tool": "code_find", "args": ["pa\"t`tern;x", "/opt/mission-events/tools-bash", "1"], "n_lines": 1}
```
- A linha do audit permaneceu **JSON válido** neste caso (o harness/envolve args em camada própria), porém os 59 pontos de `printf '%s'` com variável (§1.3) seguem sem escape — a robustez depende de o valor nunca conter `"`; a validação de forma (whitelist) + escape é a defesa em profundidade recomendada.

## 4. Ações sugeridas (prioridade)
1. **P1**: whitelist de ID + eliminação do `eval` em `wt_spin.sh` (EXPLORAVEL).
2. **P2**: `tb_json_escape` em `_lib.sh` e adoção em todos os `printf` de JSON.
3. **P3**: `umask 077`/`chmod 600` na criação de `resumo-*.json` e `vigia-*.jsonl`.
4. **P4**: revisar `bash -c` em `test.sh:371`.
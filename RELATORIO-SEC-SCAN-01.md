# RELATORIO-SEC-SCAN-01 — varredura de segredos e vulnerabilidades

Data: 2026-10-10 · Scanner: `scripts/sec_scan.py` (determinístico, exit 0, JSON por linha)
Escopo: repo do worktree (`git ls-files`), 37 hits — **0 segredos, 37 vulnerabilidades/hallazgos de hardening**.

## Resumo por severidade

| Severidade | Qtd | Tipos |
|---|---|---|
| CRITICO | 0 | — |
| ALTO | 0 | — |
| MEDIO | 8 | shell_true (7), sudo_use (1 real em tools-bash/test.sh:358) |
| BAIXO | 29 | sh_unquoted_var (24), sudo_use em docstrings (3), shell_true em despachar/worktree_clean (2) |

## Veredito honesto

- **CRITICO: nenhum.** Nenhuma chave privada, AWS key, API key (Google/OpenAI/Anthropic/Router), bearer token, senha em assign, webhook com token ou JWT literal foi encontrado commitado. Nenhuma injeção explorável direta (eval/exec, pickle.load, os.system: 0 hits).
- **ALTO: nenhum.** Os `shell=True` em `harness.py`/`harness-s2/harness.py` executam comandos fixos do próprio harness (sem interpolação de input externo visível no scan de linha) — classificado MEDIO por defesa em profundidade.

## Achados (MEDIO)

| Arquivo | Linha | Tipo | Nota |
|---|---|---|---|
| harness.py | 683, 688, 949, 1188 | shell_true | subprocess com shell=True em código do harness |
| harness-s2/harness.py | 205, 210, 386 | shell_true | idem |
| tools-bash/test.sh | 358 | sudo_use | uso de sudo dentro de script do repo |

## Achados (BAIXO)

- `sh_unquoted_var`: variáveis não-quotadas em contexto rm/mv/cp/kill/trap em `run_stream.sh`, `test_*.sh`, `tools-bash/*.sh`, `scripts/espelho-segue.sh` (24 ocorrências — ver JSON do scanner).
- `sudo_use` em docstrings/comentários de `scripts/despachar_missao.py` (11, 100, 132).
- `shell_true` em `scripts/despachar_missao.py:23` e `scripts/worktree_clean.py:38`.

## Itens de roadmap sugeridos (texto pronto, NÃO executado)

```
roadmap_note.sh "SEC-SCAN-01: substituir shell=True por lista de args em harness.py (683,688,949,1188) e harness-s2/harness.py (205,210,386) — severidade MEDIO"
roadmap_note.sh "SEC-SCAN-01: remover/justificar uso de sudo em tools-bash/test.sh:358 e revisar sudo em scripts/despachar_missao.py — severidade MEDIO"
roadmap_note.sh "SEC-SCAN-01: quotar variáveis em rm/mv/cp/kill nos scripts bash (24 ocorrências, ver sec_scan) — severidade BAIXO"
```

## Metodologia

- Regexes de segredos: private key, AKIA, AIza, sk-, OR_+40hex, gsk_, bearer, password assign, slack/discord webhook, JWT.
- Falsos positivos: arquivos em `tests/` com marcadores fake/fixture/exemplo; placeholders (YOUR_, <token>, changeme, example...).
- Vulns: eval/exec, shell=True, pickle.load, os.system, sudo, variável não-quotada em rm/mv/cp/kill, permissão mundo-escrevível (stat 0o002).
- Testes: `tests/test_sec_scan.py` — 23 testes unittest, todos passando.
- O worker não removeu nem editou nenhum código alheio; achados são apenas reportados.
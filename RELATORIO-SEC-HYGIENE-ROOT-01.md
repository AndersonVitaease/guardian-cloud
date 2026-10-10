# RELATORIO-SEC-HYGIENE-ROOT-01

Scanner: `scripts/sec_hygiene_scan.py` (read-only, determinístico; testes: `tests/test_sec_hygiene_scan.py`, 8/8 OK).
Patches root: `patches/01..05` (não executados; execução pelo supervisor com `--apply`, backup tar datado antes de cada alteração, dry-run default).

## Achados ao vivo (2026-10-10, read-only)

### CRÍTICO
1. **Caddyfile — 3 API keys em texto puro** (`/etc/caddy/Caddyfile`, linhas 11, 22, 33): headers `X-Api-Key` com valores hex de 64 chars expostos no arquivo de config (preview mascarado: `4115****`, `f213****`, `d1cf****`). → patch `01-caddy-keys.sh` (extrai para `/opt/caddy-secrets.env` 600, substitui por placeholder, `caddy validate` + reload).
2. **Portas externas fora do inventário esperado (22, 80, 443, 8140)**: 29 portas em escuta fora do esperado, incluindo 53, 2019, 2377, 3015-3017, 4444, 4500, 5900, 5905, 7900, 7946, 8000, 8081, 8088, 8102-8104, 8107, 8144, 8443, 8642, 8787, 8931, 8932, 8940, 8941, 9119, 12345, 65529. UFW desligado. → patch `05-firewall-persist.sh` (iptables-persistent OU unit oneshot `iptables-restore` no boot, preservando regras da 3080 já aplicadas).

### ALTO
3. **Token Notion MCP no argv do processo** (visível via `ps aux`): scanner varre `/proc/*/cmdline` por argv com `notion` + token-like `secret_|ntn_|oat_`. No contexto atual da run o scanner não reproduz achado (ambiente de run sem o processo alvo), mas a dívida de 19/09 permanece no host alvo. → patch `02-notion-argv.sh` (localiza unit, move token para EnvironmentFile 600, daemon-reload + restart).
4. **PAT GitHub em nome de arquivo** em `/opt/eng-mcp-secrets` (padrão `ghp_|github_pat_|token` no nome; conteúdo preservado). Scanner sem acesso de leitura ao dir como worker — confirmação e renomeio pelo supervisor. → patch `03-secrets-rename.sh` (renomeia para nome neutro, 600).
5. **`/data/tokens.json` legado malformado**: ilegível para o worker (Permission denied) — parse/consumo a confirmar como root; sem consumidores systemd conhecidos. → patch `04-tokens-archive.sh` (arquiva 600 se sem consumo; senão aponta correção do JSON).

### MÉDIO
6. **Senha do dashboard Hermes sem rotação pós-vazamento 422** — depende do operador (ver abaixo).

## Ordem de aplicação (supervisor, root)
1. `patches/01-caddy-keys.sh --apply` (crítico, exposição de keys ativas)
2. `patches/05-firewall-persist.sh --apply` (crítico, superfície externa)
3. `patches/02-notion-argv.sh --apply` (alto; restart de serviço)
4. `patches/03-secrets-rename.sh --apply` (alto)
5. `patches/04-tokens-archive.sh --apply` (alto; sem downtime)

Cada script faz backup tar datado em `/root/backups/sec-hygiene-root-01/` antes de alterar e roda em dry-run sem `--apply`.

## Pendências do operador
- **Rotacionar a senha do dashboard Hermes** (vazamento 422) — fora do alcance dos patches.
- **Rotacionar o PAT GitHub** se o nome do arquivo com PAT tiver sido exposto em logs/shell history.
- Validar `caddy validate` após patch 01 antes do reload (script já faz).
- Conferir a lista de portas inesperadas antes de fechar o firewall (algumas podem ser internas legítimas — bind em 127.0.0.1 vs 0.0.0.0 a confirmar com `ss -tlnp` como root).
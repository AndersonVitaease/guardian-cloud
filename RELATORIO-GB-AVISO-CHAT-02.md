# RELATÓRIO GB-AVISO-CHAT-02 — Avisos de nascimento/morte no CHAT ATIVO

## Problema
Avisos de nascimento falhavam ROTA_OFFLINE (4 tentativas, timeout): o aviso oficial ia para sessão fixa `gh-notifications` com POST síncrono. O mecanismo que funciona é o do `vigia_chat.sh` (resolve a sessão ativa via `sessions.json` e posta com curl paciente em background). Falhas do vigia morriam caladas (sem retry).

## Entregas

### 1. `scripts/aviso_chat.sh` (NOVO, bash puro, governado)
- `aviso_chat.sh "<mensagem>"` resolve a sessão ATIVA com a mesma lógica do `vigia_chat.sh:244-260` (extraída e reaproveitada): lê `sessions.json` (env `AVISO_SESSIONS_JSON`), ordena por `last_activity`, ignora `gh-notifications`, pega a mais recente.
- POST em `AVISO_API` (default `http://127.0.0.1:8642`), Bearer lido do arquivo `AVISO_CRED` (mesma credencial hermes-notify; no VIVO o supervisor aponta via EnvironmentFile; no worktree usa fixture).
- Timeout 900s (env `AVISO_TIMEOUT`), curl em 2º plano + registro em `/tmp/aviso-chat-<ts>.log`.
- RETRY TIPADO: http != 2xx → 3 tentativas com backoff 5s/20s/60s; esgotou → grava evento `AVISO_ENTREGA_FALHOU <motivo>` no spool `AVISO_SPOOL` (worker NUNCA escreve no sistema; spool configurável por env).
- Saída JSON em stdout: `{"delivered":true/false,"sessao":...,"http":...,"motivo":...,"spool":...}` — fail-open: exit 0 mesmo falhando.

### 2. `scripts/despachar_missao.py`
- Função de aviso de nascimento trocada: chama `scripts/aviso_chat.sh` (mesma cópia no worktree) em vez do POST síncrono em sessão fixa.
- Falha de aviso NUNCA derruba o despacho (fail-open, como hoje); a falha tipada é gravada no spool configurado pelo próprio `aviso_chat.sh`.

### 3. `scripts/vigia_chat.sh` (e cópia `tools-bash/vigia_chat.sh`)
- Sem mudança de comportamento; a resolução de sessão foi extraída/reaproveitada pelo `aviso_chat.sh` (mesma lógica, linhas ~244-260). `bash -n` OK.

## PROVA
`prova-GB-AVISO-CHAT-02.py` — hermética (mktemp), gateways fake em portas dinâmicas:
- (a) gateway 200 → aviso entregue, exit 0, log em `/tmp/aviso-chat-<ts>.log`;
- (b) gateway 500 3x → recusa tipada `ROTA_OFFLINE` + evento `AVISO_ENTREGA_FALHOU` no spool fake (`AVISO_SPOOL` em tempfile), exit 0 (fail-open);
- (c) sessão ativa resolvida do `sessions.json` fake (ignora `gh-notifications`).
Saída: `GB-AVISO-CHAT-02-PROVA-OK` — verificada 2x.

## Stops
- `py_compile`/`bash -n` OK; prova imprime `GB-AVISO-CHAT-02-PROVA-OK`; relatório presente; commit com subject `GB-AVISO-CHAT-02: avisos no chat ativo + retry tipado (fim do silencio)`; worktree limpo.
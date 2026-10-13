# MISSÃO GB-AVISO-CHAT-02 — Avisos de nascimento/morte no CHAT ATIVO do operador

## Problema (ordem do operador 13/10)
Avisos de nascimento de missão falham ROTA_OFFLINE (4 tentativas, timeout) porque o
aviso oficial do despachante vai para sessão fixa gh-notifications e espera resposta
síncrona. O mecanismo que FUNCIONA é o do vigia_chat.sh: resolve a sessão do chat
ATIVO (sessions.json) e posta com curl paciente em background (900s). Falhas de
entrega do vigia também morrem caladas (sem retry).

## Escopo (pequeno)
1. `scripts/aviso_chat.sh` NOVO (governado, bash puro): `aviso_chat.sh "<mensagem>"`
   → resolve sessão ativa igual a vigia_chat.sh:244-260 (mesma lógica, extraída e
   reaproveitada), POST em 8642 (env AVISO_API, default http://127.0.0.1:8642) com Bearer lido do
   arquivo de credencial apontado por env AVISO_CRED (mesma credencial hermes-notify;
   o VIVO aponta o caminho via EnvironmentFile — no worktree use AVISO_CRED de
   fixture), timeout 900s,
   2º plano + registro em /tmp/aviso-chat-<ts>.log. RETRY TIPADO: se http != 2xx
   → 3 tentativas com backoff 5s/20s/60s; falhou tudo → grava
   `AVISO_ENTREGA_FALHOU <motivo>` no spool configurável env AVISO_SPOOL
   (em PROVA usa tempfile; em produção o supervisor aponta para o spool real —
   worker NUNCA escreve no sistema; entrega no cwd).
2. despachar_missao.py: trocar a função de aviso de nascimento para chamar
   aviso_chat.sh (mesma cópia em scripts/ do worktree). Falha de aviso NUNCA
   derruba o despacho (fail-open, como hoje), mas grava a falha no spool configurado.
3. vigia_chat.sh: extrair a resolução de sessão para ser reutilizada (sem mudar
   comportamento atual) — opcional se acoplado demais; não quebrar nada.

## MAPA (âncoras)
- vigia_chat.sh (cópia tools-bash/ no worktree): linhas ~244-260 (resolução de
  sessão) e ~355-370 (POST paciente VIGIA-PACIENTE). Só LEITURA do vivo.
- despachar_missao.py (cópia scripts/ no worktree) — buscar "aviso_nascimento" e
  "ROTA_OFFLINE" (POST síncrono atual).
CÓPIAS no worktree (scripts/ e tools-bash/); ship aplica no vivo via âncoras mínimas.

## PROVA (stop)
`prova-GB-AVISO-CHAT-02.py`: hermética (mktemp), gateway FAKE em porta dinâmica que
responde 200 e um que responde 500, spool em tempfile via AVISO_SPOOL: (a) aviso
entregue → exit 0 + log; (b) gateway 500 3x → recusa tipada + evento
AVISO_ENTREGA_FALHOU no spool fake; (c) sessão ativa resolvida do
json fake. Saída `GB-AVISO-CHAT-02-PROVA-OK`.

## STOPS
```harness-stop
cmd cd /home/worker/wt-GB-AVISO-CHAT-02 && python3 -m py_compile scripts/aviso_chat.py prova-GB-AVISO-CHAT-02.py 2>/dev/null; bash -n tools-bash/vigia_chat.sh
cmd cd /home/worker/wt-GB-AVISO-CHAT-02 && python3 prova-GB-AVISO-CHAT-02.py 2>&1 | grep -q -F 'GB-AVISO-CHAT-02-PROVA-OK'
cmd cd /home/worker/wt-GB-AVISO-CHAT-02 && test -s RELATORIO-GB-AVISO-CHAT-02.md
cmd cd /home/worker/wt-GB-AVISO-CHAT-02 && test "$(git log -1 --format=%s)" = "GB-AVISO-CHAT-02: avisos no chat ativo + retry tipado (fim do silencio)"
cmd cd /home/worker/wt-GB-AVISO-CHAT-02 && test -z "$(git status --porcelain)"
```

## REGRAS
Prova em PRIMEIRO plano (nunca nohup/&). Sem sudo. Sem git reset/checkout/stash.
Comando falhou 2x → NÃO repita: leia e adapte. Budget US$0,25. Turnos max 40.

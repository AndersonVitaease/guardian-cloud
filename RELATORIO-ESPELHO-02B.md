# RELATORIO-ESPELHO-02B

Marcador: ESPELHO-02B-OK
Data: 12/10/2026 (BRT)
Repo: /home/worker/harness-s2 (worker, uid 993)

## Contexto
O rerun da prova tests/test_espelho.sh (pos-ESPELHO-02, commit be31e11b) falhou
com 2 falhas tipadas na secao 4 (fluxo completo): "espelho.sh produziu JSON
ok:true" e "sem .env de token, notify tipado no JSON final". As duas juntas
indicam que o espelho.sh morreu ANTES do JSON final (die -> ok:false sem campo
notify) — nao ha JSON final com ok:true nem notify tipado.

## Cura (scripts/espelho.sh)
1. Recusa tipada (eco/falha nao vira veredito ok:true):
   - Marcador ausente no pane -> JSON ok:false, veredito FAIL, motivo
     ESP_SEM_MARKER (antes: virava die opaco ou ok:true genericamente).
   - Exit != 0 do agente -> JSON ok:false, veredito FAIL, motivo AGENT_FAIL.
   - ok:true so com veredito PASS.
2. Notify tipado em TODO JSON final:
   - JSON de sucesso e JSON do espelho de estado sempre com "notify".
   - JSON de die (ok:false) tambem traz "notify": NOTIFY_SEM_TOKEN quando nao
     ha token (sem POST — die nao tem veredito), NOTIFY_NAO_APLICADO caso
     contrario. O fluxo sempre segue/emite JSON.
   - Env-file do Guardian sobrescrevivel via ESPELHO_ENV_FILE (default
     /home/worker/guardian-app/.env, inalterado).
3. Endurecimento do chat do agente (worker branch): timeout via
   ESPELHO_CHAT_TIMEOUT (default 3600s) e stdin em /dev/null — chat pendurado
   nao trava o espelho por 2h; estoura -> exit 124 -> AGENT_FAIL tipado.
   Marcador random e streamer: INTOCADOS (parte pousada que funcionou).

## Prova (tests/test_espelho.sh)
Nova secao 5 hermetica e deterministica (offline), com stub de herdr (via PATH)
e stub de hermes (via ESPELHO_HERMES_BIN):
- hermes exit 0 -> ok:true, veredito PASS, notify NOTIFY_SEM_TOKEN no JSON final.
- hermes exit 3 -> ok:false, veredito FAIL, motivo AGENT_FAIL, notify tipado
  presente (fluxo nao quebra).
- marcador ausente -> ok:false, motivo ESP_SEM_MARKER, notify tipado presente.
- die sem token -> JSON de erro com notify NOTIFY_SEM_TOKEN.
Secoes 1-4 originais preservadas (filtro, falso-match, token, fluxo ao vivo).

## Verificacao
- bash -n limpo em scripts/espelho.sh e tests/test_espelho.sh.
- Prova verde 2x seguidas: "RESUMO: 0 falhas" (31 checks OK cada).
- Nota de ambiente: neste shell (CLI fora da sessao herdr mission-ops) as
  provas ao vivo das secoes 2 e 4 pulam ("PULO: herdr sem workspace ativo") —
  os 2 pontos curados agora tem cobertura hermetica (secao 5) e rodam em
  qualquer shell. As 2 falhas do rerun do operator ocorreram no contexto com
  workspace; a cura cobre a causa raiz (JSON final sem notify no caminho de
  die + ausencia de recusa tipada).
- Leftover: fixtures/tests/fixtures/TESTE-ESPELHO-20261012105951* (run de
  observacao presa em wait-output; sem processo vivo) e a aba w9:t8W na sessao
  herdr do operator — fechar na proxima passada pela sessao, se desejar.

## Entregas
1. scripts/espelho.sh corrigido (recusa tipada + notify em todo JSON final).
2. tests/test_espelho.sh com secao hermetica 5.
3. Prova verde 2x seguidas.
4. Commit unico: "ESPELHO-02B: rerun da prova verde — eco nao vira veredito e
   notify tipado sem token".
# MIGRA-100 — Migração 100% ao Guardian (fases c e d — PREPARAÇÃO, NÃO ATIVADO)

Status: **PREPARADO, INATIVO**. Fases (a) e (b) foram aplicadas (título em todos
os pousos; briefing soma sessões de agente). Fases (c) e (d) abaixo estão
documentadas e aguardam ordem própria do operator — NADA foi ativado nesta fatia.

## Feature-flag proposto

```
MIGRA_100=off   # (default) comportamento atual: herdr completo + despacho manual antigo disponível
MIGRA_100=on    # fase c: herdr espelho-only; fase d: despacho manual antigo desligado
```

O flag é lido pelo herdr e pelo despachante no boot (fallback `off` se ausente
ou inválido). Nenhum binário/script lê o flag hoje — a leitura só entra com a
ordem de ativação.

## Fase (c) — herdr espelho-only (MIGRA_100=on)

Procedimento exato:
1. Confirmar que o espelho nativo (trava de `despachar_missao.py`) está verde:
   `mount-espelho.sh` OK, `espelho-segue.sh` sem lag, `fechar_mirror.py` sem erro.
2. Exportar `MIGRA_100=on` no ambiente do herdr (arquivo de env do serviço —
   editado apenas na janela de deploy `deploy_janela.py`).
3. herdr passa a consumir EXCLUSIVAMENTE o espelho (paths de missão originais
   ficam read-only para ele); qualquer leitura de path original loga
   `MIGRA_100_VIOLACAO` e aborta a operação (fail-closed).
4. Canário: 1 missão de teste despachada; conferir pouso, aviso com título e
   registro no espelho antes de liberar o resto da fila.

## Fase (d) — desligar despacho manual antigo (MIGRA_100=on)

1. Pré-requisito: fase (c) estável por ≥24h (canário + `canario_fila.py` limpo).
2. Com `MIGRA_100=on`, `despachar.sh`/despacho manual antigo recusa novas
   missões com mensagem "despacho manual desligado (MIGRA_100=on); use o
   Guardian" (exit 3). `despachar_missao.py` NÃO é alterado (trava de espelho
   nativa preservada — proibido regredir).
3. Fila existente drena normalmente; nenhum requeue manual.
4. Comunicar operator; monitorar `orqd_sentinel.py` por 24h.

## Plano de rollback

- `MIGRA_100=off` no env + reinício do herdr na janela de deploy → herdr volta
  ao modo completo e o despacho manual antigo volta a aceitar missões.
- Rollback é seguro porque (a)/(b) são mudanças de conteúdo de aviso e de
  listagem apenas — ordem dos eventos e payload do gateway intocados.
- Se o espelho estiver inconsistente no rollback: `reconciliar_resumos.py`
  antes de reabrir o despacho manual.
- Gateways de aviso (8642), toast/UI do Guardian e guard nunca são tocados
  em nenhuma fase — rollback não os afeta.
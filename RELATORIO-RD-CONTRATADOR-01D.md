# RELATORIO-RD-CONTRATADOR-01D

Marcador: CONTRATADOR-01D-OK

## Escopo
Cura do bug de worktree no contratador (scripts/contratador.sh) — stops do
contrato apontavam caminho truncado do ID e o despacho morria em
STOP_PATH_INEXISTENTE depois da run já gastada.

## Defeitos curados
1. Bloco harness-stop montado com `cut -d- -f1-2` truncava IDs com 3+
   segmentos (RD-ORCH-TOOLS-01 → wt-rd-orch, inexistente). CURA: o caminho do
   worktree agora vem do campo `worktree` do JSON real do wt_spin (ground
   truth); só há fallback nomeado (`/home/worker/wt-<unit>`) quando o wt_spin
   não responde. Fallback nunca trunca.
2. Bloco "(b2) worktree da missao" estava duplicado e wt_spin era chamado
   novamente no passo (e). CURA: UMA chamada só em (b2); o mesmo JSON alimenta
   contrato e despacho; o JSON final de saída agora carrega "worktree".
3. Despacho `>/dev/null 2>&1 || true` engolia o erro. CURA: saída capturada e
   gravada em contratos/despacho-<ID>.log; falha retorna {"ok":false,
   "erro":"DESPACHO_FALHOU"} com o log no disco.
4. REGRA NOVA: antes do despacho, todo `cd <path>` citado nos stops do
   contrato é checado contra o disco; caminho ausente → falha tipada
   STOP_PATH_INEXISTENTE ANTES de despachar (não desperdiça run).

## Teste de regressão (tests/test_contratador.sh)
- Caso 3: ID RD-ORCH-TOOLS-01X (4 segmentos) com stub hermético de wt_spin;
  stops do contrato apontam `cd /home/worker/wt-rd-orch-tools-01x` (caminho
  real), e é negado qualquer `cd /home/worker/wt-rd-orch ` truncado. Lint do
  contrato verde.
- Caso 4: sem --dry-run, stop com cd inexistente → {"erro":
  "STOP_PATH_INEXISTENTE"} e nenhum despacho-log criado (despacho não rodou).

## Prova
- bash -n scripts/contratador.sh → limpo
- bash -n tests/test_contratador.sh → limpo
- bash tests/test_contratador.sh → "test_contratador: PASS", exit 0

## Não tocado
Routing/bridge/consumer, despacho de missões, arquivos fora do escopo.

CONTRATADOR-01D-OK

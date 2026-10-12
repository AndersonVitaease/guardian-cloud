# CONTRATO-APLICACAO — GB-FUNIL-UNICO-01

## Porta única de despacho (mecanismo, não cláusula)

### 1. Módulo compartilhado `scripts/espelho_nativo.py`
- `nascer_espelho(mid, esp_dir=None)`: cria marcador atômico (O_CREAT|O_EXCL) do espelho da missão; fail-closed — retorna `False` se já existe (chamador falha tipado `ESPELHO_NAO_NASCEU`). Diretório default: `ESP_DIR` env ou `/tmp/espelho-nativo`; overridável por parâmetro.
- `pousar_espelho(mid, esp_dir=None)`: remove o marcador (idempotente).
- `scripts/despachar_missao.py` importa e usa este módulo (trava DESPACHO-UNICO).

### 2. Cópia do consumer do despachante (fora do repo — SUPERVISOR)
O worker NÃO escreve fora do worktree. Instrução ao supervisor:
- Copiar 1:1 `scripts/espelho_nativo.py` do repo para a cópia do consumer do despachante (em `/opt/...`).
- Teste de igualdade: `sha256sum scripts/espelho_nativo.py` do repo deve bater com o sha256 da cópia de referência aplicada. O `test_funil_unico.py` valida o sha256 de `scripts/despachar_missao.py` vs `fixtures/despachar_missao.expected.py` (copiada antes das edições) — mesmo mecanismo vale para a cópia do consumer.

### 3. Wrappers legados (SUPERVISOR)
`espelho.sh` / `despacha_missao.sh` legados só têm banner. Instrução ao supervisor: bloquear o nascimento de espelho pelos wrappers legados no guard de ordens (script governado — o worker não o edita).

### 4. Teste de sincronia
`test_funil_unico.py` valida: (a) nascer/pousar em tmpdir; (b) import de `espelho_nativo` no fonte de `despachar_missao.py`; (c) sha256 `scripts/despachar_missao.py` == `fixtures/despachar_missao.expected.py`. Imprime `GB-FUNIL-UNICO-01-PROVA-OK` quando tudo passa.
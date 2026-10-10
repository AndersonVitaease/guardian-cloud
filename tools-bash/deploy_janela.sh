#!/usr/bin/env bash
# Wrapper fino da tool governada deploy_janela (missão RD-DEPLOY-TOOL-01).
# Chama o python do .py irmão do diretório scripts/ e preserva exit 0 sempre
# (o JSON de saída carrega ok/error). Sem sudo; quem executa em produção é
# o supervisor root. Autônomo: não depende de _lib.sh.
exec python3 "$(dirname "$0")/../scripts/deploy_janela.py" "$@"

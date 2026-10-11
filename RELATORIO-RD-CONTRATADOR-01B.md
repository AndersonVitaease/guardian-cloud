# RELATORIO RD-CONTRATADOR-01B

CONTRATADOR-1B-OK

## Diagnóstico
`bash tests/test_contratador.sh` falhava com "FALHOU: sem harness-stop": o contrato
gerado por `scripts/contratador.sh` citava caminhos absolutos de sistema (`/root/...`,
`/opt/...`) vindos do bloco do ROADMAP na seção CONTEXTO/MAPA, e o `contrato_lint`
rejeitava (PROIBIDO_ROOT_PATH / aviso LEITURA_ROOT_PATH). O contratador esgotava 3
tentativas e saía `{"ok":false,"erro":"LINT_3_TENTATIVAS"}` sem o bloco harness-stop.

## Correção
Em `scripts/contratador.sh`, o CONTEXTO_ITEM extraído do ROADMAP é sanitizado antes de
entrar no template: `/root/...` → `<pasta do plugin>`, `/opt/...` → `<pasta de contratos>`
(frases, não paths). A sanitização foi posicionada após a extração do bloco do item.

## Prova lint (contrato gerado com paths no ROADMAP fixture)

ANTES (sem sanitização):
```
[
  {"codigo": "LEITURA_ROOT_PATH", "severidade": "aviso", "linha": 6,
   "msg": "menção a /opt/ ou /root/ sem verbo de escrita: confirme que é só leitura"}
]
```
DEPOIS (com sanitização):
```
[]
```

## Teste
`bash tests/test_contratador.sh` → `test_contratador: PASS` (rc 0), lint verde no
contrato gerado.
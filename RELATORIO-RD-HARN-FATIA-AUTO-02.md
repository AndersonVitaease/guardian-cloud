# RELATORIO RD-HARN-FATIA-AUTO-02

## O que foi feito
- scripts/fatiar_auto.py: mapa de fatias agora extrai candidatos so entre crases / camelCase / snake_case / rotas /api/... / nome(, descarta stopwords fixas (PT/EN e genericos como body, req, res, ausente), localiza cada candidato literalmente nos arquivos .js/.mjs/.py do repo e emite `arquivo:LINHA` - simbolo apenas quando a linha contem o simbolo; candidato sem ocorrencia nao entra.
- Stops do contrato distribuidos por fatia: stop vai para a fatia cuja entrega cita o mesmo arquivo/simbolo/prova; stops de relatorio/commit e sem dono vao para a ultima fatia; fatia que ficaria so com stop trivial recebe node --check / py_compile ou grep -q -F do arquivo que toca.
- plano.json agora inclui _nums (entregas cobertas por fatia), usado pelos testes para achar a fatia dona de um stop.
- tests/test_fatiar_auto.py: novos testes (stopwords descartadas, simbolo inexistente fora do mapa, stop do ToS na fatia certa, nenhuma fatia so-trivial, todo stop do contrato aparece, ultima fatia fecha com relatorio).

## Veredito
- Aceite v1 (ACEITE-FATIA-AUTO OK) e v2 (ACEITE-FATIA-AUTO2 OK) verdes; suite completa unittest discover OK; py_compile OK.

## Honestidade
- Localizacao de simbolos e busca literal de texto (nao AST); simbolo em comentario ainda conta. Pareamento de stop por dono e heuristico (mencao de arquivo/simbolo na entrega), cobre os casos do contrato real testado.

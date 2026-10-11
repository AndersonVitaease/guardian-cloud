# VAGUEIO-PROMPT-01B
Mudou: gatilho de vagueio agora conta turnos desde o ultimo EVENTO NOVO (Write/Edit, leitura de arquivo inedito na run via mapa bornado, stop-condition parcial que ficou verde, arquivo novo fora do checkout), com override vagueio_trigger: no contrato; loop real continua morrendo.
Provas A-E em tests/test_vagueio_regua.py (579 passed, 2 skipped): A explorador 12 reads+Write PASS; B loop x9 FAIL vagueio; C override 4; D mapa bornado; E formato do FAIL/resumo intacto.

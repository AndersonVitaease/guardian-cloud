# GB-MIGRA-CONFIG-01 — PATCH ordens_guard.sh (aplicar no deploy /opt):
# block regexes (rota antiga):
#   ^.*despachar_missao\.py.*--executar
#   ^.*mission_run\.py
#   ^.*systemd-run.*--unit=harness-
# allow (rota nova):
#   ^.*despachar-mecanico\.sh.*MEC_PROVA=
#   ^.*despachante\.py.*plano\.json

# RELATORIO-RUN-STREAM-01C

Corrigidos 3 pontos de run_stream.sh: resolver de missionId escolhe run dir mais recente por mtime preferindo trail sem VEREDITO; linha VEREDITO sai limpa (usd=X.XXX, extrai 'usd' de dict de custo); custo acumulado soma o campo real de custo dos eventos da janela. Testes estendidos (tentativa-1 com veredito vs tentativa-2 sem; veredito sem "${"; custo != 0) passam.
# MISSÃO RD-MOTOR-VIDEO-01 — inventário do motor de vídeo do ambiente

Fonte: ordem do operator 12/10 ("temos um motor de vídeo aqui, encontre qual
é, vamos evoluir ele"). Objetivo: mapear o que existe de geração/edição de
vídeo no ambiente e propor a evolução. DIAGNÓSTICO + PROPOSTA (sem instalar
nada).

## Pistas iniciais (verificar cada uma)

- ffmpeg 9.0.1 nativo do Hermes em /root/.hermes/tools/ffmpeg-9.0.1-linux-x64/
  (bin/ffmpeg; ver codecs/librarias: -version, -filters | count, escala,
  libx264/libx265/vpx presentes?)
- Skills Hermes: manim-video (Manim CE — animações matemáticas 3Blue1Brown),
  ascii-video (vídeo→ASCII MP4/GIF) — ler os SKILL.md delas (caminhos em
  /root/.hermes/skills/)
- manim/moviepy: NÃO instalados no python 3.14 (ModuleNotFoundError já
  confirmado) — instalar é evolução, não inventário
- venv/conda do ambiente (existe? pip disponível?)

## Entregas (nesta ordem)

1. RELATORIO-RD-MOTOR-VIDEO-01.md na raiz do worktree (via Bash heredoc
   python — Write/Edit confinados ao run-dir) com:
   a. tabela: motor → onde está → versão → capacidades (codecs/filters) →
      o que produz (mp4/gif/webm?)
   b. lacunas: o que falta para "motor de vídeo de verdade" (ex.: manim
      instalado, template de cena, pipeline ffmpeg pronta)
   c. PROPOSTA de evolução em 3 degraus, cada um com comando/skill envolvida
      e prova de aceite: (1) ffmpeg pronto de fábrica (render pipeline
      documentada), (2) manim instalado + cena modelo rodando, (3) skill
      atualizada com workflow de ponta a ponta (texto → cena → mp4)
2. Marcador MOTOR-VIDEO-OK no relatório.
3. UM commit: `git add RELATORIO-RD-MOTOR-VIDEO-01.md` + subject exato
   `RD-MOTOR-VIDEO-01: inventario motor de video (fecho)`.

## Regras (GB-FORCA-ESCRITA-01)

Heredoc python p/ escrever; code_slice/file_peek p/ ler; ffmpeg é SÓ leitura
de versão/filters (não renderize nada nesta missão); sem git reset/checkout
de branch/stash/clean; sem instalar pacotes (proposta, não execução).

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'MOTOR-VIDEO-OK' RELATORIO-RD-MOTOR-VIDEO-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'ffmpeg' RELATORIO-RD-MOTOR-VIDEO-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && test "$(git log -1 --format=%s)" = "RD-MOTOR-VIDEO-01: inventario motor de video (fecho)"
```

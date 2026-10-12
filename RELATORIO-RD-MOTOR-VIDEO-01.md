# RELATORIO-RD-MOTOR-VIDEO-01 — Inventário do motor de vídeo

MOTOR-VIDEO-OK

## a. Inventário (motor → onde está → versão → capacidades → saída)

| Motor | Onde está | Versão | Capacidades | Produz |
|---|---|---|---|---|
| ffmpeg (sistema) | /usr/bin/ffmpeg + /usr/bin/ffprobe | 6.1.1-3ubuntu5 (Ubuntu, gcc 13.2) | 562 filtros; encoders libx264, libx265, libvpx (VP8/VP9), libaom, libsvtav1, libdav1d (decode AV1), libmp3lame, libopus; filtros drawtext/subtitles/libass, scale, overlay, concat, zoompan | mp4 (H.264/H.265), webm (VP9/AV1), gif, áudio mp3/opus |
| ffmpeg Hermes | /root/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg | 9.0.1 (pista do operator) | INACESSÍVEL nesta run: `Permission denied` em /root/.hermes/tools/ e /root/.hermes/skills/ (sandbox do worker não tem permissão de leitura em /root) | desconhecido — requer acesso root ou cópia do binário para caminho legível |
| Skills Hermes manim-video / ascii-video | /root/.hermes/skills/ (SKILL.md) | — | INACESSÍVEL: mesmo Permission denied; conteúdo não pôde ser lido nesta run | manim-video: animações matemáticas (Manim CE) → mp4; ascii-video: vídeo→ASCII → mp4/gif |
| manim (Python) | não instalado | — | `import manim` → ModuleNotFoundError | — |
| moviepy (Python) | não instalado | — | `import moviepy` → ModuleNotFoundError | — |
| Python/pip | /usr/bin/python3 3.12.3; pip 24.0 | 3.12.3 | pip disponível (sem venv/conda detectados no PATH) | base p/ instalar manim/moviepy |

## b. Lacunas para "motor de vídeo de verdade"

1. Acesso ao ffmpeg 9.0.1 do Hermes e às skills (manim-video, ascii-video): /root/.hermes está fora da sandbox do worker — sem leitura, não há como usar nem auditar.
2. manim e moviepy ausentes no Python 3.12 — não há geração programática de cena, só manipulação ffmpeg bruta.
3. Sem template de cena (cena modelo Manim) nem pipeline documentada texto→cena→render→mp4.
4. Sem skill de workflow ponta-a-ponta no ambiente acessível (as existentes estão trancadas em /root).

## c. Proposta de evolução em 3 degraus

**Degrau 1 — ffmpeg pronto de fábrica (render pipeline documentada)**
- Ação: documentar pipeline padrão usando o ffmpeg 6.1.1 do sistema (ex.: `ffmpeg -f image2 -framerate 30 -i frame_%04d.png -c:v libx264 -pix_fmt yuv420p out.mp4`; concat, overlay, drawtext).
- Comando/skill envolvida: Bash + ffmpeg (só leitura/uso normal em missões futuras).
- Prova de aceite: comando documentado no relatório/skill roda e gera mp4 válido verificado com `ffprobe`.

**Degru 2 — manim instalado + cena modelo rodando**
- Ação: `pip install manim` (ou venv dedicado) + cena modelo `Scene` com `Text`/`Write` e `manim -qm scene.py MinhaCena`.
- Comando/skill envolvida: pip + CLI manim; skill manim-video do Hermes como referência (requer destrancar /root/.hermes/skills).
- Prova de aceite: `manim -qm cena_modelo.py CenaModelo` produz `media/videos/.../1080p60/CenaModelo.mp4` sem erro.

**Degru 3 — skill atualizada com workflow ponta-a-ponta (texto → cena → mp4)**
- Ação: nova/atualizada skill Hermes com pipeline: briefing em texto → gera cena_modelo.py (Manim) → render manim → pós-ffmpeg (áudio/trim/encode final) → mp4 entregue.
- Comando/skill envolvida: skill Hermes (SKILL.md) + manim + ffmpeg.
- Prova de aceite: execução ponta-a-ponta a partir de um briefing de texto produz mp4 final validado por ffprobe, sem intervenção manual.

## Notas de execução
- Nada foi instalado nem renderizado nesta missão (regra GB-FORCA-ESCRITA-01): ffmpeg usado apenas para `-version`/`-filters`/`-encoders`.
- Recusas registradas verbatim: `ls: cannot access '/root/.hermes/tools/': Permission denied`; `/root/.hermes/skills/: Permission denied`; `/bin/sh: 1: /root/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg: Permission denied`.

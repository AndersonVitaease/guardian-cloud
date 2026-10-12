# RELATORIO-RD-MOTOR-VIDEO-01 — Inventário do motor de vídeo

MOTOR-VIDEO-OK

## 1. Tabela de motores encontrados

| Motor | Onde está | Versão | Capacidades | Produz |
|---|---|---|---|---|
| ffmpeg (sistema) | /usr/bin/ffmpeg + /usr/bin/ffprobe | 6.1.1-3ubuntu5 (Ubuntu, gcc 13) | 562 filtros; encoders: libx264, libx265, libvpx (VP8/VP9), libaom, libsvtav1, libdav1d, libmp3lame, libopus, libass, libfreetype, libvidstab, libzimg | mp4 (H.264/H.265), webm (VP9/AV1), gif, áudio (mp3/opus/vorbis) |
| ffmpeg Hermes 9.0.1 | /root/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin/ffmpeg | 9.0.1 (pistas do operator) | INACESSÍVEL nesta run: "Permission denied" em /root/.hermes/tools/ e /root/.hermes/skills/ (verbatim: `ls: cannot access '/root/.hermes/tools/': Permission denied`) | desconhecido (não executável pelo worker) |
| Skills Hermes manim-video / ascii-video | /root/.hermes/skills/ (SKILL.md) | n/a | INACESSÍVEL: `ls: cannot access '/root/.hermes/skills/': Permission denied` | n/a |
| manim (Python) | — | — | `ModuleNotFoundError: No module named 'manim'` | — |
| moviepy (Python) | — | — | `ModuleNotFoundError: No module named 'moviepy'` | — |
| Python/pip | /usr/bin/python3 (3.12.3), pip 24.0 | 3.12.3 | pip disponível (sem venv/conda detectado) | — |

## 2. Lacunas para "motor de vídeo de verdade"

- manim/moviepy não instalados no Python 3.12 → sem geração de cena programática.
- Skills Hermes (manim-video, ascii-video) ilegíveis pelo worker → sem workflow documentado utilizável.
- ffmpeg Hermes 9.0.1 sem permissão de execução → motor efetivo hoje é o ffmpeg 6.1.1 do sistema.
- Não existe template de cena nem pipeline ffmpeg documentada (comandos prontos de render).

## 3. Proposta de evolução em 3 degraus

1. **ffmpeg pronto de fábrica** — documentar pipeline de render no repo
   (ex.: `ffmpeg -f lavfi -i testsrc=size=1280x720:rate=30 -t 5 -c:v libx264 -pix_fmt yuv420p out.mp4`).
   *Prova de aceite:* comando roda e ffprobe valida mp4 H.264.
2. **manim instalado + cena modelo** — `pip install manim` (ou venv) + cena
   modelo `Scene.construct` com `manim -ql cena.py` gerando mp4.
   *Prova de aceite:* mp4 de saída validado por ffprobe.
3. **Skill atualizada ponta a ponta** — skill Hermes de vídeo com workflow
   texto → cena (manim) → render (ffmpeg) → mp4/gif/webm.
   *Prova de aceite:* SKILL.md versionado com exemplo executável fim a fim.

Observação: nada foi instalado nem renderizado nesta missão (diagnóstico apenas).

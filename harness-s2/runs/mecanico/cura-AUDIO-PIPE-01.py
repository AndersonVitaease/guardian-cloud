#!/usr/bin/env python3
# Cura AUDIO-PIPE-01 (mecanico): pipeline de audio documentada + prova real
# (espeak-ng pt-br -> wav -> ffmpeg mp3 -> ffprobe valida stream mp3).
import subprocess, os, json, sys
REPO = "/home/worker/harness-s2/harness-s2"
REL = os.path.join(REPO, "runs", "mecanico", "RELATORIO-AUDIO-PIPE-01.md")
DOC = os.path.join(REPO, "docs", "PIPELINE-AUDIO-ffmpeg.md")

def sh(c, t=180):
    p = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    return p.returncode, p.stdout + p.stderr

linhas = ["# RELATORIO-AUDIO-PIPE-01\n"]

# 1) documentacao da pipeline de audio
doc = """# PIPELINE-AUDIO-ffmpeg.md (motor de audio — degrau US$0)

## fala (TTS local, sem custo)
espeak-ng -v pt-br -s 140 "texto" -w saida.wav

## conversao
ffmpeg -i saida.wav -codec:a libmp3lame -qscale:a 4 saida.mp3     # mp3
ffmpeg -i saida.wav -c:a libopus -b:a 96k saida.opus              # opus (voz)

## validacao
ffprobe -v error -show_entries stream=codec_name -of csv=p=0 saida.mp3

## mix com video
ffmpeg -i video.mp4 -i voz.wav -shortest -c:v copy -c:a aac final.mp4
"""
os.makedirs(os.path.dirname(DOC), exist_ok=True)
open(DOC, "w").write(doc)
linhas.append("doc: %s" % DOC)

# 2) prova real: fala -> mp3 -> ffprobe
wav = "/tmp/audio-pipe-voz.wav"
rc, out = sh('espeak-ng -v pt-br -s 140 "Pipeline de audio do Guardian provada de ponta a ponta." -w %s' % wav)
if rc != 0:
    linhas.append("espeak rc=%d\n```\n%s\n```" % (rc, out[-400:]))
    open(REL, "w").write("\n".join(linhas))
    print(json.dumps({"ok": False, "erro": "espeak_falhou"}))
    sys.exit(1)

mp3 = "/tmp/audio-pipe-voz.mp3"
rc, out = sh("ffmpeg -y -i %s -codec:a libmp3lame -qscale:a 4 %s" % (wav, mp3))
if rc != 0:
    linhas.append("ffmpeg rc=%d\n```\n%s\n```" % (rc, out[-400:]))
    open(REL, "w").write("\n".join(linhas))
    print(json.dumps({"ok": False, "erro": "ffmpeg_falhou"}))
    sys.exit(1)

rc, out = sh("ffprobe -v error -show_entries stream=codec_name -of csv=p=0 %s" % mp3)
linhas.append("probe: %s" % out.strip())
ok = "mp3" in out
linhas.append("RESULTADO: %s" % ("OK mp3 validado" if ok else "FALHOU"))
open(REL, "w").write("\n".join(linhas) + "\n")
print(json.dumps({"ok": ok, "probe": out.strip(), "relatorio": REL}))
sys.exit(0 if ok else 1)
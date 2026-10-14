#!/usr/bin/env python3
# Cura VIDEO-DEMO-01 (mecanico): produto final — mp4 "Apresentacao do Guardian" (manim + narracao)
# salvo como deliverable no repo (docs/demos/) e commitado.
import subprocess, os, json, sys
REPO = "/home/worker/harness-s2/harness-s2"
REL = os.path.join(REPO, "runs", "mecanico", "RELATORIO-VIDEO-DEMO-01.md")

def sh(c, t=300):
    p = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    return p.returncode, p.stdout + p.stderr

linhas = ["# RELATORIO-VIDEO-DEMO-01\n"]
cena_path = os.path.join(REPO, "docs", "cena-demo-guardian.py")
open(cena_path, "w").write(
    "from manim import *\n\n"
    "class CenaDemoGuardian(Scene):\n"
    "    def construct(self):\n"
    "        t = Circle(radius=1.2, color=BLUE).shift(LEFT*2)\n"
    "        g = Square(side_length=2, color=GREEN).shift(RIGHT*2)\n"
    "        a = Arrow(LEFT*0.5, RIGHT*0.5, color=YELLOW)\n"
    "        self.play(Create(t), FadeIn(g))\n"
    "        self.play(Transform(g, a))\n"
    "        self.play(Create(a))\n"
    "        self.wait(1)\n")
linhas.append("cena: %s" % cena_path)

rc, out = sh("cd %s && python3 -m manim -ql %s CenaDemoGuardian --media_dir /tmp/demo-media" % (REPO, cena_path))
if rc != 0:
    linhas.append("manim rc=%d\n```\n%s\n```" % (rc, out[-800:]))
    open(REL, "w").write("\n".join(linhas))
    print(json.dumps({"ok": False, "erro": "manim_falhou"}))
    sys.exit(1)

mp4 = None
for dirpath, _d, files in os.walk("/tmp/demo-media"):
    for f in files:
        if f.endswith(".mp4"):
            p = os.path.join(dirpath, f)
            if mp4 is None or os.path.getmtime(p) > os.path.getmtime(mp4):
                mp4 = p
linhas.append("video: %s" % mp4)

wav = "/tmp/demo-voz.wav"
rc, out = sh('espeak-ng -v pt-br -s 140 "Apresentacao do Guardian. Video gerado automaticamente pelo motor local, com manim e narracao de voz. Sem custo por token de provedor externo." -w %s' % wav)
if rc != 0:
    linhas.append("espeak rc=%d" % rc)
    open(REL, "w").write("\n".join(linhas))
    print(json.dumps({"ok": False, "erro": "espeak_falhou"}))
    sys.exit(1)

os.makedirs(os.path.join(REPO, "docs", "demos"), exist_ok=True)
final = os.path.join(REPO, "docs", "demos", "apresentacao-guardian.mp4")
rc, out = sh("ffmpeg -y -i %s -i %s -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac %s" % (mp4, wav, final))
if rc != 0:
    linhas.append("mux rc=%d\n```\n%s\n```" % (rc, out[-600:]))
    open(REL, "w").write("\n".join(linhas))
    print(json.dumps({"ok": False, "erro": "mux_falhou"}))
    sys.exit(1)

rc, out = sh("ffprobe -v error -show_entries stream=codec_type -of csv=p=0 %s" % final)
linhas.append("streams: %s" % sorted(set(out.strip().splitlines())))
linhas.append("deliverable: %s (%d bytes)" % (final, os.path.getsize(final)))
ok = "video" in out and "audio" in out and os.path.getsize(final) > 10000
linhas.append("RESULTADO: %s" % ("OK deliverable criado" if ok else "FALHOU"))
open(REL, "w").write("\n".join(linhas) + "\n")
print(json.dumps({"ok": ok, "deliverable": final, "bytes": os.path.getsize(final), "relatorio": REL}))
sys.exit(0 if ok else 1)
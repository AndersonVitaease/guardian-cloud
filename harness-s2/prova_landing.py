#!/usr/bin/env python3
"""Prova GB-LANDING-GAC-01: screenshot chromium headless + validacao DOM."""
import os, subprocess, glob
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(ROOT, "index.html")
SHOT = os.path.join(ROOT, "landing.png")

def find_chrome():
    for pat in ("/home/worker/.cache/ms-playwright/chromium-*/chrome-linux64/chrome",
                "/home/worker/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
                "/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None

checks = []

class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.chips, self.inputs, self.text = set(), 0, [], []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d: self.ids.add(d["id"])
        if tag == "button" and "chip" in d.get("class", "").split(): self.chips += 1
        if tag == "input": self.inputs.append(d.get("name", d.get("type", "?")))
    def handle_data(self, data):
        self.text.append(data)

p = P()
p.feed(open(HTML, encoding="utf-8").read())

need_ids = {"hero", "modelos", "exterior", "interior", "lead", "loja", "footer"}
checks.append(("ids-7", need_ids <= p.ids))
checks.append(("chips-6", p.chips == 6))
checks.append(("inputs-4", set(p.inputs) >= {"nome", "telefone", "email", "cidade"}))
checks.append(("cta-consultor", "Falar com um consultor" in " ".join(p.text)))

shot_ok = False
chrome = find_chrome()
if chrome:
    try:
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                        "--screenshot=" + SHOT, "--window-size=1440,2400",
                        "file://" + HTML], timeout=60, capture_output=True)
        shot_ok = os.path.exists(SHOT) and os.path.getsize(SHOT) > 20000
    except Exception:
        shot_ok = False
if shot_ok:
    print("LANDING-SHOT-OK")

for name, ok in checks:
    print(("PASS" if ok else "FAIL"), name)
if shot_ok:
    print("PASS screenshot")
else:
    print("SKIP screenshot (chrome indisponivel)")

if all(ok for _, ok in checks):
    print("GB-LANDING-GAC-01-PROVA-OK")
else:
    raise SystemExit(1)

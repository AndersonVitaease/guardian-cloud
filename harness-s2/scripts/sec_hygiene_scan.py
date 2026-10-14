#!/usr/bin/env python3
"""SEC-HYGIENE-ROOT-01 — scanner determinístico, read-only.

Confirma e tipifica 5 itens de dívida de segurança:
  A) Caddyfile com Authorization/API key literal
  B) argv de processos com token Notion (secret_/ntn_/oat_)
  C) arquivos em /opt/eng-mcp-secrets com nome contendo PAT/token
  D) /data/tokens.json parse/malformados + consumo por units systemd
  E) portas em LISTEN vs inventário esperado (22,80,443,8140)

Uso: python3 scripts/sec_hygiene_scan.py [--json]
"""
import argparse
import glob
import json
import os
import re
import sys

CADDYFILE = "/etc/caddy/Caddyfile"
SECRETS_DIR = "/opt/eng-mcp-secrets"
TOKENS_JSON = "/data/tokens.json"
SYSTEMD_DIR = "/etc/systemd/system"
EXPECTED_PORTS = {22, 80, 443, 8140}

TOKEN_RE = re.compile(r"(secret_[A-Za-z0-9_-]{8,}|ntn_[A-Za-z0-9_-]{8,}|oat_[A-Za-z0-9_-]{8,})")
KEY_LINE_RE = re.compile(r"(Authorization|api[_ -]?key|X-Api-Key)", re.IGNORECASE)
PAT_NAME_RE = re.compile(r"(ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|token)", re.IGNORECASE)


def mask(tok):
    return tok[:8] + "..." + tok[-4:] if len(tok) > 14 else tok[:4] + "..."


def scan_caddyfile(path=CADDYFILE):
    findings = []
    try:
        with open(path, "r", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if KEY_LINE_RE.search(line):
                    m = TOKEN_RE.search(line)
                    findings.append({
                        "file": path, "line": i,
                        "kind": "caddy-key-literal",
                        "preview": line.strip()[:120],
                        "token_masked": mask(m.group(1)) if m else None,
                    })
    except OSError as e:
        findings.append({"file": path, "kind": "caddy-unreadable", "error": str(e)})
    return findings


def scan_proc_argv(proc_dir="/proc"):
    findings = []
    for pid_path in glob.glob(os.path.join(proc_dir, "[0-9]*")):
        try:
            with open(os.path.join(pid_path, "cmdline"), "rb") as f:
                argv = f.read().split(b"\x00")
        except OSError:
            continue
        argv_s = [a.decode("utf-8", "replace") for a in argv if a]
        joined = " ".join(argv_s)
        if "notion" not in joined.lower():
            continue
        m = TOKEN_RE.search(joined)
        if m:
            findings.append({
                "pid": os.path.basename(pid_path),
                "kind": "proc-argv-notion-token",
                "token_masked": mask(m.group(1)),
                "argv_preview": joined[:160],
            })
    return findings


def scan_secrets_names(path=SECRETS_DIR):
    findings = []
    try:
        names = sorted(os.listdir(path))
    except OSError as e:
        return [{"path": path, "kind": "secrets-dir-unreadable", "error": str(e)}]
    for name in names:
        m = PAT_NAME_RE.search(name)
        if m:
            findings.append({
                "path": os.path.join(path, name),
                "kind": "secret-in-filename",
                "match": m.group(1),
            })
    return findings


def scan_tokens_json(path=TOKENS_JSON, systemd_dir=SYSTEMD_DIR):
    out = {"path": path, "kind": "tokens-json"}
    try:
        with open(path, "r", errors="replace") as f:
            data = json.load(f)
        out["parse_ok"] = True
        if isinstance(data, dict):
            out["malformed_entries"] = [k for k, v in data.items()
                                        if not isinstance(v, (str, dict, int, float, bool, type(None)))]
        else:
            out["malformed_entries"] = ["<top-level nao e objeto>"]
    except OSError as e:
        out["parse_ok"] = False
        out["error"] = "unreadable: %s" % e
    except json.JSONDecodeError as e:
        out["parse_ok"] = False
        out["error"] = str(e)
    consumers = []
    try:
        for unit in sorted(os.listdir(systemd_dir)):
            if not unit.endswith((".service", ".timer", ".socket")):
                continue
            try:
                with open(os.path.join(systemd_dir, unit), "r", errors="replace") as f:
                    if "tokens.json" in f.read():
                        consumers.append(unit)
            except OSError:
                continue
    except OSError as e:
        out["systemd_unreadable"] = str(e)
    out["consumers"] = consumers
    return [out]


def scan_ports(expected=None, tcp_files=("/proc/net/tcp", "/proc/net/tcp6")):
    expected = set(expected) if expected else EXPECTED_PORTS
    listening = set()
    for tf in tcp_files:
        try:
            with open(tf, "r") as f:
                next(f)
                for line in f:
                    cols = line.split()
                    if len(cols) < 4 or cols[3] != "0A":
                        continue
                    listening.add(int(cols[1].split(":")[1], 16))
        except (OSError, StopIteration, ValueError):
            continue
    return [{"kind": "ports", "listening": sorted(listening),
             "unexpected": sorted(listening - expected),
             "missing": sorted(expected - listening)}]


def run_all():
    findings = []
    findings += scan_caddyfile()
    findings += scan_proc_argv()
    findings += scan_secrets_names()
    findings += scan_tokens_json()
    findings += scan_ports()
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    findings = run_all()
    if args.json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
        return 0
    print("=== SEC-HYGIENE-ROOT-01 scan (read-only) ===")
    for f in findings:
        kind = f.get("kind", "?")
        if kind == "ports":
            print("[PORTS] listening=%s unexpected=%s missing=%s" % (f["listening"], f["unexpected"], f["missing"]))
        elif kind == "tokens-json":
            print("[TOKENS] parse_ok=%s malformed=%s consumers=%s err=%s" % (
                f["parse_ok"], f.get("malformed_entries"), f.get("consumers"), f.get("error", "-")))
        else:
            print("[%s] %s line=%s token=%s match=%s preview=%s" % (
                kind.upper(), f.get("file") or f.get("path") or f.get("pid"),
                f.get("line", "-"), f.get("token_masked", "-"), f.get("match", "-"),
                str(f.get("preview", f.get("argv_preview", "-")))[:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
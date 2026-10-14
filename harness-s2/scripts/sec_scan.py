#!/usr/bin/env python3
"""SEC-SCAN-01: scanner deterministico de segredos e vulnerabilidades.

Roda como worker, exit 0 sempre, imprime JSON por linha.
Uso: python3 scripts/sec_scan.py [raiz]
"""
import json
import os
import re
import stat
import subprocess
import sys

# ---------------- segredos ----------------
SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("router_key", re.compile(r"\bOR_[0-9a-f]{40}\b")),
    ("gsk_key", re.compile(r"\bgsk_[A-Za-z0-9_\-]{20,}\b")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=+/]{16,}")),
    ("password_assign", re.compile(
        r"(?i)\b(passwd|senha|password|pwd)\s*=\s*['\"][^'\"]{4,}['\"]")),
    ("slack_webhook", re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]+")),
    ("discord_webhook", re.compile(
        r"discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+")),
    ("jwt_literal", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.")),
]

STRONG_PATTERNS = tuple(
    rx for t, rx in SECRET_PATTERNS
    if t in ("private_key", "aws_key", "google_api_key", "openai_key",
             "router_key", "gsk_key", "jwt_literal", "slack_webhook",
             "discord_webhook"))

FAKE_RX = re.compile(r"(?i)(fake|fixture|exemplo)")

FAKE_RX = re.compile(r"(?i)(fake|fixture|exemplo|dummy|placeholder)")

# falsos positivos: placeholders obvios
FP_RE = re.compile(
    r"(?i)(fake|fixture|exemplo|placeholder|<token>|your_|seu[_-]?token|"
    r"changeme|dummy|test[_-]?key|example)")

# ---------------- vulnerabilidades ----------------
VULN_PY = [
    ("eval_exec", re.compile(r"\b(eval|exec)\s*\(")),
    ("shell_true", re.compile(r"shell\s*=\s*True")),
    ("pickle_load", re.compile(r"\bpickle\s*\.\s*loads?\s*\(")),
    ("os_system", re.compile(r"\bos\s*\.\s*system\s*\(")),
    ("sudo_use", re.compile(r"(?i)\bsudo\s+")),
]
VULN_SH_UNQUOTED = re.compile(
    r"\b(?:rm|mv|cp|kill)\b[^\n]*\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def is_false_positive(path, line):
    if path.startswith("tests/") or "/tests/" in path:
        return True
    if FP_RE.search(line):
        return True
    return False


def mask(preview):
    return (preview[:4] + "...") if preview else ""


def scan_file(path, rel):
    hits = []
    try:
        with open(path, "r", errors="replace") as f:
            for i, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                in_tests = rel.startswith("tests/")
                if in_tests and (FAKE_RX.search(rel) or FAKE_RX.search(stripped)):
                    continue
                strong = any(rx.search(stripped) for rx in STRONG_PATTERNS)
                if not strong and is_false_positive(rel, stripped):
                    continue
                for tipo, rx in SECRET_PATTERNS:
                    m = rx.search(stripped)
                    if m:
                        hits.append({
                            "arquivo": rel, "linha": i, "tipo": tipo,
                            "preview": mask(m.group(0)), "classe": "segredo",
                        })
                if rel.endswith(".py"):
                    for tipo, rx in VULN_PY:
                        if rx.search(stripped):
                            hits.append({
                                "arquivo": rel, "linha": i, "tipo": tipo,
                                "preview": mask(stripped), "classe": "vuln",
                            })
                elif rel.endswith(".sh"):
                    if VULN_SH_UNQUOTED.search(stripped):
                        hits.append({
                            "arquivo": rel, "linha": i, "tipo": "sh_unquoted_var",
                            "preview": mask(stripped), "classe": "vuln",
                        })
    except OSError:
        pass
    try:
        st = os.stat(path)
        if st.st_mode & stat.S_IWOTH:
            hits.append({
                "arquivo": rel, "linha": 0, "tipo": "world_writable",
                "preview": mask(oct(st.st_mode & 0o777)), "classe": "vuln",
            })
    except OSError:
        pass
    return hits


def repo_files(root):
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True)
    files = [l for l in out.stdout.splitlines() if l.strip()]
    if files:
        return files
    for dirpath, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.relpath(os.path.join(dirpath, n), root)
            if ".git" not in p:
                files.append(p)
    return files


def scan(root):
    hits = []
    for rel in repo_files(root):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        hits.extend(scan_file(path, rel))
    return hits


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    for h in scan(root):
        print(json.dumps(h, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
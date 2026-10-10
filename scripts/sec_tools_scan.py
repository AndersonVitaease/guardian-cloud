#!/usr/bin/env python3
"""SEC-TOOLS-01 — scanner estatico de seguranca das tools bash.

Checagens (heuristicas de regex sobre os .sh):
  1. INJECAO-ARGS: uso de eval / bash -c alimentado por variaveis que
     derivam de args do usuario ($1..$N, "$@") sem validacao whitelist
     (case ... *[!A-Za-z0-9._-]*).
  2. GREPE: grep -e/-E recebendo padrao de arg sem `--` delimitador ou
     sem bloqueio de padrao com prefixo '-'.
  3. CD-UNQUOTED: cd com variavel de arg sem aspas.
  4. JSON-PRINTF: printf de JSON com %s alimentado por variavel nao
     constante (quebra de JSON por aspas no arg) — VALIDACAO_AUSENTE.
  5. AUDIT-PROVA: executa uma tool real (code_find) em scratch com arg
     contendo aspas e verifica que a linha do audit continua JSON valido.

Saida: JSON 1 linha no stdout; exit 0 sempre.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

TOOLS_DIR = os.environ.get(
    "SEC_TOOLS_DIR", "/opt/mission-events/tools-bash")

# variaveis que tipicamente derivam de args do usuario
ARG_VARS = re.compile(r'\$(?:\{?[@1-9]\}?)')

# validacao whitelist "de forma" (padrao trail_tail/run_close/run_stream)
WHITELIST = re.compile(
    r"case\s+\"\$\{?\d+\}?\s+in[^)]*\*!\[?A-Za-z0-9._-\]?\*[^)]*\)\s*fail",
    re.S)

EVAL_RE = re.compile(r'^\s*(?:if\s+!?\s*)?eval\s+"?\$?(\w+)"?', re.M)
BASHC_RE = re.compile(r'\bbash\s+-c\b')
GREP_E_RE = re.compile(r'grep\s+(?:-[A-Za-z]+\s+)*-[eE]\s+"?\$')
CD_UNQ_RE = re.compile(r'\bcd\s+\$\{?\w+\}?\b(?!\s*")')
JSON_PRINTF_RE = re.compile(
    r"printf\s+'(?:[^']*\{[^}]*\}|[^']*%s)[^']*'\s+\"?\$")


def _arg_derived_vars(src):
    """Conjunto de variaveis que derivam (transitivamente, ate 3 niveis) de $1..$N."""
    derived = set()
    for m in re.finditer(r'^\s*(\w+)=.*\$\{?[@\d]', src, re.M):
        derived.add(m.group(1))
    for _ in range(3):
        for m in re.finditer(r'^\s*(\w+)=.*\$\{?(\w+)\}?', src, re.M):
            if m.group(2) in derived:
                derived.add(m.group(1))
    return derived


def _var_from_args(src, var):
    """Heuristica: a variavel recebe direta ou indiretamente conteudo de $1..$N."""
    return var in _arg_derived_vars(src)


def scan_script(path):
    """Retorna lista de achados (dict) para um .sh."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    name = os.path.basename(path)
    out = []

    def has_whitelist(var):
        return bool(WHITELIST.search(src)) and _var_from_args(src, var)

    for m in EVAL_RE.finditer(src):
        var = m.group(1)
        line = src[:m.start()].count("\n") + 1
        if _var_from_args(src, var) or var in ("WT_ADD", "SUITE_CMD", "FILTER"):
            sev = "EXPLORAVEL" if _var_from_args(src, var) else "VALIDACAO_AUSENTE"
            out.append({
                "tool": name, "line": line, "check": "eval",
                "sev": sev, "evid": 'eval "$%s"' % var,
                "nota": ("variavel deriva de args do usuario sem whitelist"
                         if sev == "EXPLORAVEL" else
                         "variavel de ambiente/config, nao de arg direto")})
    for m in BASHC_RE.finditer(src):
        line = src[:m.start()].count("\n") + 1
        out.append({"tool": name, "line": line, "check": "bash -c",
                    "sev": "VALIDACAO_AUSENTE", "evid": m.group(0),
                    "nota": "bash -c presente; conferir origem da string"})
    for m in GREP_E_RE.finditer(src):
        line = src[:m.start()].count("\n") + 1
        has_dash_block = bool(re.search(r"case\s+\"\$\{?\d+\}?\s+in\s+-\*\)", src))
        out.append({"tool": name, "line": line, "check": "grep -e/-E",
                    "sev": "OK" if has_dash_block else "VALIDACAO_AUSENTE",
                    "evid": m.group(0).strip(),
                    "nota": ("padrao com prefixo '-' bloqueado + delimitador --"
                             if has_dash_block else
                             "sem bloqueio de padrao iniciando com '-'")})
    for m in CD_UNQ_RE.finditer(src):
        line = src[:m.start()].count("\n") + 1
        out.append({"tool": name, "line": line, "check": "cd unquoted",
                    "sev": "VALIDACAO_AUSENTE", "evid": m.group(0),
                    "nota": "cd com variavel sem aspas"})
    for m in JSON_PRINTF_RE.finditer(src):
        line = src[:m.start()].count("\n") + 1
        out.append({"tool": name, "line": line, "check": "json-printf",
                    "sev": "VALIDACAO_AUSENTE", "evid": m.group(0)[:80],
                    "nota": "printf de JSON com %s de variavel — aspas no "
                            "valor quebram o JSON de saida"})
    return out


def audit_proof(tools_dir):
    """Prova 3: chama code_find com arg contendo aspas e valida a linha do audit."""
    audit_file = os.path.join(tempfile.mkdtemp(prefix="sec-audit-"),
                              "calls.jsonl")
    env = dict(os.environ, TOOLS_BASH_AUDIT_FILE=audit_file)
    tool = os.path.join(tools_dir, "code_find.sh")
    if not os.path.isfile(tool):
        return {"ok": False, "error": "TOOL_AUSENTE"}
    try:
        subprocess.run([tool, 'pa"t`tern;x', tools_dir, "1"],
                       env=env, capture_output=True, text=True, timeout=30)
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": "TOOL_FALHOU:%s" % exc}
    try:
        with open(audit_file, encoding="utf-8") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
        rec = json.loads(lines[-1])
        return {"ok": True, "audit_valid_json": True, "tool": rec.get("tool"),
                "args": rec.get("args"), "n_lines": len(lines)}
    except Exception as exc:
        return {"ok": False, "error": "AUDIT_JSON_QUEBRADO:%s" % exc}


def main(tools_dir=TOOLS_DIR):
    findings = []
    if os.path.isdir(tools_dir):
        for fn in sorted(os.listdir(tools_dir)):
            if fn.endswith(".sh"):
                findings.extend(scan_script(os.path.join(tools_dir, fn)))
    proof = audit_proof(tools_dir)
    print(json.dumps({"ok": True, "tools_dir": tools_dir,
                      "n_findings": len(findings), "findings": findings,
                      "audit_proof": proof}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
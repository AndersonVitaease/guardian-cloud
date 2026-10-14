# APRENDE-WIRE-01 (HARNESS-MEMORIA-01): captura de aprendizado como primitiva.
# extrair(run_dir) → dict estruturado do RELATORIO (sem texto cru de trail);
# registro(run_dir) → append atômico (fcntl) de 1 linha JSONL em aprendizado.jsonl.
# CLI: python3 scripts/aprende.py <run_dir> → imprime JSON, exit 0 (nunca derruba nada).
import fcntl
import json
import os
import sys
from datetime import datetime, timezone


def _primeira_frase(texto):
    texto = texto.strip()
    if not texto:
        return ""
    for sep in (". ", "!\n", "?\n", "\n"):
        idx = texto.find(sep)
        if idx > 0:
            return texto[:idx + (1 if sep == ". " else 0)].strip()
    return texto.splitlines()[0].strip()


def _secao(md, titulos):
    """Retorna o corpo da 1ª seção cujo título (## ...) case (insensível)."""
    linhas = md.splitlines()
    alvo = [t.lower() for t in titulos]
    atual = None
    corpo = []
    for ln in linhas:
        if ln.startswith("##"):
            if atual is not None:
                return "\n".join(corpo).strip()
            titulo = ln.lstrip("#").strip().lower()
            if any(titulo == t or titulo.startswith(t) for t in alvo):
                atual = titulo
                continue
        elif atual is not None:
            corpo.append(ln)
    return "\n".join(corpo).strip() if atual is not None else ""


def _itens_secao(md, titulos):
    """1ª frase de cada item (- / * / linha) da seção."""
    corpo = _secao(md, titulos)
    if not corpo:
        return []
    itens = []
    for ln in corpo.splitlines():
        ln = ln.strip()
        if ln.startswith(("- ", "* ")) and len(ln) > 2:
            itens.append(_primeira_frase(ln[2:]))
        elif ln and not ln.startswith(("#", "```")):
            itens.append(_primeira_frase(ln))
    return [i for i in itens if i]


def extrair(run_dir):
    """Extrai aprendizado estruturado do RELATORIO-*.md do run_dir (sem trail cru)."""
    rel = None
    if os.path.isdir(run_dir):
        for fn in sorted(os.listdir(run_dir)):
            if fn.startswith("RELATORIO") and fn.endswith(".md"):
                rel = os.path.join(run_dir, fn)
                break
    if rel is None:
        missao = os.path.basename(os.path.normpath(run_dir))
        return {"missao": missao, "erro": "sem_relatorio"}
    with open(rel, encoding="utf-8") as f:
        md = f.read()
    veredito = ""
    for ln in md.splitlines():
        low = ln.lower()
        if ("veredito" in low and "pass" in low) or low.strip().startswith("veredito: pass"):
            veredito = "PASS"
            break
        if ("veredito" in low and "fail" in low) or low.strip().startswith("veredito: fail"):
            veredito = "FAIL"
            break
    mission_id = os.path.basename(rel).replace("RELATORIO-", "").replace(".md", "")
    turnos = custo = None
    motivo = _primeira_frase(_secao(md, ["motivo", "o que foi feito"]))
    summary = os.path.join(run_dir, "run-summary.json")
    if os.path.isfile(summary):
        try:
            with open(summary, encoding="utf-8") as f:
                s = json.load(f)
            veredito = s.get("veredito", veredito)
            motivo = s.get("motivo", motivo)
            turnos = s.get("turnos", s.get("turns"))
            custo = s.get("custo_usd", s.get("cum_usd"))
        except Exception:
            pass
    return {
        "missao": mission_id,
        "mission_id": mission_id,
        "veredito": veredito,
        "motivo": motivo,
        "turnos": turnos,
        "custo_usd": custo,
        "entregas": _itens_secao(md, ["entrega", "goal", "o que foi feito"]),
        "causas_medidas": _itens_secao(md, ["causa"]),
        "dividas": _itens_secao(md, ["dívidas", "dividas", "dívida", "divida"]),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "relatorio": os.path.basename(rel),
    }


def registro(run_dir, dados=None):
    """Append atômico (fcntl lock) de 1 linha JSONL em <run_dir>/aprendizado.jsonl."""
    if dados is None:
        dados = extrair(run_dir)
    path = os.path.join(run_dir, "aprendizado.jsonl")
    linha = json.dumps(dados, ensure_ascii=False)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, (linha + "\n").encode("utf-8"))
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python3 scripts/aprende.py <run_dir>", file=sys.stderr)
        return 2
    try:
        dados = extrair(argv[0])
        print(json.dumps(dados, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001 — aprende nunca derruba nada
        print(json.dumps({"missao": os.path.basename(os.path.normpath(argv[0])),
                          "erro": f"falha: {e}"}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
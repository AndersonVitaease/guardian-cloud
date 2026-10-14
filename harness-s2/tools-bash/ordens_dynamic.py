# GB-JAULA-01 — ordens dinâmicas do Guardian: fetch com cache 60s + parse dos blocos ## ORD-*
import json, os, re, time, urllib.request

CACHE_TTL = 60

def parse_ordens_md(md):
    """Parse dos blocos '## ORD-*' com linha 'guard: block <regex>'."""
    rules = []
    cur = None
    for line in md.splitlines():
        m = re.match(r"^## (ORD-[\w-]+)", line.strip())
        if m:
            cur = m.group(1)
            continue
        m2 = re.match(r"^guard:\s*block\s+(.+)$", line.strip())
        if m2 and cur:
            rx = m2.group(1).strip().strip("`")
            rules.append({"id": cur, "regex": rx})
    return rules

def fetch_ordens(url, token, cache_file):
    """Fetch de /api/ordens; falha → usa cache (se fresco ou não); sem cache → []."""
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=3) as r:
            body = r.read().decode()
        # BUG A (GB-CANAL-UNICO-01): /api/ordens devolve envelope JSON
        # {"ok":true,"md":"..."} — extrair d["md"] quando o corpo começa com '{'
        # (tolera também corpo markdown cru, retrocompatível).
        if body.lstrip().startswith("{"):
            try:
                body = json.loads(body).get("md") or ""
            except Exception:
                pass
        rules = parse_ordens_md(body)
        tmp = cache_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": time.time(), "rules": rules}, f)
        os.replace(tmp, cache_file)
        return rules
    except Exception:
        try:
            with open(cache_file) as f:
                d = json.load(f)
            return d.get("rules", [])
        except Exception:
            return []

def main():
    """CLI: python3 ordens_dynamic.py '<cmd>' → imprime id da ordem se o cmd casar algum regex dinâmico."""
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    url = os.environ.get("ORDENS_URL", "")
    token_file = os.environ.get("ORDENS_TOKEN_FILE", "")
    cache_file = os.environ.get("ORDENS_CACHE_FILE", "")
    token = ""
    try:
        token = open(token_file).read().strip()
    except Exception:
        pass
    rules = fetch_ordens(url, token, cache_file) if url else []
    if not rules:
        # sem URL: tenta só o cache (fail-open na parte dinâmica)
        try:
            with open(cache_file) as f:
                rules = json.load(f).get("rules", [])
        except Exception:
            rules = []
    for r in rules:
        try:
            if re.search(r["regex"], cmd):
                print(r["id"]); break
        except re.error:
            continue

if __name__ == "__main__":
    main()
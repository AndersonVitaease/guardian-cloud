# MISSÃO RD-ESCADAWRITE-01 — 2 correções cravadas no harness (escrita no worktree + modelo por contrato)

Fonte: FINDs 12/10 — (1) Write/Edit confinados ao run-dir derrubaram ~10
ciclos (STRIPE-02/02C/02D, ESCRIT-TASKS ×3, POW-BROWSER ×3); (2) worker flash
falha ciclos inteiros — missões complexas devem nascer já no modelo forte
(HARNESS_ESCADA_MODEL) quando o contrato declarar.

## MAPA (arquivo:linha, verificado)

- harness.py:1113-1118 — `def _resolve(cwd, path)`: confina ao realpath(cwd)
  (raise PermissionError fora) — chamadores em 1194 (Write), 1200 (Read),
  1203 (Edit)
- harness.py:38 — `MODEL = os.environ.get("HARNESS_MODEL", "z-ai/glm-5.3-flash")`
- harness.py:66 — `ESCADA_MODEL = ... "z-ai/glm-5.3"`
- scripts/despachar_missao.py:141-165 — montagem do `cmd` systemd-run
  (--setenv por `a.setenv`), antes de mission_run.py

## Mudança 1 — harness.py _resolve: raiz extra de escrita via env

Substitua a função inteira por:

def _resolve(cwd, path):
    """Caminho de Read/Write/Edit confinado: cwd da run OU HARNESS_WRITE_ROOT
    (ex.: o worktree da missão, definido pelo despacho). Isolamento mantido:
    nada fora dessas raízes."""
    root = os.path.realpath(cwd)
    p = os.path.realpath(os.path.join(root, path))
    if p == root or p.startswith(root + os.sep):
        return p
    wr = os.environ.get("HARNESS_WRITE_ROOT", "")
    if wr:
        wroot = os.path.realpath(wr)
        if p == wroot or p.startswith(wroot + os.sep):
            return p
    raise PermissionError(f"caminho fora das raízes de escrita da run: {path}")

## Mudança 2 — scripts/despachar_missao.py: contrato declara modelo forte

No bloco de montagem do cmd (L141-160), logo depois de `for kv in a.setenv:`,
adicione:

    # RD-ESCADAWRITE-01: contrato pode declarar `## Modelo: <id>` para nascer
    # já no modelo forte (escada tarde demais perde ciclos)
    try:
        _mtxt = open(a.contrato, encoding="utf-8").read()
        _mre = re.search(r"^##\s*Modelo:\s*(\S+)", _mtxt, re.M)
        if _mre:
            cmd.append("--setenv=HARNESS_MODEL=" + _mre.group(1))
    except OSError:
        pass

E garanta `import re` no topo do arquivo (se já houver, não duplique).

## Execução (nesta ordem)

1. Leia os trechos com code_slice (absoluto, leitura ok) ANTES de editar;
   edite via Bash heredoc python (Write/Edit confinados ao run-dir):
   cd /home/worker/wt-RD-WORKER-GUARD && python3 - <<'EOF'
   p='harness.py'; s=open(p).read()
   old='''def _resolve(cwd, path):
    """Caminho de Read/Write/Edit confinado ao cwd da run (isolamento)."""
    root = os.path.realpath(cwd)
    p = os.path.realpath(os.path.join(root, path))
    if p != root and not p.startswith(root + os.sep):
        raise PermissionError(f"caminho fora do cwd da run: {path}")
    return p'''
   new='''def _resolve(cwd, path):
    """Caminho de Read/Write/Edit confinado: cwd da run OU HARNESS_WRITE_ROOT
    (ex.: o worktree da missão, definido pelo despacho). Isolamento mantido:
    nada fora dessas raízes."""
    root = os.path.realpath(cwd)
    p = os.path.realpath(os.path.join(root, path))
    if p == root or p.startswith(root + os.sep):
        return p
    wr = os.environ.get("HARNESS_WRITE_ROOT", "")
    if wr:
        wroot = os.path.realpath(wr)
        if p == wroot or p.startswith(wroot + os.sep):
            return p
    raise PermissionError(f"caminho fora das raízes de escrita da run: {path}")'''
   assert s.count(old)==1; open(p,'w').write(s.replace(old,new,1))
   EOF
2. Teste: cd /home/worker/wt-RD-WORKER-GUARD && python3 -c "import harness; import os; os.environ['HARNESS_WRITE_ROOT']='/tmp/wrt'; os.makedirs('/tmp/wrt',exist_ok=True); open('/tmp/wrt/t.txt','w').write('x'); print(harness._resolve('/tmp/wrt','t.txt'))" → precisa imprimir /tmp/wrt/t.txt sem exceção; E python3 -m pytest tests/test_worker_guard.py -q → verde (relate contagem).
3. RELATORIO-RD-ESCADAWRITE-01.md na raiz (heredoc) com marcador ESCADAWRITE-OK.
4. UM commit: `git add harness.py scripts/despachar_missao.py RELATORIO-RD-ESCADAWRITE-01.md` + subject exato `RD-ESCADAWRITE-01: write-root por env + modelo por contrato (fecho)`.

## Regras (GB-FORCA-ESCRITA-01)

Heredoc python p/ editar; code_slice/code_find p/ ler; sem git reset/checkout
de branch/stash/clean; sem tocar em routing/bridge; SOMENTE as 2 mudanças
acima (não refatore, não renomeie).

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'HARNESS_WRITE_ROOT' harness.py
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'Modelo:' scripts/despachar_missao.py
cmd cd /home/worker/wt-RD-WORKER-GUARD && test "$(git log -1 --format=%s)" = "RD-ESCADAWRITE-01: write-root por env + modelo por contrato (fecho)"
```

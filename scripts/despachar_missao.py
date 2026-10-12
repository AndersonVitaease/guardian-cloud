#!/usr/bin/env python3
"""despachar_missao.py — despacho DETERMINÍSTICO de missão do harness (sem LLM, ~10-25 s).

Uso: python3 despachar_missao.py <contrato.md> <worktree> [--seed N] [--budget F] [--turns N]
                                 [--retry N] [--setenv K=V ...] [--dry-run] [--sem-baseline]
Saída: 1 linha JSON {ok, id, unit, seed, tab, run_dir, stops, baseline, avisos, ms}.

Faz o que o despachante-agente fazia em 3-14 min: valida stops (parse>0), roda a baseline como worker
(em paralelo), garante posse worker de worktree+.git, cria runs/<ID>, lança via systemd-run
(--collect, --auto-retry), monta o espelho herdr e devolve. NÃO espera a missão terminar.
Rodar como root (supervisor). Regras: nunca sudo dentro de stop; fence único; baseline vermelha.
"""
import argparse, concurrent.futures as cf, glob, json, os, re, subprocess, sys, time
import espelho_nativo  # GB-FUNIL-UNICO-01: porta unica de despacho (espelho nativo)

HARNESS = "/home/worker/harness-s2"
SEED_FILE = "/opt/mission-events/.seed-counter"
LEDGER = "/home/worker/harness-s2/scripts/ledger_missao.py"  # caminho estável (harness-s2 mergeado); antes apontava p/ wt-despachante-03 inexistente => run nascia sem ledger/vigia (10/10)
LINT = "/home/worker/harness-s2/scripts/contrato_lint.py"  # lint bloqueante: contrato recusado aqui NUNCA vira run (RD-HARN-LINT-ENFORCE-01)


def sh(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def next_seed():
    try:
        n = int(open(SEED_FILE).read().strip())
    except Exception:
        n = 100
    n += 1
    try:
        open(SEED_FILE, "w").write(str(n))
    except Exception:
        pass
    return n


def fail(code, **kw):
    out = {"ok": False, "erro": code}
    out.update(kw)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("contrato")
    ap.add_argument("worktree")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--budget", default="0.30")
    ap.add_argument("--turns", type=int, default=25)
    ap.add_argument("--retry", type=int, default=2)
    ap.add_argument("--setenv", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sem-baseline", action="store_true")
    ap.add_argument("--sem-ledger", action="store_true")
    a = ap.parse_args()

    if os.geteuid() != 0:
        fail("PRECISA_ROOT")
    if not os.path.isfile(a.contrato):
        fail("CONTRATO_AUSENTE", contrato=a.contrato)
    if not os.path.isdir(a.worktree):
        fail("WORKTREE_AUSENTE", worktree=a.worktree)
    texto = open(a.contrato, encoding="utf-8").read()
    m = re.search(r"^#\s*MISS[ÃA]O\s+([A-Za-z0-9._-]+)", texto, re.M)
    if not m:
        fail("SEM_TITULO_MISSAO", dica="primeira linha: '# MISSÃO <ID> — ...'")
    mid = m.group(1)
    avisos = []

    # lint bloqueante do contrato (RD-HARN-LINT-ENFORCE-01): recusa ANTES de parsear stops/baseline
    rc, lint_out = sh("python3 %s %s" % (LINT, json.dumps(a.contrato)), 60)
    if rc != 0:
        fail("LINT_RECUSADO", id=mid, detalhe=(lint_out or "").strip()[-2000:])

    sys.path.insert(0, HARNESS)
    import harness  # noqa: E402
    stops = harness.parse_stop_conditions(texto)
    if not stops:
        fail("PARSE_ZERO_STOPS", id=mid,
             dica="um único fence harness-stop com linhas 'cmd <comando>', fence fechado, sem '- cmd:'")
    if any("sudo" in (s.get("cmd") or "") for s in stops):
        fail("SUDO_NO_STOP", id=mid)
    if not re.search(r"git (reset|checkout|stash|clean)", texto) and "PROIBIDO" not in texto:
        avisos.append("contrato nao proibe git reset/checkout/stash/clean")

    # baseline: stops de entrega devem estar VERMELHOS; em paralelo, como worker
    baseline = []
    if not a.sem_baseline:
        def run_stop(s):
            c = s.get("cmd")
            if not c:
                return None
            rc, _ = sh("sudo -u worker timeout 25 bash -c %s" % json.dumps(c), 40)
            return rc == 0
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            baseline = list(ex.map(run_stop, stops))
        if baseline and all(b is True for b in baseline):
            fail("VACUO_STOPS_VERDES", id=mid,
                 dica="stop de entrega deve estar VERMELHO na baseline")
        if sum(1 for b in baseline if b is True) >= max(2, len(baseline) - 1) and len(baseline) > 2:
            avisos.append("baseline quase toda verde (%d/%d): stops de entrega fracos?" % (
                sum(1 for b in baseline if b is True), len(baseline)))

    seed = a.seed or next_seed()
    unit = "harness-%s-s%d" % (mid, seed)
    cwd = os.path.join(a.worktree, "runs", mid)
    if sh("systemctl is-active %s" % unit)[1].strip() == "active":
        fail("UNIT_JA_ATIVA", unit=unit)
    plano = {"id": mid, "unit": unit, "seed": seed, "cwd": cwd, "stops": len(stops),
             "baseline": baseline, "avisos": avisos}
    if a.dry_run:
        print(json.dumps(dict(ok=True, dry_run=True, **plano), ensure_ascii=False))
        return

    # posse: worktree + .git comum (git worktree add como root envenena o commit do worker)
    rc, gcd = sh("git -C %s rev-parse --git-common-dir" % json.dumps(a.worktree))
    gitdirs = [a.worktree]
    if rc == 0:
        g = gcd.strip().splitlines()[-1]
        g = g if os.path.isabs(g) else os.path.join(a.worktree, g)
        gitdirs.append(os.path.realpath(g))
    os.makedirs(cwd, exist_ok=True)
    for d in gitdirs:
        sh("chown -R worker:worker %s" % json.dumps(d), 120)
    rc, _ = sh("sudo -u worker touch %s" % json.dumps(os.path.join(cwd, ".wtest")))
    if rc != 0:
        fail("WORKTREE_NAO_GRAVAVEL_PELO_WORKER", cwd=cwd)

    # DESP-02B2B-fix (a): ambos os layouts de run dir — com tentativas (retry>=1) o harness cria
    # <cwd>/tentativa-1/run-*seed<seed>*; com retry 0, <cwd>/run-<ts>-seed<seed>-<pid> direto.
    padroes = [os.path.join(cwd, "run-*seed%d*" % seed),
               os.path.join(cwd, "tentativa-1", "run-*seed%d*" % seed)]

    cmd = ["systemd-run", "--uid=worker", "--unit=" + unit, "--collect",
           "--working-directory=" + HARNESS]
    ledger_ok = os.path.isfile(LEDGER) and not a.sem_ledger
    if ledger_ok:
        # vigia determinístico (sem LLM): ao fim da unit (PASS/FAIL/kill) fecha ledger + RELATORIO + aba.
        # DESP-02B2B-fix (b): prefixo '-+' tolera falha do fechar (ex.: LEDGER_AUSENTE) sem unit Failed.
        # DESP-FECHO-ROBUSTO-01: systemd nao divide comandos dentro de um valor de
        # property; fecho robusto consolidado em um unico script.
        cmd.append("--property=ExecStopPost=-+/bin/bash /home/worker/harness-s2/scripts/fechar_missao.sh %s" % (mid,))
    for kv in a.setenv:
        cmd.append("--setenv=" + kv)
    # RD-ESCADAWRITE-01: worker escreve no worktree da missao (raiz extra de escrita)
    # worktree = pai do runs dir (<wt>/runs/<ID>)
    cmd.append("--setenv=HARNESS_WRITE_ROOT=" + os.path.dirname(os.path.dirname(cwd)))
    cmd += ["/usr/bin/python3", HARNESS + "/mission_run.py", "--pane", "--escada", "on",
            "--vagueio", "on"]
    if a.retry > 0:  # DESP-02B2B-fix (c): retry 0 => sem --auto-retry
        cmd += ["--auto-retry", str(a.retry)]
    cmd += ["--max-turns", str(a.turns), "--mission", a.contrato, "--cwd", cwd,
            "--budget", str(a.budget), "--seed", str(seed), "--out", "/tmp/resumo-%s.json" % mid]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        fail("SYSTEMD_RUN_FALHOU", unit=unit, detalhe=(p.stderr or "")[:300])

    # GB-DASH-REAL-01 (ordem operador 11/10): mission_start nasce no spool real no momento do despacho
    # (mesmo schema de mission_end do vigia_chat.sh; fail-open — despacho nunca falha por spool).
    try:
        import datetime as _dt
        with open("/opt/mission-events/spool.jsonl", "a", encoding="utf-8") as _sf:
            _sf.write(json.dumps({
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "source": "despachar_missao",
                "kind": "mission_start",
                "missionId": mid,
                "pane": None,
                "session_id": "",
                "msg": "despacho missao %s (unit %s, seed %d)" % (mid, unit, seed),
                "data": {"unit": unit, "seed": seed, "budget": a.budget},
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # DESP-VIGIA-01 (ordem operador 10/10): vigia de andamento nasce junto com a missao.
    # Detached (start_new_session): nao trava o despacho. Morre sozinho no veredito;
    # caps anti-zumbi: --max-min baseado em turns x retry e --sem-avanco 20 min.
    vigia_py = "/home/worker/harness-s2/scripts/vigia_run.py"
    if os.path.isfile(vigia_py):
        max_min = max(10, (a.turns * max(1, a.retry) * 5 // 60) + 10)
        vigia_log = "/tmp/vigia-%s.jsonl" % mid
        with open(vigia_log, "ab", buffering=0) as vf:
            subprocess.Popen(
                ["/usr/bin/python3", vigia_py, mid,
                 "--intervalo", "20", "--max-min", str(max_min),
                 "--sem-avanco", "20"],
                stdout=vf, stderr=subprocess.DEVNULL,
                start_new_session=True)

    # DESPACHO-UNICO (GB-FUNIL-UNICO-01): trava de espelho nativo, fail-closed
    if not espelho_nativo.nascer_espelho(mid):
        fail("ESPELHO_NAO_NASCEU", id=mid,
             dica="espelho nativo ja existe: despacho duplicado bloqueado")
    # espelho: espera o run dir nascer (poll 0,5 s, max 40 s) e monta a aba
    tab, run_dir = None, None
    for _ in range(80):
        hit = sorted([f for pat in padroes for f in glob.glob(pat)], key=os.path.getmtime)
        if hit:
            run_dir = hit[-1]
            break
        time.sleep(0.5)
    if run_dir:
        # passa o glob do layout REAL ao mount-espelho.sh (pai do run_dir encontrado)
        espelho = os.path.join(os.path.dirname(run_dir), "run-*")
        rc, out = sh("cd %s && bash scripts/mount-espelho.sh %s %d %s" % (
            HARNESS, json.dumps(espelho), seed, mid), 90)
        mt = re.search(r"pane[^\n]*?(w\d+:p\w+)", out) or re.search(r"(w\d+:p\w+)", out)
        tab = mt.group(1) if mt else None
        if rc != 0 or not tab:
            # RD-DESP-TAB-SILENT-01 (ordem do operador 10/10: missao SEM herdr = erro critico):
            # nunca deixa run nascer fora do herdr — para a unit e falha tipado.
            subprocess.run(["systemctl", "stop", unit], capture_output=True, text=True)
            fail("PANE_AUSENTE", unit=unit, detalhe=out.strip()[-160:])
    else:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, text=True)
        fail("PANE_AUSENTE", unit=unit, detalhe="run dir nao nasceu em 40 s")

    ledger = None
    if ledger_ok and run_dir:
        rc, out = sh("python3 %s registrar %s --contrato %s --cwd %s --seed %d" % (
            LEDGER, mid, json.dumps(a.contrato), json.dumps(run_dir), seed), 60)
        ledger = {"rc": rc, "out": out.strip()[-160:]}
        if rc != 0 or '"ok": false' in out or '"ok":false' in out:
            avisos.append("ledger nao registrado (fail-open): " + out.strip()[-100:])
    # VIGIA-NASCER-03: aviso de nascimento (fail-open, timeout 5 s)
    aviso_nascimento = "falho"
    if tab:
        try:
            texto = "🛰️ NASCEU: missão %s em voo — aba %s, seed %d, budget %s" % (mid, tab, seed, a.budget)
            pr = subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_hermes.sh")],
                                 input=texto.encode(), capture_output=True, timeout=8, env=os.environ)
            if pr.stdout.strip() == b"OK":
                aviso_nascimento = "ok"
            else:
                sys.stderr.write("aviso_nascimento falhou: %s %s\n" % (pr.stdout.strip(), pr.stderr.strip()[-120:]))
        except Exception as e:
            sys.stderr.write("aviso_nascimento falhou: %r\n" % (e,))
    print(json.dumps({"ok": True, "id": mid, "unit": unit, "seed": seed, "pane": tab, "ledger": ledger,
                      "aviso_nascimento": aviso_nascimento,
                      "run_dir": run_dir, "stops": len(stops), "baseline": baseline,
                      "avisos": avisos, "ms": int((time.time() - t0) * 1000)}, ensure_ascii=False))




if __name__ == "__main__":
    main()

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # SUITE-DEBT-01(a): ANTES do import
import espelho_nativo  # GB-FUNIL-UNICO-01: porta unica de despacho (espelho nativo)
import destinos  # GB-DESP-ORDEM-01: destinos declarados num unico lugar (fim dos hard-codes)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HARNESS = "/home/worker/harness-s2"
SEED_FILE = "/opt/mission-events/.seed-counter"
LEDGER = "/home/worker/harness-s2/scripts/ledger_missao.py"  # caminho estável (harness-s2 mergeado); antes apontava p/ wt-despachante-03 inexistente => run nascia sem ledger/vigia (10/10)
LINT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contrato_lint.py")  # SUITE-DEBT-01B(a) — lint bloqueante: contrato recusado aqui NUNCA vira run (RD-HARN-LINT-ENFORCE-01)

# GB-DESP-CLEAN-01: invariante "unit viva <=> aba viva" + limpeza de orfaos.
# Overrides por env tornam a prova hermetica (herdr fake, dirs temporarios).
HERDR_BIN = os.environ.get("HERDR_BIN", "herdr")
LEDGER_DIR = os.environ.get("HERDR_LEDGER_DIR", "/root/.hermes/mission-state")
AG_LIVE_DIR = os.environ.get("HERDR_AG_LIVE_DIR", destinos.DESTINOS["ESPELHO_SALA"])  # GB-DESP-ORDEM-01


def panes_vivas():
    """Lista pane ids vivos do herdr (mesmo caminho usado pelo mount-espelho).
    Retorna None se o herdr estiver indisponivel (fail-open: nao derruba missao)."""
    rc, out = sh("%s pane list" % json.dumps(HERDR_BIN), 15)
    if rc != 0:
        return None
    try:
        data = json.loads(out)
        panes = data.get("result", {}).get("panes", [])
        if not isinstance(panes, list):
            return None
        return [p.get("pane_id") or p.get("id") for p in panes if isinstance(p, dict)]
    except Exception:
        return None


def verificar_unit_com_aba(unit):
    """GB-DESP-CLEAN-01: unit ativa SEM pane viva no herdr => systemctl stop +
    fail tipado UNIT_SEM_ABA. Nunca deixa run headless invisivel nascer/continuar."""
    rc, out = sh("systemctl is-active %s" % json.dumps(unit), 15)
    if out.strip() != "active":
        return  # unit nem esta viva: nada a verificar
    panes = panes_vivas()
    if panes is None:
        return  # herdr indisponivel: fail-open
    if not panes:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, text=True)
        fail("UNIT_SEM_ABA", unit=unit, detalhe="unit ativa sem pane viva no herdr")


def limpar_orfaos(mid):
    """GB-DESP-CLEAN-01: no inicio de TODO despacho — ledger em running_sem_resumo
    sem unit viva => arquivar (archive-ledger-<id>-<ts>.json) e remover espelho
    pousado. NUNCA toca missao com unit viva. Deterministico, sem interativo."""
    led = os.path.join(LEDGER_DIR, mid + ".json")
    try:
        with open(led, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    if not isinstance(data, dict) or data.get("status") != "running_sem_resumo":
        return
    unit = data.get("unit") or "harness-%s-s%s" % (mid, data.get("seed", ""))
    rc, out = sh("systemctl is-active %s" % json.dumps(unit), 15)
    if out.strip() == "active":
        return  # unit viva: missao legitima, nao remover nada
    ts = time.strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(LEDGER_DIR, "archive-ledger-%s-%s.json" % (mid, ts))
    try:
        os.replace(led, dst)
    except Exception:
        pass
    esp = os.path.join(AG_LIVE_DIR, mid + ".espelho.pousado.json")
    try:
        os.remove(esp)
    except Exception:
        pass


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


def notify_nascimento(texto, tentativas=4, script=None):
    """GB-VIGIA-RETRY-01: aviso de nascimento com retry e backoff (2s/5s/15s).

    Retorna ("ok"|"falho", detalhe). Fail-open: quem chama decide o que fazer
    quando o status é "falho" — o despacho segue de qualquer forma.
    """
    if script is None:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_hermes.sh")
    backoff = [2, 5, 15]
    detalhe = ""
    for i in range(tentativas):
        try:
            pr = subprocess.run(["bash", script], input=texto.encode(),
                                capture_output=True, timeout=8, env=os.environ)
            if pr.stdout.strip() == b"OK":
                return "ok", ""
            detalhe = "%s %s" % (pr.stdout.strip(), pr.stderr.strip()[-120:])
        except Exception as e:
            detalhe = repr(e)
        if i < tentativas - 1:
            time.sleep(backoff[min(i, len(backoff) - 1)])  # backoff 2s/5s/15s
    return "falho", detalhe


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
    ap.add_argument("--executar", action="store_true")  # GB-CANAL-UNICO-01: spawn direto SOMENTE para o consumer/prova
    a = ap.parse_args()

    # GB-DESP-ORDEM-01: PROVA_HERMETICA=1 permite rodar a prova sem root
    # (dirs e binarios fake via env); em producao o root continua exigido.
    if os.geteuid() != 0 and os.environ.get("PROVA_HERMETICA") != "1":
        fail("PRECISA_ROOT")
    if not os.path.isfile(a.contrato):
        fail("CONTRATO_AUSENTE", contrato=a.contrato)
    # GB-CANAL-UNICO-01 (ordem do operador 13/10): por PADRAO o despachante
    texto0 = open(a.contrato, encoding="utf-8").read()
    m0 = re.search(r"^#\s*MISS[ÃA]O\s+([A-Za-z0-9._-]+)", texto0, re.M)
    mid0 = m0.group(1) if m0 else os.path.basename(a.contrato).replace("missao-", "").replace(".md", "")
    # LINT-GATE-PORTA-01: contrato lintado NA PORTA — recusado NUNCA enfileira
    rc, lint_out = sh("python3 %s %s" % (LINT, json.dumps(a.contrato)), 60)
    if rc != 0:
        fail("LINT_RECUSADO", id=mid0, detalhe=(lint_out or "").strip()[-2000:])
    # LINT-GATE-PORTA-01 (dry-run): validação COMPLETA na porta (stops + baseline
    # de entrega vermelhos) — recusa tipada ANTES de enfileirar.
    if a.dry_run:
        sys.path.insert(0, HARNESS)
        import harness as _harness  # noqa: E402
        stops0 = _harness.parse_stop_conditions(texto0)
        if not stops0:
            fail("PARSE_ZERO_STOPS", id=mid0,
                 dica="um único fence harness-stop com linhas 'cmd <comando>'")
        if any("sudo" in (s.get("cmd") or "") for s in stops0):
            fail("SUDO_NO_STOP", id=mid0)
        if not a.sem_baseline:
            def _run_stop0(s):
                c = s.get("cmd")
                if not c:
                    return None
                rc0, _ = sh("sudo -u worker timeout 25 bash -c %s" % json.dumps(c), 40)
                return rc0 == 0
            with cf.ThreadPoolExecutor(max_workers=8) as ex:
                baseline0 = list(ex.map(_run_stop0, stops0))
            if baseline0 and all(b is True for b in baseline0):
                fail("VACUO_STOPS_VERDES", id=mid0,
                     dica="stop de entrega deve estar VERMELHO na baseline")
    # NAO spawna — ENFILEIRA no orchestrator-queue.jsonl (o consumer do
    # Guardian despacha com --executar). Spawn direto so com --executar
    # (consumer) ou CONSUMER_DISPATCH=1 (prova hermetica).
    if not a.executar and os.environ.get("CONSUMER_DISPATCH") != "1" and os.environ.get("PROVA_HERMETICA") != "1":
        mid0 = os.path.basename(a.contrato).replace("missao-", "").replace(".md", "")
        fila = os.environ.get("QUEUE_PATH", "/opt/mission-events/orchestrator-queue.jsonl")
        payload = json.dumps({"id": mid0 + "-" + str(int(time.time())),
                              "type": "mission",
                              "missionId": mid0,
                              "priority": 5,
                              "enqueuedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "source": "despachante_canal_unico",
                              "payload": {"prompt": a.contrato, "worktree": a.worktree, "cwd": a.worktree,
                                          "seed": a.seed, "budget": a.budget,
                                          "maxTurns": a.turns, "retry": a.retry,
                                          "setenv": a.setenv}}, ensure_ascii=False)
        try:
            with open(fila, "a", encoding="utf-8") as f:
                f.write(payload + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            fail("FILA_INDISPONIVEL", detalhe=str(e)[:120])
        print(json.dumps({"ok": True, "enfileirado": True, "dry_run": bool(a.dry_run), "mid": mid0, "fila": fila}, ensure_ascii=False))
        return
    if not os.path.isdir(a.worktree):
        fail("WORKTREE_AUSENTE", worktree=a.worktree)
    texto = open(a.contrato, encoding="utf-8").read()
    m = re.search(r"^#\s*MISS[ÃA]O\s+([A-Za-z0-9._-]+)", texto, re.M)
    if not m:
        fail("SEM_TITULO_MISSAO", dica="primeira linha: '# MISSÃO <ID> — ...'")
    mid = m.group(1)
    avisos = []

    # lint bloqueante do contrato (RD-HARN-LINT-ENFORCE-01): recusa ANTES de parsear stops/baseline

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
    # GB-DESP-CLEAN-01: limpeza de orfaos ANTES de checar unit (ledger/espelho de
    # missao morta sem unit viva sao arquivados/removidos; missao com unit viva intacta).
    limpar_orfaos(mid)
    if sh("systemctl is-active %s" % unit)[1].strip() == "active":
        # GB-DESP-CLEAN-01: caminho UNIT_JA_ATIVA agora verifica a invariante —
        # unit ativa SEM pane viva => stop + UNIT_SEM_ABA (antes: recusa cega).
        verificar_unit_com_aba(unit)
        fail("UNIT_JA_ATIVA", unit=unit)
    plano = {"id": mid, "unit": unit, "seed": seed, "cwd": cwd, "stops": len(stops),
             "baseline": baseline, "avisos": avisos}
    if a.dry_run:
        print(json.dumps(dict(ok=True, dry_run=True, **plano), ensure_ascii=False))
        return

    # GB-DESP-ORDEM-01: ordem do pipeline — (b) guard de duplicidade (espelho
    # nativo + unit viva) ANTES do spawn. Falha aqui = fail tipado SEM unit viva
    # (licao GB-THUMB-03/GB-OFFICE-CARD-01: spawn antes do guard deixava unit
    # headless viva quando o guard falhava).
    if not espelho_nativo.nascer_espelho(mid):
        fail("ESPELHO_NAO_NASCEU", id=mid,
             dica="espelho nativo ja existe: despacho duplicado bloqueado")

    # posse: worktree + .git comum (git worktree add como root envenena o commit do worker)
    rc, gcd = sh("git -C %s rev-parse --git-common-dir" % json.dumps(a.worktree))
    gitdirs = [a.worktree]
    if rc == 0:
        g = gcd.strip().splitlines()[-1]
        g = g if os.path.isabs(g) else os.path.join(a.worktree, g)
        gitdirs.append(os.path.realpath(g))
    os.makedirs(cwd, exist_ok=True)
    # GB-DESP-ORDEM-01: posse so e ajustavel/verificavel quando o despachante roda
    # como root; rodando como worker (prova hermetica local), o touch direto basta.
    if os.geteuid() == 0:
        for d in gitdirs:
            sh("chown -R worker:worker %s" % json.dumps(d), 120)
        rc, _ = sh("sudo -u worker touch %s" % json.dumps(os.path.join(cwd, ".wtest")))
    else:
        rc, _ = sh("touch %s" % json.dumps(os.path.join(cwd, ".wtest")))
    if rc != 0:
        fail("WORKTREE_NAO_GRAVAVEL_PELO_WORKER", cwd=cwd)

    # DESP-02B2B-fix (a): ambos os layouts de run dir — com tentativas (retry>=1) o harness cria
    # <cwd>/tentativa-1/run-*seed<seed>*; com retry 0, <cwd>/run-<ts>-seed<seed>-<pid> direto.
    padroes = [os.path.join(cwd, "run-*seed%d*" % seed),
               os.path.join(cwd, "tentativa-1", "run-*seed%d*" % seed)]

    # DESPACHO-UNICO (operator 12/10, fail-closed): o espelho da sala NASCE AQUI.
    # Missao sem espelho = invisivel no Agent Office (erro repetido 12/10). Sem
    # espelho gravado, o despacho RECUSA — impossivel nascer invisivel.
    esp_dir = destinos.DESTINOS["ESPELHO_SALA"]  # GB-DESP-ORDEM-01
    espelho = os.path.join(esp_dir, mid + ".espelho.json")
    try:
        os.makedirs(esp_dir, exist_ok=True)
        with open(espelho, "w", encoding="utf-8") as _f:
            json.dump({"id": mid, "status": "running",
                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%S-03:00")}, _f)
        sh("chown worker:worker " + json.dumps(espelho))
        if not os.path.isfile(espelho):
            raise RuntimeError("espelho ausente pos-gravacao")
    except Exception as _e:
        fail("ESPELHO_NAO_NASCEU", mission=mid, detalhe=str(_e)[:200])

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
            "--budget", str(a.budget), "--seed", str(seed), "--out", destinos.resumo(mid)]  # GB-DESP-ORDEM-01
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        # GB-DESP-CLEAN-01: erro pos-spawn — unit pode ter nascido antes da falha
        verificar_unit_com_aba(unit)
        fail("SYSTEMD_RUN_FALHOU", unit=unit, detalhe=(p.stderr or "")[:300])
    # GB-DESP-CLEAN-01: pos-spawn imediato — unit viva sem herdr => recusa tipada
    verificar_unit_com_aba(unit)

    # GB-DASH-REAL-01 (ordem operador 11/10): mission_start nasce no spool real no momento do despacho
    # (mesmo schema de mission_end do vigia_chat.sh; fail-open — despacho nunca falha por spool).
    try:
        import datetime as _dt
        with open(destinos.DESTINOS["SPOOL"], "a", encoding="utf-8") as _sf:  # GB-DESP-ORDEM-01
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
    if os.path.isfile(vigia_py) and os.environ.get("PROVA_HERMETICA") != "1":
        max_min = max(10, (a.turns * max(1, a.retry) * 5 // 60) + 10)
        vigia_log = "/tmp/vigia-%s.jsonl" % mid
        with open(vigia_log, "ab", buffering=0) as vf:
            subprocess.Popen(
                ["/usr/bin/python3", vigia_py, mid,
                 "--intervalo", "20", "--max-min", str(max_min),
                 "--sem-avanco", "20"],
                stdout=vf, stderr=subprocess.DEVNULL,
                start_new_session=True)

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
        # GB-DESP-CLEAN-01: pos-spawn — unit viva precisa ter pane viva no herdr
        verificar_unit_com_aba(unit)
    else:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, text=True)
        fail("PANE_AUSENTE", unit=unit, detalhe="run dir nao nasceu em 40 s")
    # GB-DESP-CLEAN-01: sucesso — invariante final: unit viva <=> pane viva
    verificar_unit_com_aba(unit)

    # GB-SALA-ESPELHO-02: grava espelho de nascimento no dir de sala (ESPELHO_SALA
    # em destinos.py — GB-DESP-ORDEM-01; dir que a ponte do escritorio drena). Apos o mount-espelho ter SUCESSO (tab != None).
    # Fail-open: se a escrita falhar, apenas avisa — nunca derruba o despacho.
    # Sobrescreve se ja existe (retry de despacho nao deve enfileirar
    # session_start duplicado na ponte — a ponte deduplifica por id).
    if tab:
        try:
            ag_live_dir = os.environ.get("AG_LIVE_DIR") or destinos.DESTINOS["ESPELHO_SALA"]  # GB-DESP-ORDEM-01
            os.makedirs(ag_live_dir, exist_ok=True)
            espelho_path = os.path.join(ag_live_dir, "%s.espelho.json" % mid)
            espelho = {
                "id": mid,
                "tab_id": tab,
                "pane_id": tab,
                "workspace_id": tab.split(":", 1)[0],
                "status": "running",
                "started_at": _dt.datetime.now(_dt.timezone.utc)
                    .astimezone().isoformat(timespec="seconds"),
            }
            tmp_path = espelho_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as ef:
                json.dump(espelho, ef, ensure_ascii=False)
                ef.write("\n")
            os.replace(tmp_path, espelho_path)
        except Exception as e:
            avisos.append("espelho de sala (ESPELHO_SALA) nao gravado (fail-open): %r" % (e,))

    ledger = None
    if ledger_ok and run_dir:
        rc, out = sh("python3 %s registrar %s --contrato %s --cwd %s --seed %d" % (
            LEDGER, mid, json.dumps(a.contrato), json.dumps(run_dir), seed), 60)
        ledger = {"rc": rc, "out": out.strip()[-160:]}
        if rc != 0 or '"ok": false' in out or '"ok":false' in out:
            avisos.append("ledger nao registrado (fail-open): " + out.strip()[-100:])
    # VIGIA-NASCER-03 / GB-VIGIA-RETRY-01: aviso de nascimento com retry e backoff (fail-open)
    aviso_nascimento = "falho"
    if tab:
        texto = "🛰️ NASCEU: missão %s em voo — aba %s, seed %d, budget %s" % (mid, tab, seed, a.budget)
        # GB-AVISO-CHAT-02: aviso no CHAT ATIVO via aviso_chat.sh (retry tipado,
        # fail-open — falha de aviso NUNCA derruba o despacho; grava no spool AVISO_SPOOL).
        try:
            pr = subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)), "aviso_chat.sh"), texto],
                                 capture_output=True, timeout=15, env=os.environ)
            if b'"delivered":true' in pr.stdout:
                aviso_nascimento = "ok"
            else:
                sys.stderr.write("aviso_nascimento falhou: %s %s\n" % (pr.stdout.strip(), pr.stderr.strip()[-120:]))
        except Exception as e:
            sys.stderr.write("aviso_nascimento falhou: %r\n" % (e,))
    print(json.dumps({"ok": True, "id": mid, "unit": unit, "seed": seed, "pane": tab, "tab": tab, "ledger": ledger,
                      "aba_verificada": True,
                      "aviso_nascimento": aviso_nascimento,
                      "run_dir": run_dir, "stops": len(stops), "baseline": baseline,
                      "avisos": avisos, "ms": int((time.time() - t0) * 1000)}, ensure_ascii=False))




if __name__ == "__main__":
    main()

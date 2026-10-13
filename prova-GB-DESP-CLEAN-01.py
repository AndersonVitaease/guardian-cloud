#!/usr/bin/env python3
"""prova-GB-DESP-CLEAN-01.py — prova hermetica da invariante unit viva <=> aba viva.

(a) unit ativa SEM pane no herdr (fake) => despacho recusa UNIT_SEM_ABA e unit e parada;
(b) ledger running_sem_resumo sem unit viva => arquivado por limpar_orfaos + espelho removido;
(c) despacho normal (unit inativa, herdr com pane) => dry-run ok (invariante verificada).

Importa despachar_missao como modulo (geteuid mockado para 0 — prova roda como worker),
fakes em tmpdir via env (HERDR_BIN, HERDR_LEDGER_DIR, HERDR_AG_LIVE_DIR, PATH).
Sem sudo, sem rede, deterministico.
"""
import contextlib, importlib.util, io, json, os, sys, tempfile, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "scripts", "despachar_missao.py")


def load_module():
    spec = importlib.util.spec_from_file_location("despachar_missao", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_despacho(env, contrato, worktree, seed=4242):
    # env ANTES do load: HERDR_BIN/LEDGER_DIR/AG_LIVE_DIR sao lidos no import
    old = dict(os.environ)
    os.environ.update(env)
    old_argv = sys.argv
    sys.argv = [SCRIPT, contrato, worktree, "--seed", str(seed),
                "--dry-run", "--sem-baseline"]
    real_geteuid = os.geteuid
    os.geteuid = lambda: 0  # prova roda como worker; despachante exige root
    buf = io.StringIO()
    try:
        mod = load_module()  # modulo fresco: capta os overrides de env
        try:
            with contextlib.redirect_stdout(buf):
                mod.main()
        except SystemExit:
            pass
        lines = [l for l in buf.getvalue().strip().splitlines() if l.strip()]
        try:
            return json.loads(lines[-1])
        except Exception:
            return {"ok": None, "raw": buf.getvalue()}
    finally:
        os.geteuid = real_geteuid
        sys.argv = old_argv
        os.environ.clear()
        os.environ.update(old)


def main():
    tmp = tempfile.mkdtemp(prefix="prova-gb-desp-clean-01-")
    mod = load_module()
    herdr = os.path.join(tmp, "herdr")
    ctl = os.path.join(tmp, "systemctl")
    ledger_dir = os.path.join(tmp, "mission-state"); os.makedirs(ledger_dir)
    ag_dir = os.path.join(tmp, "ag-live"); os.makedirs(ag_dir)
    wt = os.path.join(tmp, "wt"); os.makedirs(wt)
    contrato = os.path.join(tmp, "contrato.md")
    open(contrato, "w").write(textwrap.dedent("""\
            # MISSÃO PROVA-GB-DESP-CLEAN-01 — prova hermetica
            ## MAPA
            - scripts/despachar_missao.py
            PROIBIDO sudo
            ```harness-stop
            cmd cd /tmp && grep -q -F 'ENTREGA-GB-DESP-CLEAN-01' entrega-gb-desp-clean-01.txt
            ```
            """))
    mid = "PROVA-GB-DESP-CLEAN-01"
    unit = "harness-%s-s4242" % mid
    env = {"HERDR_BIN": herdr, "HERDR_LEDGER_DIR": ledger_dir,
           "HERDR_AG_LIVE_DIR": ag_dir, "PATH": tmp + ":" + os.environ["PATH"]}

    # ---- (a) unit ativa SEM pane => UNIT_SEM_ABA + systemctl stop
    open(herdr, "w").write('#!/bin/sh\necho \'{"result":{"panes":[]}}\'\n')
    os.chmod(herdr, 0o755)
    stop_log = os.path.join(tmp, "stop.log")
    open(ctl, "w").write('#!/bin/sh\nif [ "$1" = is-active ]; then echo active; exit 0; fi\n'
                         'echo "$@" >> %s\nexit 0\n' % stop_log)
    os.chmod(ctl, 0o755)
    out = run_despacho(env, contrato, wt)
    ok_a = out is not None and out.get("ok") is False and out.get("erro") == "UNIT_SEM_ABA"
    ok_a = ok_a and os.path.isfile(stop_log) and unit in open(stop_log).read()

    # ---- (b) ledger running_sem_resumo sem unit viva => arquivado + espelho removido
    led = os.path.join(ledger_dir, mid + ".json")
    open(led, "w").write(json.dumps({"id": mid, "status": "running_sem_resumo",
                                     "unit": unit, "seed": 4242}))
    esp = os.path.join(ag_dir, mid + ".espelho.pousado.json")
    open(esp, "w").write(json.dumps({"id": mid, "status": "running"}))
    open(ctl, "w").write('#!/bin/sh\nif [ "$1" = is-active ]; then echo inactive; exit 3; fi\n'
                         'exit 0\n')
    os.chmod(ctl, 0o755)
    out_b = run_despacho(env, contrato, wt)
    arq = [f for f in os.listdir(ledger_dir) if f.startswith("archive-ledger-%s-" % mid)]
    ok_b = bool(arq) and not os.path.exists(led) and not os.path.exists(esp)

    # ---- (c) despacho normal: unit inativa, herdr com pane => dry-run ok
    open(herdr, "w").write('#!/bin/sh\necho \'{"result":{"panes":[{"pane_id":"w1:p1"}]}}\'\n')
    os.chmod(herdr, 0o755)
    out_c = run_despacho(env, contrato, wt)
    ok_c = out_c is not None and out_c.get("ok") is True and out_c.get("dry_run") is True

    print("(a) UNIT_SEM_ABA + stop:", ok_a, (out or {}).get("erro"))
    print("(b) orfao arquivado + espelho removido:", ok_b, arq)
    print("(c) despacho normal ok:", ok_c, (out_c or {}).get("ok"))
    if ok_a and ok_b and ok_c:
        print("GB-DESP-CLEAN-01-PROVA-OK")
        return 0
    print("GB-DESP-CLEAN-01-PROVA-FALHOU")
    return 1


if __name__ == "__main__":
    sys.exit(main())
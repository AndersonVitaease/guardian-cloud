#!/usr/bin/env python3
"""RD-TOOL-TRIAGEM-01 — triagem determinística de FAIL a partir dos trails.

triar(runs_dir) -> dict {missao, tentativas, causa_dominante, acao}
CLI: python3 scripts/triagem.py <runs_dir>  (imprime JSON; exit 0)
Diretório inválido/vazio -> mensagem clara em stderr, exit 2.
"""
import argparse
import glob
import json
import os
import sys

try:  # reaproveita o leitor de trail do diagnostico, sem quebrá-lo
    from scripts.diagnostico import _ler_trail
except ImportError:  # chamada como script direto
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.diagnostico import _ler_trail  # noqa: E402

PRIORIDADE = ["SETUP_PERMISSAO", "LEITURA_RECUSADA", "EDIT_FALHOU",
              "LOOP_COMANDO_RECUSADO", "SO_EXPLORACAO", "VAGUEIO", "STOPS_LENTOS"]

ACOES = {
    "PASS": "missão concluída com PASS: nenhuma ação necessária",
    "SETUP_PERMISSAO": "chown -R worker:worker no worktree",
    "LEITURA_RECUSADA": "o harness recusou leitura: confirme BASH-FILTRO-PIPE-01 e o contrato não cita cat/head/ls",
    "EDIT_FALHOU": "Edit com indentação errada: use old_string de uma linha / RD-HARNESS-EDIT-ROBUSTO-01",
    "LOOP_COMANDO_RECUSADO": "worker em loop: pare a run e redespache com instrução explícita",
    "SO_EXPLORACAO": "contrato sem MAPA: fatie com scripts/fatiar_auto.py ou inclua arquivo:LINHA",
    "VAGUEIO": "worker vagueou: redespache com contrato mais específico e janela menor",
    "STOPS_LENTOS": "stop-checks consumindo o tempo: reduza a frequência de verificação no harness",
    "SEM_CAUSA": "FAIL sem causa catalogada: ler o trail manualmente",
}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _cmd(r):
    inp = r.get("input")
    if isinstance(inp, dict):
        return inp.get("command") or ""
    if isinstance(inp, str):
        try:  # trail às vezes serializa input como JSON-string
            obj = json.loads(inp)
            if isinstance(obj, dict):
                return obj.get("command") or inp
        except ValueError:
            pass
        return inp
    return ""


def _causas(recs):
    """Aplica as regras de causa sobre os registros de uma tentativa."""
    causas = []
    bash = [r for r in recs if r.get("tool") == "Bash"]
    bash_err = [r for r in bash if r.get("is_error")]
    leituras = [r for r in bash_err if _num(r.get("latencia_ms")) <= 2]
    edits = [r for r in recs if r.get("tool") == "Edit"]
    edit_err = [r for r in edits if r.get("is_error")]
    escrita = [r for r in recs if r.get("tool") in ("Write", "Edit")]
    resumo = [r for r in recs if r.get("tool") == "_resumo"]
    motivo = resumo[-1].get("motivo") if resumo else None

    if motivo == "setup_permissao" or any(
            r.get("tool") == "_resumo" and r.get("motivo") == "setup_permissao" for r in recs):
        causas.append("SETUP_PERMISSAO")
    if len(leituras) >= 3:
        causas.append("LEITURA_RECUSADA")
    if len(edit_err) >= 2:
        causas.append("EDIT_FALHOU")
    cont = {}
    for r in bash_err:
        c = _cmd(r)
        if c:
            cont[c] = cont.get(c, 0) + 1
    if cont and max(cont.values()) >= 3:
        causas.append("LOOP_COMANDO_RECUSADO")
    if len(bash) >= 15 and not escrita:
        causas.append("SO_EXPLORACAO")
    if any(r.get("tool") == "_vagueio" for r in recs):
        causas.append("VAGUEIO")
    stops = [r for r in recs if r.get("tool") == "_stop_check" and "latencia_ms" in r]
    if stops:
        total = sum(_num(r.get("latencia_ms")) for r in recs if "latencia_ms" in r)
        st = sum(_num(r.get("latencia_ms")) for r in stops)
        if total > 0 and st > 0.4 * total:
            causas.append("STOPS_LENTOS")
    return causas, cont


def _evidencia(recs, causas, cont):
    bash = [r for r in recs if r.get("tool") == "Bash"]
    bash_err = [r for r in bash if r.get("is_error")]
    leituras = [r for r in bash_err if _num(r.get("latencia_ms")) <= 2]
    edit_err = [r for r in recs if r.get("tool") == "Edit" and r.get("is_error")]
    escrita = [r for r in recs if r.get("tool") in ("Write", "Edit")]
    partes = ["bash=%d err=%d" % (len(bash), len(bash_err))]
    if "LEITURA_RECUSADA" in causas:
        partes.append("leituras_recusadas=%d" % len(leituras))
    if "EDIT_FALHOU" in causas:
        partes.append("edit_err=%d" % len(edit_err))
    if "LOOP_COMANDO_RECUSADO" in causas:
        partes.append("mesmo_comando_erro_x%d" % max(cont.values()))
    if "SO_EXPLORACAO" in causas:
        partes.append("write/edit=0")
    if "VAGUEIO" in causas:
        partes.append("registro_vagueio=1")
    resumo = [r for r in recs if r.get("tool") == "_resumo"]
    if resumo:
        partes.append("motivo=%s" % resumo[-1].get("motivo"))
    return "; ".join(partes)


def triar(runs_dir):
    runs_dir = os.path.abspath(runs_dir)
    if not os.path.isdir(runs_dir):
        raise SystemExit("ERRO: runs_dir inexistente: %s" % runs_dir)
    tentativas_dirs = sorted(glob.glob(os.path.join(runs_dir, "tentativa-*")))
    if not tentativas_dirs:
        raise SystemExit("ERRO: nenhuma tentativa-N em %s" % runs_dir)

    missao = os.path.basename(runs_dir.rstrip("/"))
    tentativas = []
    for tdir in tentativas_dirs:
        try:
            n = int(os.path.basename(tdir).split("-", 1)[1])
        except ValueError:
            continue
        trails = sorted(glob.glob(os.path.join(tdir, "run-*", "harness-trail.jsonl")))
        recs = []
        for tp in trails:
            r = _ler_trail(tp)
            if r:
                recs.extend(r)
        if not recs:
            tentativas.append({"n": n, "causas": [], "evidencia": "sem trail legível",
                               "veredito": "FAIL", "turnos": 0})
            continue
        causas, cont = _causas(recs)
        resumo = [r for r in recs if r.get("tool") == "_resumo"]
        veredito = (resumo[-1].get("veredito") if resumo else None) or "FAIL"
        turnos = 0
        for r in recs:
            t = r.get("turno")
            try:
                turnos = max(turnos, int(t))
            except (TypeError, ValueError):
                pass
        tentativas.append({"n": n, "causas": causas,
                           "evidencia": _evidencia(recs, causas, cont),
                           "veredito": veredito, "turnos": turnos})

    if tentativas and tentativas[-1].get("veredito") == "PASS":
        dominante = "PASS"
    else:
        todas = [c for t in tentativas for c in t["causas"]]
        dominante = None
        for c in PRIORIDADE:
            if c in todas:
                dominante = c
                break
        if dominante is None:
            dominante = "SEM_CAUSA"
    return {"missao": missao, "tentativas": tentativas,
            "causa_dominante": dominante, "acao": ACOES[dominante]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Triagem determinística de FAIL")
    ap.add_argument("runs_dir")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.runs_dir):
        print("ERRO: runs_dir inexistente: %s" % args.runs_dir, file=sys.stderr)
        return 2
    if not glob.glob(os.path.join(args.runs_dir, "tentativa-*")):
        print("ERRO: nenhuma tentativa-N em %s" % args.runs_dir, file=sys.stderr)
        return 2
    print(json.dumps(triar(args.runs_dir), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
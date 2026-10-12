#!/usr/bin/env python3
"""Prova hermética LEDGER-REOPEN-FIX-01: 3 caminhos do fechar().

1. failed com veredito None (fecho automático sem resumo) + resumo real
   com PASS -> reabre e sobrescreve com closed/veredito/custo/turnos.
2. Fecho sem resumo (resumo vazio/ausente) -> running_sem_resumo
   (não-terminal; fecho posterior com resumo real ainda funciona).
3. Fecho normal com resumo -> closed com veredito.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_missao import fechar, registrar, _gravar_atomico, _caminho

falhas = []


def checar(nome, cond, detalhe=""):
    if cond:
        print("OK   %s" % nome)
    else:
        falhas.append(nome)
        print("FAIL %s %s" % (nome, detalhe))


def ledger_de(mid, sd):
    return json.loads(Path(_caminho(mid, sd)).read_text(encoding="utf-8"))


def main():
    with tempfile.TemporaryDirectory() as td:
        sd = str(Path(td) / "state")
        resumos = Path(td) / "resumos"
        resumos.mkdir(parents=True)
        _gravar_atomico(resumos / "real.json", {
            "veredito": "PASS", "custo_usd": 0.42, "turnos": 12,
            "run_dir": str(td),
        })
        _gravar_atomico(Path(resumos) / "vazio.json", {})
        _gravar_atomico(Path(resumos) / "falha.json", {
            "veredito": "FAIL", "custo_usd": 0.10, "turnos": 3,
        })
        registrar("M1", str(td), "contrato.md", "2290", state_dir=sd,
                  runner=lambda *a, **k: None, espera_s=0)
        registrar("M2", str(td), "contrato.md", "2291", state_dir=sd,
                  runner=lambda *a, **k: None, espera_s=0)
        registrar("M3", str(td), "contrato.md", "2292", state_dir=sd,
                  runner=lambda *a, **k: None, espera_s=0)
        # Estado histórico bugado: failed com veredito None (ExecStopPost).
        p1 = Path(_caminho("M1", sd))
        bugado = json.loads(p1.read_text(encoding="utf-8"))
        bugado.update({"status": "failed", "veredito": None})
        p1.write_text(json.dumps(bugado), encoding="utf-8")

        # Caminho 1: reabre failed+None com resumo real.
        out = fechar("M1", str(resumos / "real.json"), state_dir=sd,
                     runner=lambda *a, **k: None)
        l1 = ledger_de("M1", sd)
        checar("1.reabre_ok", out.get("ok") is True, str(out))
        checar("1.status_closed", l1.get("status") == "closed", str(l1.get("status")))
        checar("1.veredito_pass", l1.get("veredito") == "PASS", str(l1.get("veredito")))
        checar("1.custo", l1.get("custo_usd") == 0.42, str(l1.get("custo_usd")))
        checar("1.turnos", l1.get("turnos") == 12, str(l1.get("turnos")))
        checar("1.nao_idempotente_bloq", not out.get("idempotente"), str(out))
        # Idempotência REAL depois do fecho legítimo continua valendo.
        out2 = fechar("M1", str(resumos / "real.json"), state_dir=sd,
                      runner=lambda *a, **k: None)
        checar("1.idempotente_depois", out2.get("idempotente") is True, str(out2))

        # Caminho 2: fecho sem resumo -> running_sem_resumo (não-terminal).
        out3 = fechar("M2", str(resumos / "vazio.json"), state_dir=sd,
                      runner=lambda *a, **k: None)
        l2 = ledger_de("M2", sd)
        checar("2.sem_resumo_status", l2.get("status") == "running_sem_resumo",
               str(l2.get("status")))
        checar("2.nao_gravou_failed", l2.get("status") != "failed", str(l2))
        checar("2.aviso", out3.get("aviso") == "sem_veredito_resumo", str(out3))
        # Fecho posterior com resumo real funciona (não-terminal).
        out4 = fechar("M2", str(resumos / "real.json"), state_dir=sd,
                      runner=lambda *a, **k: None)
        l2b = ledger_de("M2", sd)
        checar("2.fecho_posterior", l2b.get("status") == "closed"
               and l2b.get("veredito") == "PASS", str(l2b))

        # Caminho 3: fecho normal -> closed com veredito.
        out5 = fechar("M3", str(resumos / "real.json"), state_dir=sd,
                      runner=lambda *a, **k: None)
        l3 = ledger_de("M3", sd)
        checar("3.status_closed", l3.get("status") == "closed", str(l3.get("status")))
        checar("3.veredito", l3.get("veredito") == "PASS", str(l3.get("veredito")))
        checar("3.out_ok", out5.get("ok") is True and out5.get("status") == "closed",
               str(out5))

        # Extra: failed legítimo (veredito FAIL real) NÃO reabre.
        out6 = fechar("M3", str(resumos / "falha.json"), state_dir=sd,
                      runner=lambda *a, **k: None)
        checar("4.failed_legitimo_travado", out6.get("idempotente") is True,
               str(out6))

    print("LEDGER-REOPEN-OK" if not falhas else "LEDGER-REOPEN-OK(N/A)")
    print("RESUMO: %d falhas" % len(falhas))
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())

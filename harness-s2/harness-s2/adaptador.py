# Adaptador missão-ops → harness v2 (HARNESS-SPRINT4-01, item 1)
#
# Lê um contrato `missao-*.md` do mission-ops (seções Entregas/Provas/Regras)
# e produz o dict de configuração que `harness.run_mission` consome:
# stop-conditions, budget, max-turnos, cwd e mission id.
#
# Regra de honestidade: contrato com bloco ```harness-stop``` inline vence;
# sem bloco, deriva `cmd` do "## Provas" quando há comando determinístico
# (linha com `/usr/bin/python3` ou `pytest`); se não deriva, FAIL no setup —
# não adivinhar prova subjetiva.
import re


class AdaptadorSetupError(Exception):
    """Contrato mission-ops não adaptável a stop-conditions determinísticas."""


DEFAULT_BUDGET_USD = 1.0
DEFAULT_MAX_TURNS = 60

# Linha de prova determinística: comando absoluto python3 ou pytest.
_RE_CMD = re.compile(r"((?:/usr/bin/python3|python3)\s+-m\s+pytest\s+\S+)")
# Aceita vírgula decimal pt-BR (ex.: "budget US$ 0,50" -> 0.5).
_RE_BUDGET = re.compile(r"budget\s+US\$\s*([\d.,]+)", re.I)
_RE_MISSION = re.compile(r"^#\s*MISSÃO\s+([A-Z0-9][A-Z0-9-]*)", re.M)


def _extrair_bloco(texto):
    m = re.search(r"```harness-stop\n(.*?)```", texto, re.S)
    return m.group(1) if m else None


def _derivar_cmd_de_provas(texto):
    """Primeiro comando determinístico da seção Provas (ou do contrato todo)."""
    m = re.search(r"##\s*Provas(.*?)(?:\n##\s|\Z)", texto, re.S)
    secao = m.group(1) if m else texto
    hit = _RE_CMD.search(secao)
    if not hit:
        hit = _RE_CMD.search(texto)
    return hit.group(1).strip().rstrip("`") if hit else None


def adaptar_contrato(missao_texto, cwd, budget_usd=None, max_turns=None):
    """Converte contrato mission-ops em config do harness.

    Retorna dict: {mission, cwd, budget_usd, max_turns, stop_conditions,
    contrato_texto}. Levanta AdaptadorSetupError se não houver prova
    determinística (FAIL honesto no setup, sem adivinhar).
    """
    texto = missao_texto
    m_id = _RE_MISSION.search(texto)
    mission = m_id.group(1) if m_id else "MISSAO-SEM-ID"

    bloco = _extrair_bloco(texto)
    if bloco:
        # Reusa o parser do harness no bloco inline (fonte única de verdade).
        from harness import parse_stop_conditions
        conds = parse_stop_conditions("```harness-stop\n%s```" % bloco)
    else:
        cmd = _derivar_cmd_de_provas(texto)
        if not cmd:
            raise AdaptadorSetupError(
                "contrato %s sem bloco harness-stop e sem prova determinística "
                "em '## Provas' — FAIL honesto no setup (não adivinhar)" % mission)
        # Ancora o cmd no cwd da run (comandos relativos precisam do cd).
        cmd = "cd %s && %s" % (cwd, cmd)
        conds = [{"kind": "cmd", "cmd": cmd}]

    # {{HARNESS_CWD}} → cwd real da run (em qualquer campo das conds).
    for c in conds:
        for k, v in list(c.items()):
            if isinstance(v, str) and "{{HARNESS_CWD}}" in v:
                c[k] = v.replace("{{HARNESS_CWD}}", cwd)

    if budget_usd is None:
        mb = _RE_BUDGET.search(texto)
        budget_usd = float(mb.group(1).replace(",", ".")) if mb else DEFAULT_BUDGET_USD
    if max_turns is None:
        max_turns = DEFAULT_MAX_TURNS

    return {"mission": mission, "cwd": cwd, "budget_usd": budget_usd,
            "max_turns": max_turns, "stop_conditions": conds,
            "contrato_texto": texto}
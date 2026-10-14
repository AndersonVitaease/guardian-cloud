#!/usr/bin/env python3
"""RD-HARN-FATIA-AUTO-02 — fatiador automático de contratos grandes.

Dado um contrato .md (seção ## ENTREGAS com itens numerados), um repo alvo e um
diretório de saída, gera SEM LLM, de forma determinística, uma cadeia serial de
micro-missões (plano.json + um .md por fatia). Cada fatia traz:

- MAPA com símbolos REAIS: candidatos extraídos só de trechos entre crases da
  entrega (camelCase/snake_case/rotas `/api/...`/chamadas `nome(`), filtrados
  contra stopwords, e localizados LITERALMENTE no código do repo
  (`arquivo:LINHA` — símbolo). Candidato sem ocorrência no repo não entra.
- Stops HERDADOS do contrato: cada stop vai para a fatia cuja entrega cita o
  mesmo arquivo/símbolo/prova; stops de relatório/commit ficam na última;
  nenhuma fatia fica só com stops triviais.
"""
import argparse
import json
import os
import re
import sys

CODE_EXT = ('.js', '.mjs', '.py')
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'runs', 'uploads',
             'artifacts', '.venv', 'venv'}
STOP_RE = re.compile(r"```harness-stop(.*?)```", re.S)
CMD_RE = re.compile(r"^cmd\s+(.+)$", re.M)
ENTREGA_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$", re.M)
TICK_RE = re.compile(r"`([^`]+)`")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
CAND_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ROTA_RE = re.compile(r"/[A-Za-z0-9_][\w/*.-]*")
ARQ_CMD_RE = re.compile(r"[\w./-]+\.(?:js|mjs|py)\b")
TRIVIAL_RE = re.compile(r"^\s*(test\s+-[fde]\s+\S+|true|:|ls\b.*|echo\b.*)\s*$")
ULTIMA_RE = re.compile(r"RELATORIO|git\s+log|git\s+diff")

# palavras genéricas de código e stopwords PT/EN: nunca são símbolo de mapa
GENERICOS = {'ausente', 'body', 'req', 'res', 'const', 'function', 'true',
             'false', 'null', 'undefined', 'var', 'let', 'return', 'async',
             'await', 'import', 'export', 'require', 'module', 'exports'}
STOPWORDS = GENERICOS | {
    'missão', 'missao', 'entregas', 'regras', 'mapa', 'relatorio', 'commit',
    'commite', 'verdade', 'veredito', 'honesto', 'novo', 'padrão', 'padrao',
    'ajuste', 'aplicado', 'início', 'inicio', 'assunto', 'arquivo', 'linha',
    'coluna', 'raiz', 'porta', 'livre', 'temporário', 'temporario', 'prova',
    'provas', 'signup', 'post', 'bucket', 'burst', 'refill', 'handler',
    'header', 'migração', 'migracao', 'idempotente', 'checkbox', 'envio',
    'persistir', 'timestamp', 'aceito', 'termos', 'usuário', 'usuario',
    'devolve', 'esgotado', 'rotas', 'test', 'tests', 'python', 'node',
}


class SemEntregas(ValueError):
    """Contrato sem seção ## ENTREGAS com itens numerados."""


def id_do_contrato(texto):
    m = re.search(r"#\s*MISS[AÃ]O\s+([A-Za-z0-9-]+)", texto)
    return m.group(1) if m else "CONTRATO"


def secao(texto, titulo):
    m = re.search(r"^##\s+%s\s*$(.*?)(?=^##\s|\Z)" % re.escape(titulo),
                  texto, re.M | re.S)
    return m.group(1) if m else ""


def parse_entregas(texto):
    """[(num, texto)] da seção ## ENTREGAS, em ordem."""
    corpo = secao(texto, 'ENTREGAS')
    itens = [(int(n), t.strip()) for n, t in ENTREGA_RE.findall(corpo)]
    if not itens:
        raise SemEntregas(
            "contrato sem ## ENTREGAS com itens numerados (1., 2., ...)")
    return itens


def parse_stops(texto):
    """[cmd] do bloco ```harness-stop```, verbatim."""
    cmds = []
    for bloco in STOP_RE.findall(texto):
        cmds.extend(c.strip() for c in CMD_RE.findall(bloco))
    return cmds


def listar_codigo(repo):
    """Caminhos relativos dos arquivos de código do repo (determinístico)."""
    saida = []
    for raiz, dirs, files in os.walk(repo):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            if f.endswith(CODE_EXT):
                saida.append(os.path.relpath(os.path.join(raiz, f), repo))
    return sorted(saida)


def ler(repo, rel):
    with open(os.path.join(repo, rel), encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _camel(w):
    return any(a.islower() and b.isupper() for a, b in zip(w, w[1:]))


def candidatos_da_entrega(texto):
    """Símbolos candidatos: só o que está entre crases na entrega.

    Aceita rotas `/api/...`, identificadores camelCase/snake_case e nomes de
    função `nome(`. Descarta stopwords/genéricos (ausente, body, req, ...).
    """
    cands = set()
    for tick in TICK_RE.findall(texto):
        for w in CAND_RE.findall(tick):
            if len(w) < 4 or w.lower() in STOPWORDS:
                continue
            # identificador puro: camelCase, snake_case, ALL_CAPS ou chamada
            # `nome(` — rotas e termos genéricos nunca entram.
            if w.isupper():
                # ALL_CAPS só se a crase cita a constante em si (com ou sem chamada)
                if tick == w or tick.startswith(w + '('):
                    cands.add(w)
                continue
            if '_' in w or _camel(w) or \
                    re.search(re.escape(w) + r'\s*\(', tick):
                cands.add(w)
    return sorted(cands)


COMENT_LINHA_RE = re.compile(r'^\s*(#|//|\*|/\*|"""|\'\'\')')


def eh_definicao(linha, nome):
    """Linha define `nome` (function/const/def/export) em vez de só usar."""
    esc = re.escape(nome)
    if re.search(r'\b(?:async\s+)?function\s+' + esc + r'\b', linha):
        return True
    if re.search(r'\bconst\s+' + esc + r'\s*=', linha):
        return True
    if re.search(r'\bdef\s+' + esc + r'\b', linha):
        return True
    if 'export' in linha and re.search(esc + r'\s*\(', linha):
        return True
    return False


def tokens_da_entrega(texto):
    """Tokens amplos (para escolher arquivos da fatia, não para o mapa)."""
    toks = set()
    for t in TICK_RE.findall(texto):
        for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{3,}", t):
            toks.add(w)
    for w in IDENT_RE.findall(texto):
        if w.lower() not in STOPWORDS:
            toks.add(w)
    return sorted(toks)


def localizar(repo, arquivos, cands):
    """[(rel, linha, simbolo)] — 1ª linha de cada arquivo com símbolo literal.

    Candidato sem ocorrência no repo simplesmente não entra.
    """
    out = []
    for rel in arquivos:
        try:
            linhas = ler(repo, rel).splitlines()
        except OSError:
            continue
        for c in cands:
            melhor = None
            for i, linha in enumerate(linhas, 1):
                if c not in linha or COMENT_LINHA_RE.match(linha):
                    continue
                if eh_definicao(linha, c):
                    melhor = (rel, i, c)
                    break
                if melhor is None:
                    melhor = (rel, i, c)
            if melhor:
                out.append(melhor)
    return out


def arquivos_da_entrega(ent_texto, repo, codigos, max_arquivos):
    """Top max_arquivos arquivos do repo que citam os símbolos da entrega."""
    toks = tokens_da_entrega(ent_texto)
    pontuacao = {}
    for rel in codigos:
        conteudo = ler(repo, rel)
        pts = sum(1 for t in toks if t in conteudo)
        if pts:
            pontuacao[rel] = pts
    ordenados = sorted(pontuacao, key=lambda r: (-pontuacao[r], r))
    return ordenados[:max_arquivos]


def arquivos_do_cmd(cmd, codigos):
    """Arquivos de código citados textualmente no cmd."""
    return sorted(c for c in codigos
                  if re.search(r'(?<![\w./-])' + re.escape(c) + r'(?![\w./-])',
                               cmd))


def refs_do_cmd(cmd, codigos):
    """(strings citadas, arquivos citados) no cmd, p/ casar com a entrega."""
    citadas = []
    for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", cmd):
        citadas.append(a or b)
    arqs = set(arquivos_do_cmd(cmd, codigos))
    arqs |= set(ARQ_CMD_RE.findall(cmd))
    return [c for c in citadas if c], sorted(arqs)


def stop_especifico(repo, mapa, codigos):
    """Stop não-trivial de reserva: check/grep do arquivo-símbolo do mapa."""
    if mapa:
        rel, _, sym = mapa[0]
        if rel.endswith(('.js', '.mjs')):
            return 'cd %s && node --check %s' % (repo, rel)
        if rel.endswith('.py'):
            return 'cd %s && python3 -m py_compile %s' % (repo, rel)
        return "cd %s && grep -q -F '%s' %s" % (repo, sym, rel)
    if codigos:
        return 'cd %s && node --check %s' % (repo, codigos[0])
    return 'cd %s && true' % repo


def fatiar(contrato, repo, outdir, max_arquivos=2):
    with open(contrato, encoding='utf-8') as fh:
        texto = fh.read()
    entregas = parse_entregas(texto)
    cid = id_do_contrato(texto)
    stops = parse_stops(texto)
    codigos = listar_codigo(repo)

    # 1) arquivos por entrega (limitado a max_arquivos)
    por_entrega = {n: arquivos_da_entrega(t, repo, codigos, max_arquivos)
                   for n, t in entregas}

    # 2) agrupamento guloso serial: junta entregas consecutivas cujos
    #    arquivos cabem no mesmo conjunto de tamanho <= max_arquivos.
    #    Entrega sem termos citados entre crases (ex.: so relatorio/commit)
    #    nao gera ancoras proprias: herda a fatia anterior em vez de ganhar
    #    um mapa irrelevante com simbolos de outras entregas.
    cands_por_entrega = {n: candidatos_da_entrega(t) for n, t in entregas}
    grupos = []  # [(nums_entrega, arquivos, cands_do_grupo)]
    for n, t in entregas:
        arqs = por_entrega[n]
        cands = set(cands_por_entrega[n])
        # junta se os arquivos cabem E os termos da entrega nao trazem
        # ancoras novas (evita mapa irrelevante e preserva >=3 fatias
        # quando cada entrega cita simbolos proprios); entrega sem
        # termos citados entre crases (ex.: so relatorio/commit) herda
        # a fatia anterior em vez de ganhar ancoras de outras entregas.
        if grupos and (not cands or (set(arqs) <= set(grupos[-1][1])
                                     and cands <= grupos[-1][2])):
            grupos[-1][0].append(n)
            grupos[-1] = (grupos[-1][0], grupos[-1][1],
                          grupos[-1][2] | cands)
        else:
            grupos.append(([n], arqs, set(cands)))
    fatias = []
    for i, (nums, arqs, _c) in enumerate(grupos):
        fatias.append({'id': '%s-S%d' % (cid, i + 1),
                       'arquivo': '%s-S%d.md' % (cid, i + 1),
                       'deps': [] if i == 0 else [fatias[i - 1]['id']],
                       'entrega': nums[0],
                       'arquivos': arqs,
                       '_nums': nums})

    # 3) mapa de símbolos reais por fatia (localizados no repo)
    cands_globais = sorted(set().union(*cands_por_entrega.values())) \
        if cands_por_entrega else []
    for f in fatias:
        proprios = sorted(set().union(*[cands_por_entrega[n]
                                        for n in f['_nums']]))
        mapa = localizar(repo, f['arquivos'], proprios)
        if not mapa:  # entrega nova: usa símbolos globais nos mesmos arquivos
            mapa = localizar(repo, f['arquivos'], cands_globais)
        if not mapa:  # fatia sem código próprio (ex.: só relatório)
            mapa = localizar(repo, codigos, cands_globais)[:1]
        f['_mapa'] = mapa

    # 4) distribuição dos stops do contrato: cada stop vai para a fatia cuja
    #    entrega cita o mesmo arquivo/símbolo/prova; relatório/commit e stops
    #    sem dono ficam para a última.
    textos = {i: '\n'.join(t for n, t in entregas if n in f['_nums'])
              for i, f in enumerate(fatias)}
    for cmd in stops:
        if ULTIMA_RE.search(cmd):
            fatias[-1].setdefault('_stops', []).append(cmd)
            continue
        citadas, arqs_cmd = refs_do_cmd(cmd, codigos)
        melhor, pontos = None, 0
        for i, f in enumerate(fatias):
            txt = textos[i]
            pts = 0
            for q in citadas:
                if q in txt:
                    pts += 2
            for fn in arqs_cmd:
                if fn in txt or fn.rsplit('.', 1)[0] in txt:
                    pts += 1
                if fn in f['arquivos']:
                    pts += 1
            if pts > pontos:
                melhor, pontos = f, pts
        (melhor if melhor is not None else fatias[-1]) \
            .setdefault('_stops', []).append(cmd)

    # 5) nenhuma fatia só com stop trivial: acrescenta stop específico
    for f in fatias:
        sts = f.setdefault('_stops', [])
        if not sts or all(TRIVIAL_RE.match(s) for s in sts):
            sts.append(stop_especifico(repo, f['_mapa'], codigos))

    # 6) escreve saída
    os.makedirs(outdir, exist_ok=True)
    plano = {'contrato': contrato, 'fatias': []}
    total = len(fatias)
    for idx, f in enumerate(fatias):
        corpo_entregas = '\n'.join('%d. %s' % (n, t)
                                   for n, t in entregas if n in f['_nums'])
        mapa_txt = '\n'.join('- `%s:%d` — símbolo `%s`' % (r, l, s)
                             for r, l, s in f['_mapa'])
        stops_txt = '\n'.join('cmd ' + c for c in f['_stops'])
        md = ('# MISSÃO %s\n\n'
              'Fatia %d de %d do contrato %s (entrega(s) %s). Repo: %s.\n'
              'Deps: %s.\n\n'
              '## MAPA\n%s\n\n'
              '## ENTREGAS\n%s\n\n'
              '## REGRAS\n'
              '- Commite cedo e a cada entrega verde; NUNCA git reset/checkout/stash/clean.\n'
              '- Assunto do commit deve conter `%s`.\n\n'
              '```harness-stop\n%s\n```\n') % (
            f['id'], idx + 1, total, cid,
            ', '.join(str(n) for n in f['_nums']), repo,
            ', '.join(f['deps']) or 'nenhuma', mapa_txt, corpo_entregas,
            f['id'], stops_txt)
        with open(os.path.join(outdir, f['arquivo']), 'w',
                  encoding='utf-8') as fh:
            fh.write(md)
        plano['fatias'].append({'id': f['id'], 'arquivo': f['arquivo'],
                                'deps': f['deps'], 'entrega': f['entrega'],
                                'arquivos': f['arquivos'],
                                '_nums': f['_nums']})
    with open(os.path.join(outdir, 'plano.json'), 'w', encoding='utf-8') as fh:
        json.dump(plano, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    return plano


def main(argv=None):
    ap = argparse.ArgumentParser(description='Fatiador automático de contrato')
    ap.add_argument('contrato')
    ap.add_argument('repo')
    ap.add_argument('outdir')
    ap.add_argument('--max-arquivos', type=int, default=2)
    args = ap.parse_args(argv)
    try:
        plano = fatiar(args.contrato, args.repo, args.outdir,
                       max_arquivos=args.max_arquivos)
    except SemEntregas as e:
        print('ERRO: %s' % e, file=sys.stderr)
        return 2
    print('OK: %d fatias em %s' % (len(plano['fatias']), args.outdir))
    return 0


if __name__ == '__main__':
    sys.exit(main())
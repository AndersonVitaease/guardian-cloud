#!/usr/bin/env python3
"""RD-HARN-FATIA-AUTO-01 — fatiador automático de contratos grandes.

Dado um contrato .md (seção ## ENTREGAS com itens numerados), um repo alvo e um
diretório de saída, gera SEM LLM, de forma determinística, uma cadeia serial de
micro-missões (plano.json + um .md por fatia), cada uma com mapa de linhas
real (arquivo:LINHA extraído por busca no código do repo).
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
STOPWORDS = {'MISSÃO', 'MISSAO', 'ENTREGAS', 'REGRAS', 'MAPA', 'RELATORIO',
             'commit', 'commite', 'verdade', 'veredito', 'honesto', 'novo',
             'padrão', 'padrao', 'ajuste', 'aplicado', 'início', 'inicio'}


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


def tokens_da_entrega(texto):
    toks = set()
    for t in TICK_RE.findall(texto):
        for w in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]{3,}", t):
            toks.add(w)
    for w in IDENT_RE.findall(texto):
        if w not in STOPWORDS:
            toks.add(w)
    return sorted(toks)


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


def linha_do_simbolo(repo, rel, toks):
    """Primeira linha de `rel` que contém algum símbolo; 1 se nenhum."""
    for i, linha in enumerate(ler(repo, rel).splitlines(), 1):
        for t in toks:
            if t in linha:
                return i, t
    return 1, (toks[0] if toks else rel)


def arquivos_do_cmd(cmd, codigos):
    """Arquivos de código citados textualmente no cmd."""
    return sorted(c for c in codigos if re.search(r'(?<![\w./-])' + re.escape(c) + r'(?![\w./-])', cmd))


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
    #    arquivos cabem no mesmo conjunto de tamanho <= max_arquivos
    grupos = []  # [(nums_entrega, arquivos)]
    for n, t in entregas:
        arqs = por_entrega[n]
        if grupos and set(arqs) <= set(grupos[-1][1]):
            grupos[-1][0].append(n)
        else:
            grupos.append(([n], arqs))
    fatias = []
    for i, (nums, arqs) in enumerate(grupos):
        fatias.append({'id': '%s-S%d' % (cid, i + 1),
                       'arquivo': '%s-S%d.md' % (cid, i + 1),
                       'deps': [] if i == 0 else [fatias[i - 1]['id']],
                       'entrega': nums[0],
                       'arquivos': arqs,
                       '_nums': nums})

    # 3) distribuição dos stops: cmd vai para a 1ª fatia que cobre seus
    #    arquivos; cmds sem arquivos de código conhecidos ficam pra última.
    pendentes = []
    for cmd in stops:
        alvo = None
        for f in fatias:
            if arquivos_do_cmd(cmd, codigos) and \
               set(arquivos_do_cmd(cmd, codigos)) <= set(f['arquivos']):
                alvo = f
                break
        if alvo is not None:
            alvo.setdefault('_stops', []).append(cmd)
        else:
            pendentes.append(cmd)
    fatias[-1].setdefault('_stops', []).extend(pendentes)

    # 4) escreve saída
    os.makedirs(outdir, exist_ok=True)
    plano = {'contrato': contrato, 'fatias': []}
    total = len(fatias)
    for f in fatias:
        toks = sorted(set().union(*[tokens_da_entrega(t)
                                    for n, t in entregas if n in f['_nums']]))
        mapa = []
        for rel in f['arquivos']:
            linha, sym = linha_do_simbolo(repo, rel, toks)
            mapa.append((rel, linha, sym))
        if not mapa and codigos:  # fatia sem código (ex.: só relatório)
            rel = codigos[0]
            mapa.append((rel, 1, rel))
        if not f.get('_stops'):
            f['_stops'] = ['cd %s && test -f %s' % (repo, mapa[0][0])]
        corpo_entregas = '\n'.join('%d. %s' % (n, t)
                                   for n, t in entregas if n in f['_nums'])
        mapa_txt = '\n'.join('- `%s:%d` — símbolo `%s`' % (r, l, s)
                             for r, l, s in mapa)
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
            f['id'], fatias.index(f) + 1, total, cid,
            ', '.join(str(n) for n in f['_nums']), repo,
            ', '.join(f['deps']) or 'nenhuma', mapa_txt, corpo_entregas,
            f['id'], stops_txt)
        with open(os.path.join(outdir, f['arquivo']), 'w',
                  encoding='utf-8') as fh:
            fh.write(md)
        plano['fatias'].append({'id': f['id'], 'arquivo': f['arquivo'],
                                'deps': f['deps'], 'entrega': f['entrega'],
                                'arquivos': f['arquivos']})
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
# MISSÃO GB-LANDING-GAC-01

Fonte: ROADMAP.md linha 465.

Objetivo: construir landing de produto automotivo ESTÁTICA (1 página) seguindo EXATAMENTE o DOSSIER.md que está na raiz deste worktree. Leia `DOSSIER.md` inteiro PRIMEIRO (grep -n '^##' DOSSIER.md para o mapa de seções, depois `sed -n` por bloco). Nada de internet, nada de biblioteca externa: HTML+CSS+JS puro.

## REGRAS ANTI-VAGUEIO (cravadas)
- Escreva o código NOS PRIMEIROS TURNOS. Não explore: o design inteiro está descrito no DOSSIER.md — transcreva para código.
- Se um comando falhar 2x: NÃO repita. Rode `pwd` e `grep -n PADRAO arq` para reorientar e adapte.
- Escrever arquivos: use Bash com python3 heredoc (Write do harness é confinado ao run-dir):
  cd /home/worker/wt-GB-LANDING-GAC-01 && python3 - <<'PYEOF'
  open('index.html','w').write('''...CONTEUDO...''')
  PYEOF
- Commit cedo com o ID no assunto: `cd /home/worker/wt-GB-LANDING-GAC-01 && git add index.html DOSSIER.md && git commit -m "GB-LANDING-GAC-01: landing estatica (hero, specs, vitrine carrossel, galerias, form lead, concessionaria, footer)"`.
- PROIBIDO: git reset/checkout/stash/clean; escrever fora do worktree; sudo; cat/head/ls.

## MAPA
Arquivos a criar (novos, raiz do worktree):
- index.html (novo) — página única autocontida: CSS em <style>, JS em <script>. 8 blocos na ordem do DOSSIER.md: 1 hero full-bleed (nav translúcida + CTA + specs + botão rolar), 2 apresentação do modelo com faixa de specs, 3 vitrine de modelos com tabs GS/AION/HYPTEC + carrossel contador 01/02 + setas, 4 galeria exterior com carrossel, 5 galeria interior, 6 formulário de lead em bloco escuro (chips de modelo selecionáveis + NOME/TELEFONE/E-MAIL/CIDADE + botão enviar com confirmação fake), 7 bloco concessionária (endereço + botão como chegar + mapa stub), 8 footer preto com palavra da marca GIGANTE cortada na base.
- Sem arquivos de imagem: fotos = placeholders SVG inline (gradiente + silhueta simples de carro). Todos os <img> com alt.
- IDs nas seções para a prova: id="hero", id="modelos", id="exterior", id="interior", id="lead", id="loja", id="footer".
- Copy: use a copy pronta do DOSSIER.md (seção "Copy pronta").

## PROVA (mecânica)
Crie `prova_landing.py` no worktree (python3 puro, sem dependências) que:
1. roda chromium headless do playwright cache para screenshot:
   /root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome —headless=new --no-sandbox --disable-gpu --screenshot=/home/worker/wt-GB-LANDING-GAC-01/landing.png --window-size=1440,2400 file:///home/worker/wt-GB-LANDING-GAC-01/index.html
   (o chrome binário NÃO está em /root para você — use o caminho do chromium disponível: rode `grep -rl chrome-linux /home/worker/.cache/ms-playwright 2>/dev/null | head -1` OU, se não achar, use `python3 -m http.server` skip: alternativa aceita é validar DOM sem screenshot — ver 2)
2. valida com python3 (html.parser) que index.html contém as 7 ids acima, os chips de modelo (6), os 4 inputs do formulário e o texto "Falar com um consultor";
3. se o screenshot foi gerado e tem >20000 bytes, imprime LANDING-SHOT-OK; sempre imprime no fim o marcador `GB-LANDING-GAC-01-PROVA-OK` com as checagens listadas.

## ENTREGA
- `index.html` commitado no branch rd-gb-landing-gac-01 + `prova_landing.py` commitado + `RELATORIO-GB-LANDING-GAC-01.md` (curto: o que foi feito, como rodar a prova, saída da prova).

```harness-stop
cmd cd /home/worker/wt-GB-LANDING-GAC-01 && test -f index.html
cmd cd /home/worker/wt-GB-LANDING-GAC-01 && grep -q 'id="lead"' index.html
cmd cd /home/worker/wt-GB-LANDING-GAC-01 && python3 prova_landing.py
cmd cd /home/worker/wt-GB-LANDING-GAC-01 && python3 prova_landing.py | grep -q 'GB-LANDING-GAC-01-PROVA-OK'
cmd cd /home/worker/wt-GB-LANDING-GAC-01 && test -f RELATORIO-GB-LANDING-GAC-01.md
cmd cd /home/worker/wt-GB-LANDING-GAC-01 && test "$(git log -1 --format=%s)" = "GB-LANDING-GAC-01: landing estatica (hero, specs, vitrine carrossel, galerias, form lead, concessionaria, footer)"
```

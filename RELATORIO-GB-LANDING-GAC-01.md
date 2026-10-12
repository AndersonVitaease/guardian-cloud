# RELATORIO GB-LANDING-GAC-01

## O que foi feito
- `index.html`: landing automotiva estatica, 1 pagina autocontida (CSS em <style>, JS em <script>), 8 blocos na ordem do DOSSIER.md: hero full-bleed (nav translucida + CTA + specs + botao rolar), apresentacao do modelo com faixa de specs, vitrine com tabs GS/AION/HYPTEC + carrossel contador 01/02 + setas, galeria exterior com carrossel, galeria interior, formulario de lead em bloco escuro (6 chips de modelo + NOME/TELEFONE/E-MAIL/CIDADE + botao enviar com confirmacao fake), bloco concessionaria (endereco + botao como chegar + mapa stub), footer preto com palavra GAC gigante cortada na base.
- Fotos = placeholders SVG inline (gradiente + silhueta de carro), todos os <img> com alt.
- IDs de prova: hero, modelos, exterior, interior, lead, loja, footer.
- `prova_landing.py`: screenshot chromium headless (playwright cache) + validacao DOM com html.parser.

## Como rodar a prova
    cd /home/worker/wt-GB-LANDING-GAC-01 && python3 prova_landing.py

## Saida da prova
    LANDING-SHOT-OK
    PASS ids-7
    PASS chips-6
    PASS inputs-4
    PASS cta-consultor
    PASS screenshot
    GB-LANDING-GAC-01-PROVA-OK

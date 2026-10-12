# RELATORIO GB-LANDING-GAC-01

## O que foi feito
- `index.html`: landing estatica 1 pagina (HTML+CSS+JS puro, sem libs/imagens externas; fotos = SVG inline com gradiente e silhueta de carro, todos os img com alt).
  Blocos na ordem do DOSSIER.md: 1) hero full-bleed com nav translucida, CTA "Falar com um consultor", specs e botao rolar; 2) apresentacao do modelo com faixa de specs; 3) vitrine com tabs GS/AION/HYPTEC e carrossel com contador 01/02 e setas; 4) galeria exterior (carrossel); 5) galeria interior; 6) form de lead em bloco escuro (6 chips de modelo selecionaveis + NOME/TELEFONE/E-MAIL/CIDADE + envio com confirmacao fake); 7) bloco concessionaria (endereco + botao "como chegar" + mapa stub); 8) footer preto com palavra da marca gigante cortada na base.
  IDs de prova: hero, modelos, exterior, interior, lead, loja, footer.

## Como rodar a prova
```
cd /home/worker/wt-GB-LANDING-GAC-01 && python3 prova_landing.py
```
A prova roda chromium headless do cache playwright para screenshot (landing.png, 1440x2400) e valida o DOM com html.parser: 7 ids, 6 chips de modelo, 4 inputs do form e o texto "Falar com um consultor".

## Saida da prova
```
LANDING-SHOT-OK
PASS ids-7
PASS chips-6
PASS inputs-4
PASS cta-consultor
PASS screenshot
GB-LANDING-GAC-01-PROVA-OK
```

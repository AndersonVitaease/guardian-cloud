# DOSSIER DE DESIGN — Landing automotiva estilo GAC (referência: gac2.grupostradarn.com.br)

Origem: operador pediu landing "parecida com essa". Worker NÃO tem internet — tudo que precisa está NESTE arquivo. Não tentar acessar URLs.

## Objetivo
Landing de produto automotivo, 1 página estática (HTML+CSS+JS puro, sem build), PT-BR, dark-elegante onde couber, estilo concessionária premium. Estrutura e fôlego idênticos à referência; conteúdo adaptado para o produto que o operador indicar (default: SUV híbrido fictício).

## Estrutura de cima para baixo (7 blocos)
1. **Hero full-bleed**: foto grande do SUV 3/4 dianteira ao ar livre; barra de navegação fina translúcida (logo à esquerda; links SOBRE, MODELOS, DESTAQUES; CTA à direita "Falar com um consultor"); legenda sobreposta "Novo [MODELO]"; botão circular "Rolar para baixo" no rodapé do hero.
2. **Apresentação do modelo**: tag "LANÇAMENTO [MARCA]"; H2 com nome do modelo; parágrafo de ~3 linhas; faixa de 3–4 specs em colunas (ex.: Potência combinada 235 cv · Porta-malas 638 L · Consumo urbano 14,1 km/l · Motorização 2.0 híbrido); CTA "Falar com um consultor"; foto grande do carro.
3. **Vitrine de modelos**: H2 "Tecnologia e presença em cada [MARCA]"; tabs de família (GS / AION / HYPTEC — ou equivalentes); carrossel com contador "01 / 02" e setas; cada card mostra o carro sobre fundo claro com o nome em letras gigantes translúcidas atrás; sob o card, specs em 4 colunas (Potência, Torque, 0–100, Câmbio).
4. **Galeria exterior**: H2 centralizado em 2 linhas ("Esportivo por fora, sofisticado por dentro"); grid de fotos grandes com mini-carrossel e setas; caption H3 "Design que impõe presença" + parágrafo.
5. **Galeria interior**: mesma gramática invertida (caption à esquerda "Conforto pensado para a rotina", fotos de painel/console/bancos).
6. **Formulário de lead (bloco escuro, fundo navy/quase-preto com foto esmaecida do carro)**: H2 "Escolha o seu [MARCA]"; chips selecionáveis de modelos; inputs NOME, TELEFONE, E-MAIL, CIDADE; botão "Enviar meus dados" com ícone circular.
7. **Concessionária**: foto da fachada; endereço, texto "Visite a concessionária", botão "Como chegar"; iframe de mapa (stub com endereço — não precisa chave).
8. **Footer preto**: logo pequeno; links; palavra da marca GIGANTE cortada na base (efeito de cauda tipográfica).

## Visual / identidade
- Fundos: branco/cinza-claro nos blocos de vitrine; escuro (navy/preto) no form e footer; hero com foto full-bleed.
- Acento: praticamente sem cor — o impacto vem das FOTOS e da tipografia; botões preto sobre claro / branco sobre escuro, pill com seta em círculo.
- Tipografia: sans geométrica, títulos com peso 600–700, tracking levemente fechado; labels de spec em caps pequenas cinza.
- Micro-detalhe: nome do modelo em letras gigantes translúcidas atrás do carro (marque o estilo).
- Espaçamento: seções muito arejadas (~120–160px de respiro), conteúdo em container ~1200px.

## Copy pronta (adaptar nomes)
- Hero: "Novo GS4 Hybrid Elite"; specs: Potência combinada 235 cv / Porta-malas 638 L / Consumo urbano 14,1 km/l / Motorização 2.0 híbrido.
- Apresentação: "O SUV médio híbrido da GAC combina motor 2.0 ciclo Atkinson e motor elétrico, somando 235 cv de potência, com câmbio DHT de duas marchas e bateria de 2,1 kWh que se recarrega sozinha, sem tomada. Na versão Elite, teto panorâmico com cortina elétrica, tampa do porta-malas elétrica e bancos dianteiros ventilados."
- Vitrine: "Tecnologia e presença em cada GAC" / "Conheça os modelos GAC disponíveis na concessionária e encontre o que combina com a sua rotina." Card GS3 Elite: 170 cv / 25,5 kgfm / 8,1 s / WDCT 7 marchas.
- Exterior: "Esportivo por fora, sofisticado por dentro" + "Design que impõe presença" + "No GS4 Hybrid Elite, a grade de lâminas diagonais se une aos faróis full LED, a traseira traz lanternas em LED com assinatura vertical e o aerofólio esculpido completa o perfil cupê."
- Interior: "Conforto pensado para a rotina" + "No GS4 Hybrid Elite, a central multimídia e o painel de instrumentos digital ficam à frente do motorista, com console central em acabamento metálico e bancos revestidos em couro."
- Form: "Escolha o seu GAC" / "Selecione o modelo que você quer conhecer e deixe seu contato. Um consultor da concessionária recebe seus dados e entra em contato com você." / chips: GS4 Hybrid Elite, GS3 Elite, AION UT, AION V, AION Y, HYPTEC HT.
- Concessionária: "Visite a concessionária" / Av. Industrial Dehuel Vieira Diniz, 1260 - Santo Antônio, Mossoró - RN, 59615-255 / "Como chegar".

## Fotos — NÃO copiar da referência
Sem internet: use placeholders gerados (SVG/CSS gradientes com silhueta, ou imagens de banco local se houver). Todos os `<img>` com alt descritivo. O operador troca as fotos reais depois.

## Formulário
Front-end completo com validação; submit = stub que exibe confirmação (não enviar a lugar algum).

## Entrega esperada
`index.html` + `styles.css` + `script.js` (ou single-file, se preferir), rodando ao abrir no navegador. Prova: render local sem erros de console.
# MISSÃO FOTO-ESTUDIO-01 — agente fotoestudio.sh: fala → edição de foto (embrulho do img_tools.sh)

Fonte: ordem do operator 12/10 (autorizada, equivalente ao videoestudio para fotos).
Repo: /home/worker/harness-s2. NUNCA /opt ou /root. O motor é a tool governada
/opt/mission-events/tools-bash/img_tools.sh (ops hoje: resize W H IN OUT | webp |
thumb) — worker a EXECUTA, nunca a edita. Se a frase pedir op que img_tools não tem
(crop/rotate/cortar bordas), usar ImageMagick (convert/mogrify) direto no script —
binário do sistema, custo zero.

## Entrega 1 — scripts/fotoestudio.sh (bash puro)

Uso: fotoestudio.sh "FRASE" IN OUT [OUT2...]. Sem frase/IN/OUT →
{"ok":false,"error":"ARGS_AUSENTES"}. Validar IN existe e é imagem
(identificar via file/magic: png|jpeg|webp) — senão {"ok":false,"error":"IN_INVALIDO"}.
1. T0; ev(){ trilha JSONL runs/fotoestudio/fotoestudio-trail.jsonl {t,ms,step,ok,data}; }
2. PLANO (1 chamada glm, trava dura): curl OpenRouter (key .env do worker 600,
   model z-ai/glm-5.3-flash, max_tokens 300, temp 0). Sistema: "Converta a frase
   em UMA lista JSON de operações de edição de imagem usando APENAS: resize WxH,
   crop LxT WxH (recorte), rotate GRAUS, flip h|v, webp, thumb. Caminhos: só os
   fornecidos; primeiro comando lê IN e escreve OUT (intermediário tmp se >1 op).
   NÃO invente operações fora dessa lista." User: FRASE + dimensões reais de IN
   (identify) + OUT. Não-parseável → {"ok":false,"error":"FE_GLM_INUTIL"}.
3. EXECUTAR em ordem (tmp entre ops): img_tools.sh para resize/webp/thumb;
   convert para crop/rotate/flip. Falha → {"ok":false,"error":"FE_OP_FALHOU:<op>"}.
4. PROVA: OUT existe, >0 bytes e identifica como imagem válida; senão
   {"ok":false,"error":"FE_OUT_INVALIDO"}.
5. SAÍDA: última linha JSON {"ok":true,"mudanca":"...","out":"OUT","dim":"WxH","ms":N}
   (ou ok:false + error tipado). TODO caminho emite JSON (trap ERR; set -u com
   ${VAR:-}; nunca morre calado). Escreve SÓ em OUT/tmp. Sem commit de imagens.

## Entrega 2 — prova prova-fotoestudio.sh

1. Gerar PNG de teste 800x600 (convert xc:blue -resize ou ffmpeg frame) tmp/foto.png.
2. fotoestudio.sh "redimensiona para 400x300 e corta uma faixa de 50px do topo"
   tmp/foto.png tmp/final.png → ok:true; identify final.png = 400x250 (±2px).
3. fotoestudio.sh "gira 90 graus e converte para webp" tmp/final.png tmp/girado.webp
   → ok:true; file girado.webp contém WebP; dimensões trocadas (250x400).
4. Última linha: `RESUMO: X falhas` com X=0.

## Stops (harness-stop)

```harness-stop
cmd cd /home/worker/harness-s2 && bash -n scripts/fotoestudio.sh
cmd cd /home/worker/harness-s2 && bash prova-fotoestudio.sh 2>&1 | tail -1 | grep -q 'RESUMO: 0 falhas'
cmd cd /home/worker/harness-s2 && git log -1 --format=%s | grep -q 'FOTO-ESTUDIO-01'
```

## Commit

UM commit: scripts/fotoestudio.sh + prova-fotoestudio.sh + missao-FOTO-ESTUDIO-01.md,
subject exato: "FOTO-ESTUDIO-01: fotoestudio.sh fala para edicao de foto (prova 0 falhas)".
Budget: 0.20 USD · 14 turnos. Sem git reset/checkout/stash.

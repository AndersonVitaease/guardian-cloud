# PIPELINE-VIDEO-ffmpeg — render pronto de fábrica (degrau 1 de RD-MOTOR-VIDEO-01)

Motor: ffmpeg do sistema (6.1.1) + ffprobe. Tudo determinístico, US$0.

## Render de teste (barra colorida 5s, H.264 mp4)
ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=30 -t 5 -c:v libx264 -pix_fmt yuv420p out.mp4

## Validação
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,duration -of csv=p=0 out.mp4
# esperado: h264,1280,720,5.0

## Pipeline de cena (imagem + áudio -> vídeo)
ffmpeg -y -loop 1 -i cena.png -i narracao.mp3 -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac cena.mp4

## GIF a partir de vídeo
ffmpeg -y -i cena.mp4 -vf "fps=12,scale=640:-1:flags=lanczos" cena.gif

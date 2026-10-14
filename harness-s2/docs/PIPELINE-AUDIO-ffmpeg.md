# PIPELINE-AUDIO-ffmpeg.md (motor de audio — degrau US$0)

## fala (TTS local, sem custo)
espeak-ng -v pt-br -s 140 "texto" -w saida.wav

## conversao
ffmpeg -i saida.wav -codec:a libmp3lame -qscale:a 4 saida.mp3     # mp3
ffmpeg -i saida.wav -c:a libopus -b:a 96k saida.opus              # opus (voz)

## validacao
ffprobe -v error -show_entries stream=codec_name -of csv=p=0 saida.mp3

## mix com video
ffmpeg -i video.mp4 -i voz.wav -shortest -c:v copy -c:a aac final.mp4

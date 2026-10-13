#!/usr/bin/env python3
"""Mede a janela da pessoa na tela dividida: o `y` do topo do recorte 1080×964 que vai pra metade de baixo.

uso:
  python3 ferramentas/medir_janela.py DeVFJ2Ei65T             # folha com régua: escolha o y no olho
  python3 ferramentas/medir_janela.py DeVFJ2Ei65T --y 300     # folha já recortada pra conferir
  python3 ferramentas/medir_janela.py DeVFJ2Ei65T --y 300 --gravar   # grava em planos/_dividida_y.json

Como escolher o y: o rosto inteiro dentro da janela o vídeo todo, topo da cabeça logo abaixo da borda de cima
(20–70 px de folga; cortar um pouco de cabelo pode, testa não) e, se der, a legenda queimada do Reel original
fora da janela (a gente põe uma legenda nova). Mão cortada embaixo não importa. Sem medição, o plano usa
DIVIDIDA_Y_PADRAO do config.env.
"""
import argparse, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ANA_H = 964
N = 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('shortcode')
    ap.add_argument('--y', type=int)
    ap.add_argument('--gravar', action='store_true')
    a = ap.parse_args()
    pasta = os.path.join(config.REELS_BASE, 'videos')
    arq = next((os.path.join(pasta, f) for f in sorted(os.listdir(pasta))
                if f.endswith(f'_{a.shortcode}.mp4') and not f.startswith('._')), None)
    if not arq:
        raise SystemExit(f'{a.shortcode}: vídeo não encontrado em {pasta}')
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                               capture_output=True, text=True).stdout)
    quadros = []
    for i in range(N):
        t = dur * (i + 0.5) / N
        raw = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-ss', f'{t:.2f}', '-i', arq, '-frames:v', '1',
                              '-vf', 'scale=1080:1920', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True).stdout
        quadros.append(Image.frombytes('RGB', (1080, 1920), raw))
    if a.y is None:                                  # régua a cada 100 px
        from PIL import ImageFont
        f = ImageFont.truetype(config.FONTE_NATIVA, 64)
        mini = []
        for q in quadros:
            d = ImageDraw.Draw(q)
            for y in range(100, 1920, 100):
                d.line((0, y, 1080, y), fill=(255, 0, 0), width=6 if y % 200 == 0 else 2)
                if y % 200 == 0:
                    d.text((14, y - 70), str(y), font=f, fill=(255, 255, 0), stroke_width=4, stroke_fill=(0, 0, 0))
            mini.append(q.resize((270, 480)))
    else:
        if not 0 <= a.y <= 1920 - ANA_H:
            raise SystemExit(f'y precisa ficar entre 0 e {1920 - ANA_H}')
        mini = [q.crop((0, a.y, 1080, a.y + ANA_H)).resize((270, 241)) for q in quadros]
    folha = Image.new('RGB', (270 * N, mini[0].height), (0, 0, 0))
    for i, m in enumerate(mini):
        folha.paste(m, (i * 270, 0))
    destino = os.path.join(config.PROJETO, 'planos', '_janelas')
    os.makedirs(destino, exist_ok=True)
    nome = os.path.join(destino, f'{a.shortcode}' + (f'_y{a.y}' if a.y is not None else '_regua') + '.jpg')
    folha.save(nome, quality=88)
    print('folha:', nome)
    if a.gravar and a.y is not None:
        p = os.path.join(config.PROJETO, 'planos', '_dividida_y.json')
        ys = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
        ys[a.shortcode] = {'y': a.y, 'obs': 'medido com ferramentas/medir_janela.py'}
        json.dump(ys, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('gravado em', p)


if __name__ == '__main__':
    main()

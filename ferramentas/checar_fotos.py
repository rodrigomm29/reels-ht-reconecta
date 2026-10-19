#!/usr/bin/env python3
"""REGRA DE ANÚNCIO (Rodrigo, 18–19/10/2026): em vídeo para ANÚNCIO, foto de antes, de depois ou de antes/depois
não passa de 2,5 s na tela (o Meta barra). No orgânico não há limite. Este script acha FOTO PARADA em vídeo: trechos em que a imagem não se mexe, fora a faixa da
legenda (que muda por cima da foto e engana o freezedetect do ffmpeg).

Mede a diferença entre quadros (8 por segundo, 144×256 em cinza) com a faixa da legenda (y 900–1450) e a
borda de baixo apagadas. Pessoa falando sempre mexe (boca, mão, respiração); foto não.

uso:
  python3 ferramentas/checar_fotos.py <vídeo> [<vídeo> ...]          # lista os trechos parados ≥ 1 s
  python3 ferramentas/checar_fotos.py --limite 2.5 saida/SEM43/segunda/orgânico/*.mp4
Saída: um trecho por linha; "PASSOU" quando passa do limite. Sai com código 1 se algum vídeo passou.

Também serve como função: `trechos_parados(video)` → [(início, fim)].
Limites conhecidos: foto PEQUENA sobre o vídeo (janela/inserto) e foto com zoom lento (efeito Ken Burns) não
são pegas, porque o quadro mexe.
Isso fica na conferência visual (tiras) e na regra dos agentes.
"""
import argparse, subprocess, sys

import numpy as np

FPS = 8
W, H = 144, 256
MASCARA = (int(900 / 1920 * H), int(1450 / 1920 * H))     # faixa da legenda (onde quer que ela esteja)
LIMIAR = 0.25          # diferença média (0–255): foto parada dá 0,003–0,08; ela falando, mesmo de tripé
                       # em plano aberto, dá 0,5 ou mais (medido em 18/10/2026)
MIN_PARADO = 1.0       # s mínimos pra listar


def trechos_parados(video, min_parado=MIN_PARADO):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', video, '-vf', f'fps={FPS},scale={W}:{H},format=gray',
                        '-f', 'rawvideo', '-'], capture_output=True).stdout
    q = np.frombuffer(r, dtype=np.uint8).reshape(-1, H, W).astype(np.int16)
    if len(q) < 2:
        return []
    q[:, MASCARA[0]:MASCARA[1], :] = 0
    q[:, int(H * 0.88):, :] = 0                       # interface do Instagram / logo no rodapé
    dif = np.abs(np.diff(q, axis=0)).mean(axis=(1, 2))
    parado = dif < LIMIAR
    out, ini = [], None
    for i, p in enumerate(list(parado) + [False]):
        if p and ini is None:
            ini = i
        elif not p and ini is not None:
            a, b = ini / FPS, (i + 1) / FPS
            if b - a >= min_parado:
                out.append((round(a, 2), round(b, 2)))
            ini = None
    # junta trechos separados por um tropeço de 1 quadro (troca de legenda que vaza da máscara)
    juntos = []
    for a, b in out:
        if juntos and a - juntos[-1][1] <= 0.3:
            juntos[-1] = (juntos[-1][0], b)
        else:
            juntos.append((a, b))
    return juntos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('videos', nargs='+')
    ap.add_argument('--limite', type=float, default=2.5)
    a = ap.parse_args()
    ruim = 0
    for v in a.videos:
        tr = trechos_parados(v)
        piores = [(x, y) for x, y in tr if y - x > a.limite]
        ruim += bool(piores)
        nome = v.rsplit('/', 1)[-1]
        if not tr:
            print(f'ok       {nome}')
            continue
        print(f"{'PASSOU' if piores else 'ok    '}   {nome}: " +
              ', '.join(f"{x:.1f}–{y:.1f} ({y - x:.1f} s){' ←' if y - x > a.limite else ''}" for x, y in tr))
    sys.exit(1 if ruim else 0)


if __name__ == '__main__':
    main()

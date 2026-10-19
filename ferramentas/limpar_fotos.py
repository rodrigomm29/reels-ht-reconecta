#!/usr/bin/env python3
"""REGRA DE ANÚNCIO: foto de antes, de depois ou de antes/depois no máximo 2,5 s na tela (o Meta barra em anúncio;
no orgânico não há limite). Use este script só para gerar a versão de ANÚNCIO de um Reel.

Gera uma cópia LIMPA de um Reel de origem que já foi publicado com foto parada por mais tempo: cada foto fica só
os primeiros FOTO_FICA s e o resto é coberto por um fundo dela mesma (um trecho do próprio Reel sem foto, em
movimento, bem desfocado e escurecido), com a legenda palavra por palavra no meio da tela. O ÁUDIO NÃO MUDA:
mesma duração, mesma fala, mesma transcrição, então os ganchos e cortes do plano continuam valendo.

Os trechos de foto (início e fim de cada foto, aparições seguidas juntas numa janela só) são marcados no olho,
conferidos pela troca de cena, e ficam em `planos/_fotos.json` ({shortcode: [[início, fim], ...]}).
O ferramentas/checar_fotos.py ajuda a achar, mas não pega foto em janela nem com zoom lento.

Saída: `dados/videos/<data>_<sc>F.mp4` + `dados/transcricoes/<data>_<sc>F.json` (cópia). No plano/rascunho, use
o shortcode `<sc>F`. O original nunca é alterado.

uso: python3 ferramentas/limpar_fotos.py DbvnjRxuefz [DajCq0guecP ...]
"""
import glob, json, os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
import config  # noqa: E402
from montar_ht_peles import camada_legenda, ff, filtro_caminho, LEGENDA_H  # noqa: E402

FOTO_FICA = 2.4            # s de foto que ficam (margem sob os 2,5 s)
FPS = 30
LEGENDA_Y = 860 - LEGENDA_H   # texto em ~y 860–940: meio da tela, sobre o fundo desfocado
CACHE = os.path.join(AQUI, 'planos', '_fotos.json')


def duracao(arq):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                                capture_output=True, text=True).stdout)


def limpar(sc, fotos):
    video = glob.glob(os.path.join(config.REELS_BASE, 'videos', f'*_{sc}.mp4'))[0]
    tr = video.replace('/videos/', '/transcricoes/').replace('.mp4', '.json')
    total = duracao(video)
    cobrir = [(a + FOTO_FICA, b) for a, b in fotos if b - a > 2.5]
    saida = video.replace(f'_{sc}.mp4', f'_{sc}F.mp4')
    if not cobrir:
        print(f'{sc}: nenhuma foto acima de 2,5 s; nada a cobrir')
        return
    # fundo: o trecho mais longo do Reel sem foto (ela falando), desfocado; repete se for curto
    livres, t = [], 0.0
    for a, b in sorted(fotos):
        livres.append((t, a))
        t = b
    livres.append((t, total))
    ini_f, fim_f = max(livres, key=lambda x: x[1] - x[0])
    tmp = os.path.join(config.REELS_BASE, 'brutos', '_tmp', f'{sc}F')
    os.makedirs(tmp, exist_ok=True)
    words = [w for w in json.load(open(tr, encoding='utf-8'))['words'] if w.get('type') == 'word']
    pals = [(w['start'], w['end'], w['text'].strip()) for w in words
            if any(a - 0.05 <= w['start'] < b for a, b in cobrir)]
    lista = camada_legenda(pals, total, FPS, os.path.join(tmp, 'legenda'))
    legenda = os.path.join(tmp, 'legenda', 'legenda.mov')
    ff(['-f', 'concat', '-safe', '0', '-i', lista, '-t', f'{total:.3f}', '-vf', f'fps={FPS},format=argb',
        '-c:v', 'qtrle', legenda])
    janela = '+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in cobrir)
    f = [f"[1:v]boxblur=40:2,eq=brightness=-0.10:saturation=0.8,"
         f"trim=duration={total:.3f},setpts=PTS-STARTPTS[fundo]",
         f"[0:v]fps={FPS},scale=1080:1920,setsar=1[base]",
         f"[base][fundo]overlay=0:0:enable='{janela}'[cob]",
         f"movie={filtro_caminho(legenda)},fps={FPS},format=rgba,setpts=PTS-STARTPTS[lg]",
         f"[cob][lg]overlay=0:{LEGENDA_Y}:eof_action=pass:format=auto,format=yuv420p[v]"]
    fundo = os.path.join(tmp, 'fundo.mp4')          # o trecho sem foto vira um clipe que repete em loop
    ff(['-ss', f'{ini_f + 0.2:.3f}', '-t', f'{max(0.5, fim_f - ini_f - 0.4):.3f}', '-i', video, '-an',
        '-vf', f'fps={FPS},scale=1080:1920,setsar=1', '-c:v', 'libx264', '-crf', '20', fundo])
    ff(['-i', video, '-stream_loop', '-1', '-i', fundo, '-filter_complex', ';'.join(f), '-map', '[v]', '-map', '0:a', '-t', f'{total:.3f}',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS),
        '-c:a', 'copy', '-movflags', '+faststart', saida])
    shutil.copyfile(tr, tr.replace(f'_{sc}.json', f'_{sc}F.json'))
    print(f'{sc} → {os.path.basename(saida)}: coberto ' +
          ', '.join(f'{a:.2f}–{b:.2f} ({b - a:.1f} s)' for a, b in cobrir) + f'; fundo de {ini_f:.1f}–{fim_f:.1f} s')


def main():
    fotos = json.load(open(CACHE, encoding='utf-8'))
    for sc in sys.argv[1:]:
        if sc not in fotos:
            raise SystemExit(f'{sc}: marque as fotos em {CACHE} primeiro')
        limpar(sc, fotos[sc])


if __name__ == '__main__':
    main()

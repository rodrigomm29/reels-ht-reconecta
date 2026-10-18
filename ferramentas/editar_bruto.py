#!/usr/bin/env python3
"""Edita um bruto importado (ferramentas/importar_brutos.py) e gera a VERSÃO SEM GANCHO, que depois entra
no fluxo normal (novo_lote → agentes → plano → render) como se fosse um Reel publicado.

Lê `dados/brutos/<ID>_edicao.json`:
  manter   [[início, fim, "texto"], ...]  trechos do bruto que ficam, na ordem (o resto sai: erro, conversa, pausa).
           início = start da 1ª palavra, fim = end da última; a folga de respiração é posta aqui (FOLGA_*).
  imagens  [{"arquivo", "em", "dur"}]     imagem de apoio (ex.: antes/depois) em tela cheia; "em" no tempo do BRUTO.
           A duração é limitada a IMAGEM_MAX (2,5 s): o Meta barra antes/depois que fica mais de 3 s na tela.

Faz:
  - corta e junta os trechos (cada trecho é uma entrada -ss/-t do mesmo arquivo; nada de split→concat),
    com folga antes/depois (emenda de 0,30 s, o ritmo dela) sem invadir a palavra vizinha;
  - alterna o enquadramento a cada trecho (normal / ZOOM_EMENDA× no rosto): a emenda lê como troca de câmera,
    não como pulo do mesmo quadro;
  - fade de 40 ms no áudio em cada emenda (sem estalo) e loudnorm (-16 LUFS);
  - legenda palavra por palavra (a mesma `camada_legenda` da tela dividida), no terço de baixo;
  - imagem ajustada à largura sobre ela mesma desfocada (sem cortar o antes/depois), entrando e saindo em 0,15 s.
Saída: `dados/videos/<data>_<ID>E.mp4` + transcrição remapeada em `dados/transcricoes/<data>_<ID>E.json`
(o id `<ID>E` é o "shortcode" no resto do fluxo) e uma cópia em `$SAIDA_DIR/brutos/<ID>/sem gancho/`.

uso: python3 ferramentas/editar_bruto.py BR001
"""
import glob, json, os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
import config  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402
from montar_ht_peles import camada_legenda, ff, filtro_caminho, LEGENDA_H  # noqa: E402

IMAGEM_MAX = 2.5          # s: regra do Meta pra antes/depois (< 3 s na tela; 2,5 dá margem)
FOLGA_ANTES, FOLGA_DEPOIS = 0.10, 0.20   # s em volta da fala: a emenda soma 0,30 s, a pausa natural dela entre frases (~0,35)
ZOOM_EMENDA, ZOOM_CY = 1.10, 860         # trechos ímpares: enquadramento mais fechado, centrado no rosto
FADE_AUDIO = 0.04
LEGENDA_Y = 1200          # topo da faixa da legenda (texto em ~1330–1400): abaixo da caixa de título (y≈1130)
FADE_IMG = 0.15
FPS = 30


def png_imagem(origem, saida):
    """Imagem inteira na largura (1080) sobre ela mesma ampliada e desfocada, em 1080×1920."""
    im = Image.open(origem).convert('RGB')
    fundo = im.copy()
    esc = max(1080 / fundo.width, 1920 / fundo.height)
    fundo = fundo.resize((int(fundo.width * esc) + 1, int(fundo.height * esc) + 1), Image.LANCZOS)
    x, y = (fundo.width - 1080) // 2, (fundo.height - 1920) // 2
    fundo = fundo.crop((x, y, x + 1080, y + 1920)).filter(ImageFilter.GaussianBlur(40))
    fundo = Image.blend(fundo, Image.new('RGB', fundo.size, (0, 0, 0)), 0.35)
    frente = im.resize((1080, int(im.height * 1080 / im.width)), Image.LANCZOS)
    if frente.height > 1920:
        frente = im.resize((int(im.width * 1920 / im.height), 1920), Image.LANCZOS)
    fundo.paste(frente, ((1080 - frente.width) // 2, (1920 - frente.height) // 2))
    fundo.save(saida, quality=95)


def com_folga(manter, palavras, dur):
    """Abre cada trecho em volta da fala: FOLGA_ANTES/DEPOIS, sem passar da metade do silêncio até a palavra
    vizinha que ficou de fora (conversa, take errado). O início dado manda quando o Scribe estica a 1ª palavra."""
    novos = []
    for a, b, *resto in manter:
        dentro = [w for w in palavras if a - 0.05 <= w['end'] <= b + 0.05]
        antes = [w for w in palavras if w['end'] < a - 0.05 and w not in dentro]
        depois = [w for w in palavras if w['start'] > b - 0.05]
        ini = max(a - FOLGA_ANTES, 0.0)
        if antes:
            ini = max(ini, (antes[-1]['end'] + a) / 2)
        fim = min(b + FOLGA_DEPOIS, dur)
        if depois:
            prox = depois[0]['start']
            for a2, b2, *_ in manter:              # palavra de outro trecho: vale o início marcado dele
                if a2 - 0.05 <= depois[0]['end'] <= b2 + 0.05:
                    prox = max(prox, a2)
            fim = min(fim, (b + prox) / 2)
        novos.append([round(ini, 3), round(fim, 3), *resto])
    for n in range(1, len(novos)):             # trechos colados não se sobrepõem
        if novos[n][0] < novos[n - 1][1]:
            meio = (novos[n][0] + novos[n - 1][1]) / 2
            novos[n - 1][1] = novos[n][0] = round(meio, 3)
    return novos


def no_tempo_da_saida(manter):
    """Função tempo-do-bruto → tempo-da-saída (None fora dos trechos mantidos)."""
    def f(t):
        acum = 0.0
        for a, b, *_ in manter:
            if a - 0.05 <= t <= b + 0.05:
                return acum + min(max(t, a), b) - a
            acum += b - a
        return None
    return f


def main():
    vid = sys.argv[1]
    info = json.load(open(os.path.join(config.REELS_BASE, 'brutos', f'{vid}.json'), encoding='utf-8'))
    ed = json.load(open(os.path.join(config.REELS_BASE, 'brutos', f'{vid}_edicao.json'), encoding='utf-8'))
    bruto = os.path.join(config.REELS_BASE, 'videos', info['video'])
    tr = json.load(open(bruto.replace('/videos/', '/transcricoes/').replace('.mp4', '.json'), encoding='utf-8'))
    palavras = [w for w in tr['words'] if w.get('type') == 'word']
    dur_bruto = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                      bruto], capture_output=True, text=True).stdout)
    manter = com_folga(ed['manter'], palavras, dur_bruto)
    total = sum(b - a for a, b, *_ in manter)
    mapa = no_tempo_da_saida(manter)
    data = info['video'].split('_')[0]
    saida = os.path.join(config.REELS_BASE, 'videos', f'{data}_{vid}E.mp4')
    tmp = os.path.join(config.REELS_BASE, 'brutos', '_tmp', f'{vid}E')
    os.makedirs(tmp, exist_ok=True)

    # palavras no tempo da saída: o início é preso ao trecho (o Scribe às vezes estica a 1ª palavra de um take)
    pals, words = [], []
    for w in tr['words']:
        if w.get('type') != 'word':
            continue
        for a, b, *_ in manter:
            if a - 0.05 <= w['end'] <= b + 0.05:
                s, e = mapa(max(w['start'], a)), mapa(w['end'])
                pals.append((s, e, w['text'].strip()))
                words.append({**w, 'start': round(s, 3), 'end': round(e, 3)})
                break
    texto = ' '.join(w['text'] for w in words)
    espaco = []
    for n, w in enumerate(words):                 # mantém o formato do Scribe (word + spacing)
        if n:
            espaco.append({'text': ' ', 'start': words[n - 1]['end'], 'end': w['start'], 'type': 'spacing'})
        espaco.append(w)

    # legenda (faixa com alfa pré-renderizada, como na tela dividida)
    lista = camada_legenda(pals, total, FPS, os.path.join(tmp, 'legenda'))
    legenda = os.path.join(tmp, 'legenda', 'legenda.mov')
    ff(['-f', 'concat', '-safe', '0', '-i', lista, '-t', f'{total:.3f}', '-vf', f'fps={FPS},format=argb',
        '-c:v', 'qtrle', legenda])

    entradas, f = [], []
    for n, (a, b, *_) in enumerate(manter):
        entradas += ['-ss', f'{a:.3f}', '-t', f'{b - a:.3f}', '-i', bruto]
        d = b - a
        quadro = ''
        if n % 2:
            z = ZOOM_EMENDA
            quadro = (f",scale={round(1080 * z / 2) * 2}:{round(1920 * z / 2) * 2},"
                      f"crop=1080:1920:{round(1080 * (z - 1) / 2)}:{round(ZOOM_CY * (z - 1))}")
        f.append(f"[{n}:v]fps={FPS}{quadro},setsar=1,setpts=PTS-STARTPTS[v{n}]")
        f.append(f"[{n}:a]aresample=48000,asetpts=PTS-STARTPTS,afade=t=in:d={FADE_AUDIO},"
                 f"afade=t=out:st={d - FADE_AUDIO:.3f}:d={FADE_AUDIO}[a{n}]")
    pares = ''.join(f'[v{n}][a{n}]' for n in range(len(manter)))
    f.append(f"{pares}concat=n={len(manter)}:v=1:a=1[cv][ca]")
    ultimo = 'cv'
    for k, img in enumerate(ed.get('imagens', [])):
        t0 = mapa(img['em'])
        if t0 is None:
            raise SystemExit(f"imagem {k}: 'em'={img['em']} fora dos trechos mantidos")
        dur = min(float(img.get('dur', IMAGEM_MAX)), IMAGEM_MAX)
        png = os.path.join(tmp, f'imagem{k}.jpg')
        png_imagem(os.path.join(config.PROJETO, img['arquivo']), png)
        i = len(manter) + k
        entradas += ['-loop', '1', '-framerate', str(FPS), '-t', f'{dur:.3f}', '-i', png]
        f.append(f"[{i}:v]format=rgba,fade=t=in:d={FADE_IMG}:alpha=1,fade=t=out:st={dur - FADE_IMG:.3f}:d={FADE_IMG}:alpha=1,"
                 f"setpts=PTS-STARTPTS+{t0:.3f}/TB[im{k}]")
        f.append(f"[{ultimo}][im{k}]overlay=0:0:eof_action=pass:format=auto[ov{k}]")
        ultimo = f'ov{k}'
        print(f'  imagem {k}: {t0:.2f}–{t0 + dur:.2f} s na saída ({dur:.1f} s)')
    f.append(f"movie={filtro_caminho(legenda)},fps={FPS},format=rgba,setpts=PTS-STARTPTS[lg]")
    f.append(f"[{ultimo}][lg]overlay=0:{LEGENDA_Y}:eof_action=pass:format=auto,format=yuv420p[vout]")
    f.append("[ca]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    ff([*entradas, '-filter_complex', ';'.join(f), '-map', '[vout]', '-map', '[aout]', '-t', f'{total:.3f}',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS),
        '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', saida])

    json.dump({'language_code': tr.get('language_code', 'por'), 'text': texto, 'words': espaco,
               'origem': f'remapeada de {info["video"]} por editar_bruto.py'},
              open(saida.replace('/videos/', '/transcricoes/').replace('.mp4', '.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    final = os.path.join(config.SAIDA_DIR, 'brutos', vid, 'sem gancho', f'{vid} sem gancho.mp4')
    os.makedirs(os.path.dirname(final), exist_ok=True)
    shutil.copyfile(saida, final)
    print(f'{vid}: {len(manter)} trechos, {total:.1f} s → {saida}\n  sem gancho: {final}')


if __name__ == '__main__':
    main()

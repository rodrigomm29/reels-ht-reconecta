#!/usr/bin/env python3
"""Monta um vídeo no formato "tela verde" (aprovado em 23/10/2026): fundo em tela cheia (vídeo de paciente, foto ou
quadro congelado) e a Fernanda recortada por cima, no CANTO inferior esquerdo ou no CENTRO.

Entrada: um JSON de montagem (EDL) com as fontes e as versões:
{
 "fundos": {"hannah": "brutos/.../IMG_9808.mov"},
 "falas":  {"hannah": "dados/depoimentos/hannah.json"},           # transcrição (Scribe) de cada fonte, p/ legenda
 "takes":  {"dir": "brutos/.../", "transcr": "dados/depoimentos/hannah_fernanda/"},
 "imagens": {"antes_depois": "dados/depoimentos/hannah_antes_depois.png"},
 "cenas": {
   "c1": {"fundo": {"video": "hannah", "ini": 20.6, "fim": 30.6}, "audio": "fundo",
          "fernanda": {"take": "IMG_1752", "ini": 0.8, "pos": "canto", "mudo": true},
          "texto_tela": "Fios, PDRN, preenchimento… e nada resolveu."},
   "c2": {"fundo": {"congela": "hannah", "t": 30.5}, "fernanda": {"take": "IMG_1742", "ini": 2.1, "fim": 4.1,
          "pos": "canto"}, "audio": "fernanda"},
   "c3": {"fundo": {"congela": "hannah", "t": 30.5, "escuro": true}, ...},
   "c4": {"fundo": {"imagem": "antes_depois"}, ...}
 },
 "versoes": {"feed": ["c1", "c2", ...], "anuncio": [...]},
 "saida": "saida/casos/hannah"
}
Duração de cada cena: a do trecho de fundo quando o áudio é do fundo; senão a do take da Fernanda (já acelerado).
A Fernanda fala a VELOCIDADE_FALA (1,10×); a paciente fica na velocidade normal.
Legenda em frase (3–4 palavras), branca com sombra: y≈1720 com a Fernanda no canto (acima fica o rosto da
paciente), y≈1445 com ela no centro. Texto na tela: branco sem caixa no alto (y≈375), 2,7 s.
O recorte vem do bin/recortar_pessoa (Vision): rode `swiftc -O recortar_pessoa.swift -o bin/recortar_pessoa`.

uso: python3 ferramentas/tela_verde.py dados/depoimentos/hannah_tela_verde.json [--so feed] [--forcar]
"""
import argparse, json, os, subprocess, sys

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, 'ferramentas'))
import config  # noqa: E402
from PIL import Image  # noqa: E402
from montar_ht_peles import ajustar, texto_com_sombra, FONTE_LEGENDA  # noqa: E402
from editar_bruto import grupos_frase, png_titulo_texto, FRASE_TAM  # noqa: E402
from sdr import garantir_sdr  # noqa: E402

FPS, W, H = 30, 1080, 1920
V = config.VELOCIDADE_FALA
POS = {'canto': (0.55, -20, H - round(H * 0.55)),          # escala, x, y (rodapé alinhado)
       'centro': (0.95, round(W * 0.025), H - round(H * 0.95))}
LEG_CY = {'canto': 1720, 'centro': 1445, 'fora': 1445}
TEXTO_DUR = 2.7
FOLGA_ANTES, FOLGA_DEPOIS = 0.10, 0.18
RECORTE = os.path.join(AQUI, 'bin', 'recortar_pessoa')


def ff(*a):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *a], check=True)


def dur(arq):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                                capture_output=True, text=True).stdout)


def palavras(caminho):
    d = json.load(open(caminho, encoding='utf-8'))
    return [(w['start'], w['end'], w['text']) for w in d['words'] if w.get('type') == 'word']


def png_frase(texto, cy, saida):
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    f, ls = ajustar(texto, FONTE_LEGENDA, FRASE_TAM, 40, 960, 2)
    texto_com_sombra(img, ls, f, 540, cy - f.size * 1.1 * len(ls) / 2, 1.1, (255, 255, 255), sombra=0.6, raio=8)
    img.save(saida)


def legendas(pals, total, cy, pasta, nome):
    """[(png, t0, t1)] das frases dentro de [0, total] (tempos já no relógio da cena)."""
    out, gs = [], grupos_frase([p for p in pals if p[1] > 0.02 and p[0] < total - 0.02])
    for n, g in enumerate(gs):
        t0 = max(g[0][0], 0.0)
        t1 = min(gs[n + 1][0][0] if n + 1 < len(gs) else g[-1][1] + 0.4, g[-1][1] + 0.6, total)
        if t1 - t0 < 0.1:
            continue
        arq = os.path.join(pasta, f'{nome}_f{n:02d}.png')
        png_frase(' '.join(x[2] for x in g), cy, arq)
        out.append((arq, t0, t1))
    return out


def preparar_take(cfg, edl, cena, tmp):
    """Corta o take (girado de pé, 1080×1920, 30 fps), acelera a fala e gera a máscara da pessoa."""
    f = cena['fernanda']
    take = os.path.join(AQUI, edl['takes']['dir'], f['take'] + '.mov')
    take = garantir_sdr(take, os.path.join(tmp, 'sdr'))              # HDR do iPhone sai lavado sem o ajuste de tom
    pals = palavras(os.path.join(AQUI, edl['takes']['transcr'], f['take'] + '.json'))
    ini = f.get('ini')
    fim = f.get('fim')
    if ini is None:
        ini = max(pals[0][0] - FOLGA_ANTES, 0) if pals else 0
    if fim is None:
        fim = min(pals[-1][1] + FOLGA_DEPOIS, dur(take)) if pals else dur(take)
    vel = 1.0 if f.get('mudo') else f.get('vel', V)
    clip = os.path.join(tmp, f"{cfg}_{f['take']}_{ini:.2f}.mp4")
    ff('-ss', f'{ini:.3f}', '-to', f'{fim:.3f}', '-i', take,
       '-vf', f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setpts=PTS/{vel},fps={FPS},setsar=1',
       '-af', f'atempo={vel},aresample=48000', '-c:v', 'libx264', '-crf', '14', '-c:a', 'aac', '-b:a', '192k', clip)
    masc = clip.replace('.mp4', '_m.mp4')
    p1 = subprocess.Popen([RECORTE, clip], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'gray', '-s', f'{W}x{H}',
                    '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-crf', '10', '-pix_fmt', 'yuv420p', masc],
                   stdin=p1.stdout, check=True)
    p1.wait()
    # palavras no relógio da cena
    ps = [((s - ini) / vel, (e - ini) / vel, t) for s, e, t in pals if s >= ini - 0.05 and e <= fim + 0.05]
    return clip, masc, dur(clip), ps


def render_cena(nome, cena, edl, tmp, cache):
    if nome in cache:
        return cache[nome]
    fu = cena['fundo']
    entradas, filtros = [], []
    tem_f = bool(cena.get('fernanda'))
    if tem_f:
        clip, masc, dclip, pf = preparar_take(nome, edl, cena, tmp)
    # duração
    if cena.get('audio', 'fernanda') == 'fundo':
        total = fu['fim'] - fu['ini']
    else:
        total = dclip
    total = round(total * FPS) / FPS
    # fundo
    if 'video' in fu:
        src = garantir_sdr(os.path.join(AQUI, edl['fundos'][fu['video']]), os.path.join(tmp, 'sdr'))
        entradas += ['-ss', f"{fu['ini']:.3f}", '-t', f'{total:.3f}', '-i', src]
    elif 'congela' in fu:
        src = garantir_sdr(os.path.join(AQUI, edl['fundos'][fu['congela']]), os.path.join(tmp, 'sdr'))
        png = os.path.join(tmp, f"cong_{fu['congela']}_{fu['t']:.2f}.png")
        ff('-ss', f"{fu['t']:.3f}", '-i', src, '-frames:v', '1', png)
        entradas += ['-loop', '1', '-t', f'{total:.3f}', '-i', png]
    else:
        entradas += ['-loop', '1', '-t', f'{total:.3f}', '-i', os.path.join(AQUI, edl['imagens'][fu['imagem']])]
    bg = (f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,'
          f'tpad=stop_mode=clone:stop_duration={total},trim=duration={total}')
    if fu.get('escuro'):
        bg += ',boxblur=18:2,eq=brightness=-0.18'
    filtros.append(bg + ',format=yuv420p[bg]')
    atual, n = 'bg', 1
    pos = 'fora'
    if tem_f:
        pos = cena['fernanda'].get('pos', 'canto')
        esc, x, y = POS[pos]
        entradas += ['-i', clip, '-i', masc]
        congela = f',tpad=stop_mode=clone:stop_duration={total}' if dclip < total else ''
        filtros.append(f'[{n + 1}:v]format=gray,boxblur=2:1,lutyuv=y=\'clip((val-40)*1.4,0,255)\'{congela},'
                       f'trim=duration={total},scale=iw*{esc}:-1[m]')
        filtros.append(f'[{n}:v]format=yuva420p{congela},trim=duration={total},scale=iw*{esc}:-1[fv]')
        filtros.append('[fv][m]alphamerge[fa]')
        filtros.append(f'[{atual}][fa]overlay={x}:{y}:shortest=0:eof_action=pass[v{n}]')
        atual, n_f, n = f'v{n}', n, n + 2
    # legendas
    if cena.get('audio', 'fernanda') == 'fundo' and fu.get('video') in edl.get('falas', {}):
        ph = palavras(os.path.join(AQUI, edl['falas'][fu['video']]))
        ps = [(s - fu['ini'], e - fu['ini'], t) for s, e, t in ph if s >= fu['ini'] - 0.05 and e <= fu['ini'] + total + 0.05]
    elif tem_f and not cena['fernanda'].get('mudo'):
        ps = pf
    else:
        ps = []
    cy = LEG_CY[pos] if cena.get('audio', 'fernanda') == 'fernanda' else LEG_CY['canto']
    camadas = legendas(ps, total, cy, tmp, nome)
    if cena.get('texto_tela'):
        tt = os.path.join(tmp, f'{nome}_titulo.png')
        png_titulo_texto(cena['texto_tela'], tt, 375)
        camadas.append((tt, 0.0, min(TEXTO_DUR, total)))
    for arq, t0, t1 in camadas:
        entradas += ['-loop', '1', '-t', f'{total:.3f}', '-i', arq]
        # [t0, t1): com between() (fechado nos dois lados) o quadro exato da troca mostrava as 2 frases (27/10)
        filtros.append(f"[{atual}][{n}:v]overlay=0:0:enable='gte(t,{t0:.4f})*lt(t,{t1:.4f})'[v{n}]")
        atual, n = f'v{n}', n + 1
    # áudio
    if cena.get('audio', 'fernanda') == 'fundo':
        a = f"[0:a]atrim=duration={total},asetpts=PTS-STARTPTS"
    else:
        a = f"[{n_f}:a]apad,atrim=duration={total}"
    filtros.append(a + ',aresample=48000,loudnorm=I=-16:TP=-1.5:LRA=11,aformat=channel_layouts=stereo[a]')
    saida = os.path.join(tmp, f'cena_{nome}.mp4')
    ff(*entradas, '-filter_complex', ';'.join(filtros), '-map', f'[{atual}]', '-map', '[a]', '-t', f'{total:.3f}',
       '-r', str(FPS), '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p',
       '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', saida)
    cache[nome] = saida
    print(f'  cena {nome}: {total:.2f}s ({pos})')
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('edl')
    ap.add_argument('--so', nargs='*')
    a = ap.parse_args()
    edl = json.load(open(a.edl, encoding='utf-8'))
    saida = os.path.join(AQUI, edl['saida'])
    tmp = os.path.join(saida, '_tmp')
    os.makedirs(tmp, exist_ok=True)
    cache = {}
    for versao, cenas in edl['versoes'].items():
        if a.so and versao not in a.so:
            continue
        print(f'{versao}:')
        partes = [render_cena(c, edl['cenas'][c], edl, tmp, cache) for c in cenas]
        lista = os.path.join(tmp, f'{versao}.txt')
        open(lista, 'w').write(''.join(f"file '{p}'\n" for p in partes))
        final = os.path.join(saida, f"{edl.get('prefixo', 'tela_verde')}_{versao}.mp4")
        # junta pelo filtro concat (decodifica e reencoda): o -c copy deixava o vídeo 0,021 s atrás do áudio e o
        # render dos ganchos travava sem CPU; o concat demuxer reencodado encurtava a imagem (27/10/2026)
        ent = [x for p in partes for x in ('-i', p)]
        fc = ''.join(f'[{i}:v]settb=1/{FPS},setpts=PTS-STARTPTS,fps={FPS}[v{i}];[{i}:a]asetpts=PTS-STARTPTS,'
                     f'aresample=48000[a{i}];' for i in range(len(partes)))
        fc += ''.join(f'[v{i}][a{i}]' for i in range(len(partes))) + f'concat=n={len(partes)}:v=1:a=1[v][a]'
        ff(*ent, '-filter_complex', fc, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '17',
           '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
           '-movflags', '+faststart', final)
        print(f'  → {final} ({dur(final):.1f}s)')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Monta o KIT das peles (Manchete, Cinema, Dinâmica) a partir dos packs do Cineva e do Pack editor:
converte UMA VEZ os efeitos 4K pra 1080×1920 / 30 fps, pra cada render não ter que decodificar 4K.
Também extrai os marcadores animados (traço à mão com alfa) em PNG, que o montar_ht_peles.py
compõe com o texto dos números.

uso: python3 kit_peles.py            # só converte o que falta (pode rodar de novo)
     python3 kit_peles.py --refazer

Saída: KIT_DIR do config.env (+ kit.json com caminhos e níveis dos SFX)
Origem: CINEVA_DIR e PACK_EDITOR_DIR do config.env (pacotes pagos); só LÊ deles.
"""
import argparse, json, os, subprocess, sys
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402

CINEVA = config.CINEVA_DIR
PACK = config.PACK_EDITOR_DIR
KIT = config.KIT_DIR

# vídeo: (saída, origem, segundos a usar (None = tudo), recorte 9:16 centrado)
VIDEOS = [
    ('grao_35mm.mp4',      f'{CINEVA}/35MM/35mm/35mmGrain_Fine_4K.mov', 20),
    ('queima_cinema.mp4',  f'{CINEVA}/Film Burns/Filmburn1 (Screen).mov', None),
    ('vhs_tracking.mp4',   f'{CINEVA}/VHS TEXTURES + TRANSITIONS/Tracking_Down.mp4', 3),
    ('vhs_ruido.mp4',      f'{CINEVA}/VHS TEXTURES + TRANSITIONS/Long_1.mp4', 3),
    ('vhs_transicao.mp4',  f'{CINEVA}/VHS TEXTURES + TRANSITIONS/Transition_1.mp4', None),
    ('glitch.mp4',         f'{CINEVA}/CRT-TEXTURES (4K)/GLITCHES/B_GLITCH_01.mp4', None),
]
# marcadores com alfa → PNG (1280×720, o traço fica no centro do quadro 16:9)
MARCADORES = {
    'circulo':    f'{CINEVA}/MARKERS/MOTION/CFX-MARKER_CIRCLE_01.mov',
    'sublinhado': f'{CINEVA}/MARKERS/MOTION/CFX-MARKER_LINE_04.mov',
    'brilho':     f'{CINEVA}/MARKERS/MOTION/CFX-MARKER_SHINE_01.mov',
    'seta':       f'{CINEVA}/MARKERS/MOTION/CFX-MARKER_ARROW_04.mov',
}
# SFX: arquivo, trecho usado (início, duração), instante do pico DENTRO do trecho, ganho (dB).
# Referência medida: obturador pico −0,6 dBFS a −8 dB ≈ −9 dBFS, ~10 dB abaixo da voz (aprovado SEM39).
SFX = {
    'obturador': {'arq': f'{PACK}/SFX/SFX Interface PRO/Shutter Câmera2_byEditorPro.mp3', 'ini': 0.0, 'dur': 0.89, 'pico': 0.256, 'ganho': -8},
    'rebobinar': {'arq': f'{PACK}/SFX/SFX Retro PRO/FIta Rebobinando_byEditorPro.mp3', 'ini': 0.2, 'dur': 1.4, 'pico': 0.31, 'ganho': -12},
    'whoosh':    {'arq': f'{CINEVA}/ESSENTIAL SOUND FX/WHOOSHES/Deep whoosh.wav', 'ini': 2.2, 'dur': 1.6, 'pico': 0.90, 'ganho': 2},
    'zoom':      {'arq': f'{CINEVA}/ESSENTIAL SOUND FX/WHOOSHES/High whoosh.wav', 'ini': 1.45, 'dur': 0.9, 'pico': 0.51, 'ganho': -2},
    'impacto':   {'arq': f'{CINEVA}/ESSENTIAL SOUND FX/HITS/Gleam hit.wav', 'ini': 0.55, 'dur': 1.8, 'pico': 0.18, 'ganho': -1},
    'glitch':    {'arq': f'{PACK}/SFX EFFECTS (Bônus)/SFX/GLITCH/Glitch 1.wav', 'ini': 0.0, 'dur': None, 'pico': None, 'ganho': -10},
    'pop':       {'arq': f'{PACK}/SFX EFFECTS (Bônus)/SFX/POPS/Pop 1.wav', 'ini': 0.0, 'dur': None, 'pico': None, 'ganho': -12},
}

def ff(*args):
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', *args], check=True)

def dur(caminho):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', caminho],
                                capture_output=True, text=True, check=True).stdout)

def pico_de(caminho, ini=0.0, dur_=None):
    """Instante (s) e nível (dBFS) do pico, em blocos de 10 ms."""
    import math, struct
    args = ['ffmpeg', '-nostdin', '-v', 'error', '-ss', str(ini)] + (['-t', str(dur_)] if dur_ else []) + \
           ['-i', caminho, '-ac', '1', '-ar', '48000', '-f', 's16le', '-']
    raw = subprocess.run(args, capture_output=True, check=True).stdout
    a = struct.unpack(f'{len(raw)//2}h', raw)
    pk = [max(abs(x) for x in a[i:i+480]) for i in range(0, len(a), 480)]
    m = max(pk) or 1
    return round(pk.index(m) * 0.01, 3), round(20 * math.log10(m / 32768), 1), round(len(a) / 48000, 3)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refazer', action='store_true')
    a = ap.parse_args()
    os.makedirs(KIT, exist_ok=True)
    kit = {'pasta': KIT, 'video': {}, 'marcadores': {}, 'sfx': {}}
    for nome, origem, seg in VIDEOS:
        saida = os.path.join(KIT, nome)
        kit['video'][nome.rsplit('.', 1)[0]] = saida
        if os.path.exists(saida) and not a.refazer:
            continue
        # recorte 9:16 centrado na altura toda, escala 1080×1920, 30 fps; CRF baixo pra não matar o grão
        vf = "crop='min(iw,ih*9/16)':ih,scale=1080:1920:flags=lanczos,fps=30,format=yuv420p,setsar=1"
        ff(*(['-t', str(seg)] if seg else []), '-i', origem, '-an', '-vf', vf,
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '12', saida + '.part.mp4')
        os.replace(saida + '.part.mp4', saida)
        print(f'vídeo  {nome}  {dur(saida):.2f}s')
    for nome, origem in MARCADORES.items():
        pasta = os.path.join(KIT, f'marcador_{nome}')
        kit['marcadores'][nome] = pasta
        if os.path.isdir(pasta) and os.listdir(pasta) and not a.refazer:
            continue
        os.makedirs(pasta, exist_ok=True)
        # só os 1,6 s iniciais (o traço se desenha em ~1 s e para); 30 fps; PNG com alfa
        ff('-t', '1.6', '-i', origem, '-vf', 'scale=1280:720:flags=lanczos,fps=30,format=rgba',
           os.path.join(pasta, 'q%03d.png'))
        print(f'marcador {nome}: {len(os.listdir(pasta))} quadros')
    for nome, s in SFX.items():
        if not os.path.exists(s['arq']):
            sys.exit(f'SFX não encontrado: {s["arq"]}')
        d = s['dur']
        if s['pico'] is None:                        # mede o que não foi medido à mão
            p, nivel, total = pico_de(s['arq'], s['ini'], d)
            s = {**s, 'pico': p, 'dur': d or total, 'nivel_pico_dbfs': nivel}
        kit['sfx'][nome] = s
    json.dump(kit, open(os.path.join(KIT, 'kit.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('kit.json ok:', ', '.join(f"{k} pico {v['pico']}s" for k, v in kit['sfx'].items()))

if __name__ == '__main__':
    main()

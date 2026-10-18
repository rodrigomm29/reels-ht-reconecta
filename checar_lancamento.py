#!/usr/bin/env python3
"""Varre a TELA e a FALA de Reels procurando lançamento pago / Desafio / evento antes de virarem Reel base.

Por quê (06/10/2026): o DcKVLWVJ-lb fala de "abater a consulta", mas abre com o print de um post
"comenta SUPERCASO aqui embaixo… que eu te chamo no direct". A transcrição não acusava nada; só a tela.
Regra do Sávio: nada de Reel que fale de lançamento pago (Desafio SUPERCASO), live ou Reel de 22/07 pra trás.

uso: python3 checar_lancamento.py DbT-73eCedT DcKVLWVJ-lb ...
Lê 1 quadro a cada 2 s (meia resolução) com o OCR do Vision (bin/ocr_legenda) + a transcrição do Scribe.
Saída: LIMPO ou as linhas que bateram (com o tempo). Palavras comuns que dão falso positivo ficam na
lista IGNORAR (ex.: "inscrita como mesária").
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = config.REELS_BASE
PADRAO = re.compile(r'supercaso|super caso|desafio|lançamento|ingresso|inscriç|janela abre|mansão|workshop|'
                    r'ao vivo|link na bio|vagas|'
                    # Dra. Fernanda (18/10/2026): oferta, preço e data não entram em Reel base
                    r'promoç|desconto|\bpreço|\bvalor(es)? (de|do|da)|parcel|condição especial|sorteio|'
                    r'black friday|outubro rosa|dia das mães|\blive\b|garantid', re.I)
IGNORAR = re.compile(r'mesári', re.I)

def achar(pasta, sufixo):
    return next((os.path.join(pasta, f) for f in os.listdir(pasta) if f.endswith(sufixo) and not f.startswith('._')), None)

def checar(sc):
    video = achar(os.path.join(BASE, 'videos'), f'_{sc}.mp4')
    if not video:
        return f'{sc}: vídeo não baixado'
    achados = []
    tr = achar(os.path.join(BASE, 'transcricoes'), f'_{sc}.json')
    if tr:
        texto = json.load(open(tr, encoding='utf-8')).get('text', '')
        for m in PADRAO.finditer(texto):
            trecho = texto[max(0, m.start() - 50):m.end() + 40].replace('\n', ' ')
            if not IGNORAR.search(trecho):
                achados.append(f'fala: …{trecho}…')
    tmp = tempfile.mkdtemp(prefix='lanc_')
    try:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', video, '-vf', 'fps=0.5,scale=540:-1',
                        os.path.join(tmp, 'q%04d.png')], check=True)
        qs = sorted(glob.glob(os.path.join(tmp, 'q*.png')))
        saida = subprocess.run([os.path.join(AQUI, 'bin', 'ocr_legenda'), *qs], capture_output=True, text=True).stdout
        for linha in saida.splitlines():
            caminho, _, txt = linha.partition('\t')
            if PADRAO.search(txt) and not IGNORAR.search(txt):
                n = int(re.search(r'q(\d+)\.png', caminho).group(1))
                achados.append(f'tela ~{(n - 1) * 2}s: {txt[:110]}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f'{sc}: ' + ('LIMPO' if not achados else 'ACHOU\n   ' + '\n   '.join(achados[:6]))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for sc in sys.argv[1:]:
        print(checar(sc), flush=True)

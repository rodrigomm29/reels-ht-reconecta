#!/usr/bin/env python3
"""Confere se a LEGENDA QUEIMADA do Reel casa com o áudio de cada gancho. Senão a tela mostra palavras
que a fala do gancho não diz (VD004_B/VD005_B do SEM39; VD003_B/VD004_B/VD007_A do SEM40).

uso:
  python3 blocos_legenda.py <video> <transcricao.json> --de 80 --ate 100   # lista os blocos da legenda
  python3 blocos_legenda.py --plano planos/ht_sem40.json                   # confere todos os ganchos
  python3 blocos_legenda.py --plano planos/ht_sem40.json --aplicar         # grava os ajustes finos no plano

Como funciona:
  1. Detecta os BLOCOS da legenda (quando cada um entra e sai): decodifica só a janela (-ss/-t), recorta
     a faixa da legenda e lê quadro a quadro por pipe (memória constante). Texto = pixel > 240 (a blusa
     branca do VD005 fica em ~231 e não conta). Troca de bloco = a máscara muda > 35 % de um quadro pro outro.
  2. LÊ cada bloco que aparece durante o gancho com o OCR do Vision (bin/ocr_legenda). Não dá pra deduzir
     o texto pelo tempo das palavras: a legenda do VD004 chega até 0,8 s DEPOIS da fala.
  3. Palavra "de fora" = aparece na legenda, está na fala dos 4 s antes/depois do gancho e NÃO está no
     gancho. Números e grafia de legenda ("R$20.000", "cê/você") ficam neutros: só conta o que casa com
     a fala de fora.
  4. Veredito por gancho:
     - ok;
     - AJUSTE FINO (automático com --aplicar): bloco errado só nas pontas e curto → `ini_corte_min`
       (começa depois dele, até 0,25 s) ou `fim_video` (congela o último quadro limpo, até 0,35 s);
     - TROCAR GANCHO: bloco errado longo ou no meio → escolher outro trecho (listar os blocos com --de/--ate).
Sempre olhar a tira de quadros depois de renderizar: o script aponta, o olho confirma.
"""
import argparse, json, os, re, subprocess, sys, tempfile, unicodedata
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from montar_ht_hooks import corte_do_gancho  # noqa: E402
import config  # noqa: E402

OCR = os.path.join(AQUI, 'bin', 'ocr_legenda')
# faixa da legenda em 1080×1920 (config.env). LEGENDA_FAIXA_Y=auto mede por vídeo (faixa_do) e guarda em
# planos/_legenda_faixa.json: a legenda da Fernanda muda de altura de um Reel pro outro (1130 a 1290).
FAIXA_Y, FAIXA_H = config.LEGENDA_FAIXA_Y, config.LEGENDA_FAIXA_H
W = 540                               # faixa reduzida (1/2): em 1/4 a legenda de letra pequena (DeASuSYATAR) some
FPS = 30
LIMIAR_BRANCO = 240
TROCA = 0.35
MIN_TEXTO = config.LEGENDA_MIN_TEXTO  # pixels de texto na faixa reduzida (Ana: 240; legenda pequena dá 700+, blusa branca dá 1)
MIN_BLOCO = 0.15
TETO_INI, TETO_FIM = 0.25, 0.35       # s de bloco errado que o ajuste fino resolve sem trocar o gancho

CACHE_FAIXA = os.path.join(AQUI, 'planos', '_legenda_faixa.json')


def medir_faixa(video, amostras=10):
    """Acha a faixa da legenda queimada lendo FAIXAS horizontais da tela com o OCR (y 760 a 1560, de 80 em 80)
    em alguns quadros, e fica com a que mais devolve palavras da própria fala (transcrição). Brilho ou
    movimento enganam (mão, rosto, blusa branca); palavra da fala, não."""
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', video],
                               capture_output=True, text=True).stdout)
    tr = video.replace('/videos/', '/transcricoes/').rsplit('.', 1)[0] + '.json'
    fala = set(tokens(json.load(open(tr, encoding='utf-8')).get('text', ''))) if os.path.exists(tr) else set()
    ys = list(range(760, 1561, 80))
    with tempfile.TemporaryDirectory() as d:
        pngs = {}
        for k in range(amostras):
            t = dur * (k + 0.5) / amostras
            quadro = os.path.join(d, f'q{k}.png')
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', f'{t:.2f}', '-i', video,
                            '-frames:v', '1', '-vf', 'scale=1080:1920', quadro], check=True)
            for y in ys:
                faixa = os.path.join(d, f'q{k}_{y}.png')
                subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', quadro,
                                '-vf', f'crop=1080:160:0:{y}', faixa], check=True)
                pngs[faixa] = y
        saida = subprocess.run([OCR, *pngs], capture_output=True, text=True).stdout
    pontos = {y: 0 for y in ys}
    for linha in saida.splitlines():
        if '\t' in linha:
            caminho, texto = linha.split('\t', 1)
            pontos[pngs[caminho]] += sum(1 for w in tokens(texto) if len(w) >= 3 and (not fala or w in fala))
    melhor = max(ys, key=lambda y: pontos[y])
    if pontos[melhor] < 3:                               # quase nada lido: sem legenda queimada
        return FAIXA_Y_PADRAO, FAIXA_H_PADRAO
    # a legenda pode estar entre duas faixas vizinhas: junta a vizinha se ela também leu bem
    viz = [y for y in (melhor - 80, melhor + 80) if pontos.get(y, 0) >= pontos[melhor] * 0.6]
    y0, y1 = min([melhor] + viz), max([melhor] + viz) + 160
    return y0, y1 - y0


FAIXA_Y_PADRAO, FAIXA_H_PADRAO = 1200, 440
_faixas = {}


def faixa_do(video):
    """(y, altura) da faixa da legenda deste vídeo: a do config.env, ou medida (LEGENDA_FAIXA_Y=auto)."""
    if str(FAIXA_Y).lower() != 'auto':
        return int(FAIXA_Y), int(FAIXA_H)
    nome = os.path.basename(video)
    if nome not in _faixas:
        cache = json.load(open(CACHE_FAIXA, encoding='utf-8')) if os.path.exists(CACHE_FAIXA) else {}
        if nome not in cache:
            cache[nome] = list(medir_faixa(video))
            json.dump(cache, open(CACHE_FAIXA, 'w', encoding='utf-8'), indent=1)
        _faixas[nome] = tuple(cache[nome])
    return _faixas[nome]


def mascaras(video, t0, dur):
    fy, fh = faixa_do(video)
    H = fh // 2
    cmd = ['ffmpeg', '-nostdin', '-loglevel', 'error', '-ss', f'{t0:.3f}', '-t', f'{dur:.3f}', '-i', video,
           '-vf', f'fps={FPS},scale=1080:1920,crop=1080:{fh}:0:{fy},scale={W}:{H},format=gray',
           '-f', 'rawvideo', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n, i = W * H, 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield t0 + i / FPS, np.frombuffer(buf, dtype=np.uint8).reshape(H, W) > LIMIAR_BRANCO
        i += 1
    p.wait()

def blocos(video, t0, t1):
    """[(inicio, fim, tem_texto)] contíguos na janela."""
    t0 = max(0.0, t0)
    out, ini, ant, texto_ant, t = [], None, None, False, t0
    for t, m in mascaras(video, t0, t1 - t0):
        texto = m.sum() >= MIN_TEXTO
        if ant is None:
            ini, ant, texto_ant = t, m, texto
            continue
        uniao = np.logical_or(m, ant).sum()
        if (texto != texto_ant) or (texto and uniao and np.logical_xor(m, ant).sum() / uniao > TROCA):
            out.append([ini, t, texto_ant])
            ini, texto_ant = t, texto
        ant = m
    if ini is not None:
        out.append([ini, t + 1 / FPS, texto_ant])
    limpo = []
    for b in out:                      # troca falsa curta (mão passando) volta pro bloco anterior
        if limpo and b[1] - b[0] < MIN_BLOCO:
            limpo[-1][1] = b[1]
            continue
        limpo.append(b)
    return [tuple(b) for b in limpo]

def ocr(video, tempos):
    """Lê a legenda nos instantes pedidos. Devolve [texto]."""
    fy, fh = faixa_do(video)
    with tempfile.TemporaryDirectory() as d:
        pngs = []
        for i, t in enumerate(tempos):
            png = os.path.join(d, f'{i}.png')
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', f'{t:.3f}', '-i', video,
                            '-frames:v', '1', '-vf', f'scale=1080:1920,crop=1080:{fh}:0:{fy}', png], check=True)
            pngs.append(png)
        if not pngs:
            return []
        saida = subprocess.run([OCR, *pngs], capture_output=True, text=True).stdout
        por = dict(l.split('\t', 1) for l in saida.splitlines() if '\t' in l)
        return [por.get(p, '') for p in pngs]

TROCAS = {'ce': 'voce', 'ta': 'esta', 'pra': 'para', 'pro': 'para', 'to': 'estou', 'tao': 'estao'}

def tokens(texto):
    t = unicodedata.normalize('NFD', texto.lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return [TROCAS.get(x, x) for x in re.findall(r"[a-z]+", t)]

def palavras(transcricao):
    return [w for w in json.load(open(transcricao, encoding='utf-8'))['words'] if w.get('type') == 'word']

def conferir(cfg, v, hk):
    pals = palavras(v['transcricao'])
    ini, fim, extra, fim_v = corte_do_gancho(pals, hk, cfg)
    dentro = set(tokens(' '.join(w['text'] for w in pals if hk['inicio'] - 0.01 <= w['start'] and w['end'] <= hk['fim'] + 0.01)))
    fora = set(tokens(' '.join(w['text'] for w in pals if (hk['inicio'] - 4 <= w['start'] < hk['inicio'] - 0.01)
                               or (hk['fim'] + 0.01 < w['end'] <= hk['fim'] + 4))))
    ult = fim_v + 1 / FPS                                   # o último quadro mostrado (depois congela)
    segs = []
    for b0, b1, tem in blocos(v['arquivo'], ini - 0.5, ult + 0.5):
        o0, o1 = max(b0, ini), min(b1, ult)
        if o1 - o0 <= 1e-3 or not tem:
            continue
        tela = o1 - o0 + ((fim - fim_v) + extra if b1 >= ult - 1e-3 else 0.0)   # soma o congelado
        segs.append({'de': round(o0, 3), 'ate': round(o1, 3), 'tela': round(tela, 3), 'ler': (o0 + o1) / 2})
    for s, txt in zip(segs, ocr(v['arquivo'], [s['ler'] for s in segs])):
        s['texto'] = txt
        # artigo/preposição de 1-2 letras não conta: a legenda escreve "para o mercado" onde a fala diz "pro mercado"
        s['de_fora'] = sorted({t for t in tokens(txt) if t in fora and t not in dentro and len(t) > 2})
    ruins = [s for s in segs if s['de_fora']]
    ajuste, veredito = {}, 'ok'
    for s in ruins:
        if s is segs[0] and s['tela'] <= TETO_INI and s['ate'] < hk['inicio'] + 0.01:
            ajuste['ini_corte_min'] = round(s['ate'], 3)
        elif s is segs[-1] and s['tela'] <= TETO_FIM and len(segs) > 1:
            ajuste['fim_video'] = round(s['de'] - 1 / FPS, 3)
        else:
            veredito = 'TROCAR GANCHO'
    if veredito == 'ok' and ajuste:
        veredito = 'AJUSTE FINO'
    return veredito, segs, ajuste, (ini, fim, fim_v)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video', nargs='?')
    ap.add_argument('transcricao', nargs='?')
    ap.add_argument('--de', type=float)
    ap.add_argument('--ate', type=float)
    ap.add_argument('--plano')
    ap.add_argument('--so', help='só este gancho, ex.: VD003_B')
    ap.add_argument('--aplicar', action='store_true', help='grava ini_corte_min / fim_video no plano')
    a = ap.parse_args()
    if not a.plano:
        bl = blocos(a.video, a.de, a.ate)
        textos = ocr(a.video, [(b0 + b1) / 2 for b0, b1, tem in bl])
        for (b0, b1, tem), txt in zip(bl, textos):
            print(f"[{b0:7.2f} – {b1:7.2f}] {('«' + txt + '»') if tem else '(sem legenda)'}")
        return
    plano = json.load(open(a.plano, encoding='utf-8'))
    trocar = 0
    for v in plano['videos']:
        for letra, hk in sorted(v['hooks'].items()):
            rot = f"{v['vd']}_{letra}"
            if a.so and a.so != rot:
                continue
            veredito, segs, ajuste, (ini, fim, fim_v) = conferir(plano, v, hk)
            print(f"{rot} [{hk['inicio']:.2f}–{hk['fim']:.2f}] corte {ini:.2f}→{fim:.2f}: {veredito}")
            for s in segs:
                marca = f"  ← de fora: {', '.join(s['de_fora'])}" if s['de_fora'] else ''
                print(f"    {s['de']:.2f}–{s['ate']:.2f} ({s['tela']:.2f} s na tela) «{s['texto']}»{marca}")
            if ajuste:
                print(f"    ajuste fino: {ajuste}")
                if a.aplicar:
                    hk.update(ajuste)
            trocar += veredito == 'TROCAR GANCHO'
    if a.aplicar:
        json.dump(plano, open(a.plano, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f"== ajustes finos gravados em {a.plano}")
    print(f"== {trocar} gancho(s) pra TROCAR")
    sys.exit(1 if trocar else 0)

if __name__ == '__main__':
    main()

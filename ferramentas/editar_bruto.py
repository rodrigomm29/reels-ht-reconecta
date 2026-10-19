#!/usr/bin/env python3
"""Edita um bruto importado (ferramentas/importar_brutos.py) e gera a VERSÃO SEM GANCHO, que depois entra
no fluxo normal (novo_lote → agentes → plano → render) como se fosse um Reel publicado.

Lê `dados/brutos/<ID>_edicao.json`:
  manter   [[início, fim, "texto"], ...]  trechos do bruto que ficam, na ordem (o resto sai: erro, conversa, pausa).
           início = start da 1ª palavra, fim = end da última; a folga de respiração é posta aqui (FOLGA_*).
  imagens  [{"arquivo", "em", "dur", "modo"}]  imagem de apoio (ex.: antes/depois); "em" no tempo do BRUTO.
           modo "tela_cheia" (padrão) ou "dividida": a tela divide SÓ enquanto a foto aparece, foto em cima
           (1080×956) e ela embaixo (janela de 964 px a partir de `dividida_y` do _edicao.json); fora disso,
           ela em tela cheia (estilo aprovado pela Fernanda em 18/10/2026).
           Com "para_anuncio": true no JSON, cada foto fica no máximo IMAGEM_MAX (2,5 s): o Meta barra antes/depois
           acima de 3 s em ANÚNCIO. No orgânico não há limite (vale o "dur").
  titulo_tela  texto do "gancho escrito (na tela)" do roteiro: caixa de título no alto nos primeiros TITULO_DUR s
  cenas    [{"arquivo", "em", "dur", "ini"}]   corte de atendimento/procedimento (da pasta cenas/ do bruto) em tela
           cheia, sem o áudio dele, por cima da fala: "em" no tempo do BRUTO, "ini" = de onde o clipe começa.
           Duração entre CENA_MIN e CENA_MAX (1,5–4 s).

Faz:
  - corta e junta os trechos (cada trecho é uma entrada -ss/-t do mesmo arquivo; nada de split→concat),
    com folga antes/depois (emenda de ~0,12 s, o ritmo da edição dela) sem invadir a palavra vizinha;
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
from montar_ht_peles import (camada_legenda, ff, filtro_caminho, png_texto_nativo, ajustar, texto_com_sombra,  # noqa: E402
                              FONTE_LEGENDA, LEGENDA_H)
from PIL import Image as _Img  # noqa: E402
from checar_olhar import perfil, fora, e_fora  # noqa: E402

IMAGEM_MAX = 2.5          # s: regra do Meta pra antes/depois EM ANÚNCIO (< 3 s na tela; 2,5 dá margem); padrão do "dur"
FOLGA_ANTES, FOLGA_DEPOIS = 0.04, 0.08   # s em volta da fala: emenda de ~0,12 s, o ritmo da edição da Fernanda (média 0,14 s, 19/10)
ZOOM_EMENDA, ZOOM_CY = 1.10, 860         # trechos ímpares: enquadramento mais fechado, centrado no rosto
FADE_AUDIO = 0.04
CENA_MIN, CENA_MAX = 1.5, 4.0            # s de cada cena de atendimento na tela
FADE_CENA = 0.08
LEGENDA_Y = 1200          # topo da faixa da legenda (texto em ~1330–1400): abaixo da caixa de título (y≈1130)
FADE_IMG = 0.15
TITULO_DUR, TITULO_CY = 4.0, 330          # título na tela (modo "caixa"): 4 s no alto (abaixo da interface do Instagram)
# ESTILO DA FERNANDA (medido no "Video 1" que ela mesma editou, 19/10/2026): fala acelerada 1,10×; título em texto
# branco sem caixa, grande, centro em y≈375, ~2,7 s na tela; legenda em FRASE (3–5 palavras de uma vez), branca,
# centro em y≈1445. Os padrões vêm do config.env (VELOCIDADE_FALA, LEGENDA_MODO, TITULO_MODO); o _edicao.json
# pode sobrescrever com "velocidade", "legenda_modo" e "titulo_modo".
TITULO_TEXTO_DUR, TITULO_TEXTO_CY, TITULO_TEXTO_TAM = 3.0, 375, 66
FRASE_CY, FRASE_TAM, FRASE_MAX = 1445, 54, 26            # legenda em frase: centro, tamanho, caracteres por frase
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


def png_metade(origem, saida, altura=956, topo=0, cobrir=True):
    """Foto na metade de cima (1080×altura). cobrir=True (aprovado em 19/10): a foto ocupa a metade inteira, na
    largura toda, cortando um pouco do alto e do pé (os rostos ficam); False: foto inteira sobre ela mesma
    desfocada. `topo`: faixa livre no alto (só no modo inteiro)."""
    if cobrir:
        im = Image.open(origem).convert('RGB')
        esc = max(1080 / im.width, altura / im.height)
        im = im.resize((round(im.width * esc), round(im.height * esc)), Image.LANCZOS)
        x = (im.width - 1080) // 2
        y = int((im.height - altura) * 0.35)           # corta mais embaixo que em cima: rosto fica no quadro
        im.crop((x, y, x + 1080, y + altura)).save(saida, quality=95)
        return
    im = Image.open(origem).convert('RGB')
    esc = max(1080 / im.width, altura / im.height)
    fundo = im.resize((int(im.width * esc) + 1, int(im.height * esc) + 1), Image.LANCZOS)
    x, y = (fundo.width - 1080) // 2, (fundo.height - altura) // 2
    fundo = fundo.crop((x, y, x + 1080, y + altura)).filter(ImageFilter.GaussianBlur(30))
    fundo = Image.blend(fundo, Image.new('RGB', fundo.size, (0, 0, 0)), 0.3)
    esc = min(1040 / im.width, (altura - topo - 30) / im.height)
    frente = im.resize((int(im.width * esc), int(im.height * esc)), Image.LANCZOS)
    fundo.paste(frente, ((1080 - frente.width) // 2, topo + (altura - topo - frente.height) // 2))
    fundo.save(saida, quality=95)


def png_titulo_texto(titulo, saida, cy):
    """Título do roteiro como a Fernanda faz: texto branco grande, sem caixa, com sombra suave."""
    img = _Img.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    f, linhas = ajustar(titulo, FONTE_LEGENDA, TITULO_TEXTO_TAM, 48, 900, 3)
    entre = 1.12
    y0 = cy - f.size * entre * len(linhas) / 2
    texto_com_sombra(img, linhas, f, 540, y0, entre, (255, 255, 255), sombra=0.55, raio=10)
    img.save(saida)


def grupos_frase(pals):
    """Palavras → frases de até 4 palavras / FRASE_MAX caracteres, quebrando em pontuação e pausa > 0,5 s."""
    grupos, atual = [], []
    for s, e, t in pals:
        if atual and (len(atual) == 4 or len(' '.join(x[2] for x in atual + [(s, e, t)])) > FRASE_MAX
                      or s - atual[-1][1] > 0.5):
            grupos.append(atual)
            atual = []
        atual.append((s, e, t))
        if t.rstrip()[-1:] in '.?!':
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    return grupos


def camada_frases(pals, total, fps, pasta):
    """Legenda em frase (a frase inteira aparece de uma vez), faixa 1080×1920 com alfa, lista do concat."""
    os.makedirs(pasta, exist_ok=True)
    vazio = os.path.join(pasta, 'vazio.png')
    _Img.new('RGBA', (1080, 1920), (0, 0, 0, 0)).save(vazio)
    grupos = grupos_frase(pals)
    linhas, t, quadro = [], 0.0, 1.0 / fps

    def item(arq, d):
        linhas.append(f"file '{arq}'")
        linhas.append(f"duration {max(quadro, d):.4f}")
    for n, g in enumerate(grupos):
        t0 = max(g[0][0], t)
        t1 = min(grupos[n + 1][0][0] if n + 1 < len(grupos) else g[-1][1] + 0.4, g[-1][1] + 0.6, total)
        if t1 <= t0:
            continue
        if t0 - t > 0.001:
            item(vazio, t0 - t)
        img = _Img.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        texto = ' '.join(x[2] for x in g)
        f, ls = ajustar(texto, FONTE_LEGENDA, FRASE_TAM, 40, 960, 2)
        texto_com_sombra(img, ls, f, 540, FRASE_CY - f.size * 1.1 * len(ls) / 2, 1.1, (255, 255, 255),
                         sombra=0.6, raio=8)
        arq = os.path.join(pasta, f'f{n:04d}.png')
        img.save(arq)
        item(arq, t1 - t0)
        t = t1
    if total - t > 0.001:
        item(vazio, total - t)
    linhas.append(f"file '{vazio}'")
    lista = os.path.join(pasta, 'lista.txt')
    with open(lista, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(linhas) + '\n')
    return lista


def aparar_olhar(manter, bruto, palavras):
    """Ela olhando para a câmera (Vision): apara a ponta de cada trecho em que ela vira o rosto (antes da 1ª
    palavra ou depois da última) e AVISA quando ela vira o rosto durante a fala (aí é trocar de tentativa)."""
    novos, avisos, congelar = [], [], {}
    for n, (a, b, *resto) in enumerate(manter):
        pf = perfil(bruto, a, b, fps=20)
        dentro = [w for w in palavras if a - 0.05 <= w['end'] <= b + 0.05]
        p_ini = dentro[0]['start'] if dentro else a
        p_fim = dentro[-1]['end'] if dentro else b
        # pontas (fora da fala): qualquer giro passa a ser corte; ela de frente é ±10°, então >12° já é o
        # começo do giro (no BR003 ela foi de −19° a −58° em 0,3 s depois de "definido")
        vira = lambda y: y is None or abs(y) > 12
        for t, y in pf:
            if t < p_ini - 0.05 and vira(y):
                a = round(t + 0.05, 3)
        for t, y in pf:
            if t > p_fim - 0.35 and vira(y):
                if t > p_fim + 0.03:
                    b = round(max(t - 0.05, p_fim + 0.03), 3)
                else:                                  # vira ainda terminando a última palavra: congela a
                    congelar[n] = round(t - 0.03 - a, 3)   # imagem de frente e deixa o áudio terminar
                    b = round(p_fim + 0.08, 3)
                break
        fala = [(t, y) for t, y in pf if p_ini <= t <= p_fim and (y is None or abs(y) > 35)]
        if len(fala) >= 2:                             # 0,2 s ou mais com desvio forte durante a fala
            avisos.append(f"trecho {n + 1} ({a:.2f}–{b:.2f}): ela vira o rosto DURANTE a fala em "
                          f"{fala[0][0]:.1f}–{fala[-1][0]:.1f} s do bruto; troque de tentativa")
        novos.append([max(a, 0.0), max(b, a + 0.2), *resto])
    return novos, avisos, congelar


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
    manter, avisos_olhar, congelar = aparar_olhar(manter, bruto, palavras)
    for aviso in avisos_olhar:
        print('  ATENÇÃO olhar:', aviso)
    # VELOCIDADE ANTES DE MONTAR (19/10): cada trecho é acelerado sozinho e tem um número inteiro de quadros na
    # saída, então emendas, fotos, legenda e título caem em quadros exatos. (Acelerando o vídeo pronto, a
    # conversão de quadros desalinhava a emenda em até 1 quadro: sobrava 1 quadro em tela cheia depois da
    # tela dividida, o "tranco" que o Rodrigo viu no BR004 aos 38 s.)
    V = float(ed.get('velocidade', config.VELOCIDADE_FALA))
    quadros = []
    for m in manter:
        nf = max(1, round((m[1] - m[0]) / V * FPS))
        m[1] = round(m[0] + nf * V / FPS, 4)
        quadros.append(nf)
    # CORTE EM L (19/10): quando ela vira o rosto terminando a frase, a IMAGEM passa antes para o trecho
    # seguinte (ela de frente, prestes a falar) e o ÁUDIO termina a frase por baixo. O congelamento, que o
    # Rodrigo viu como corte no BR003 aos 14–15 s, fica só de reserva (sem imagem de frente antes do trecho seguinte).
    vq = list(quadros)                                 # quadros de IMAGEM de cada trecho (o áudio segue `quadros`)
    pre = {}                                           # trecho → s do bruto que a imagem começa antes
    for n, c in list(congelar.items()):
        if n + 1 >= len(manter):
            continue
        nv = max(1, round(c / V * FPS))
        extra = quadros[n] - nv
        recuo = extra * V / FPS
        a2 = manter[n + 1][0]
        antes = perfil(bruto, max(0.0, a2 - recuo - 0.05), a2, fps=20)
        if antes and all(y is not None and abs(y) <= 12 for _, y in antes):
            vq[n], vq[n + 1] = nv, quadros[n + 1] + extra
            pre[n + 1] = recuo
            del congelar[n]
            print(f'  olhar: trecho {n + 1} sai em corte em L: a imagem do trecho {n + 2} entra {recuo:.2f} s antes '
                  f'(ela de frente) e o áudio termina a frase')
    for n, c in congelar.items():                      # reserva: sem imagem de frente para o corte em L
        print(f'  olhar: trecho {n + 1} congela a imagem nos últimos {manter[n][1] - manter[n][0] - c:.2f} s '
              f'(ela vira o rosto terminando a frase)')
    total = sum(b - a for a, b, *_ in manter)          # no tempo do bruto (sem acelerar)
    total_out = sum(quadros) / FPS                     # no tempo da saída
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

    velocidade = V
    pals_out = [(s_ / V, e_ / V, t_) for s_, e_, t_ in pals]
    leg_modo = ed.get('legenda_modo', config.LEGENDA_MODO)
    tit_modo = ed.get('titulo_modo', config.TITULO_MODO)
    # a foto que abre o vídeo junto com o título reserva o alto da tela pro título
    abre_com_foto = any(mapa(i['em']) is not None and mapa(i['em']) < TITULO_TEXTO_DUR and i.get('modo') == 'dividida'
                        for i in ed.get('imagens', []))
    # legenda (faixa com alfa pré-renderizada, como na tela dividida)
    if leg_modo == 'frase':
        lista = camada_frases(pals_out, total_out, FPS, os.path.join(tmp, 'legenda'))
        leg_y = 0
    else:
        lista = camada_legenda(pals_out, total_out, FPS, os.path.join(tmp, 'legenda'))
        leg_y = LEGENDA_Y
    legenda = os.path.join(tmp, 'legenda', 'legenda.mov')
    ff(['-f', 'concat', '-safe', '0', '-i', lista, '-t', f'{total_out:.3f}', '-vf', f'fps={FPS},format=argb',
        '-c:v', 'qtrle', legenda])

    entradas, f = [], []
    for n, (a, b, *_) in enumerate(manter):
        va = a - pre.get(n, 0.0)                       # imagem pode começar antes (corte em L)
        entradas += ['-ss', f'{va:.3f}', '-t', f'{b - va:.3f}', '-i', bruto]
        d = b - a
        quadro = ''
        if n % 2:
            z = ZOOM_EMENDA
            quadro = (f",scale={round(1080 * z / 2) * 2}:{round(1920 * z / 2) * 2},"
                      f"crop=1080:1920:{round(1080 * (z - 1) / 2)}:{round(ZOOM_CY * (z - 1))}")
        congela = ''
        if n in congelar:                              # imagem para no último quadro de frente
            c = congelar[n]
            congela = f",trim=end={c:.3f},tpad=stop_mode=clone:stop_duration={d - c + 0.05:.3f},trim=end={d:.3f}"
        f.append(f"[{n}:v]fps={FPS}{quadro}{congela},setsar=1,setpts=(PTS-STARTPTS)/{V},fps={FPS},"
                 f"trim=end_frame={vq[n]},setpts=PTS-STARTPTS[v{n}]")
        f.append(f"[{n}:a]atrim=start={a - va:.4f},aresample=48000,asetpts=PTS-STARTPTS,afade=t=in:d={FADE_AUDIO},"
                 f"afade=t=out:st={d - FADE_AUDIO:.3f}:d={FADE_AUDIO},atempo={V},"
                 f"atrim=end={quadros[n] / FPS:.4f},apad=whole_dur={quadros[n] / FPS:.4f}[a{n}]")
    f.append(''.join(f'[v{n}]' for n in range(len(manter))) + f"concat=n={len(manter)}:v=1:a=0[cv]")
    f.append(''.join(f'[a{n}]' for n in range(len(manter))) + f"concat=n={len(manter)}:v=0:a=1[ca]")
    ultimo = 'cv'
    for k, c in enumerate(ed.get('cenas', [])):
        t0 = mapa(c['em'])
        if t0 is None:
            raise SystemExit(f"cena {k}: 'em'={c['em']} fora dos trechos mantidos")
        t0 /= V
        arq = os.path.join(config.PROJETO, c['arquivo'])
        ini = float(c.get('ini', 0))
        dur_arq = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                        arq], capture_output=True, text=True).stdout)
        dur = max(CENA_MIN, min(float(c.get('dur', 3.0)), CENA_MAX, dur_arq - ini, total_out - t0))
        i = len(manter) + k
        entradas += ['-ss', f'{ini:.3f}', '-t', f'{dur:.3f}', '-i', arq]
        f.append(f"[{i}:v]fps={FPS},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
                 f"format=rgba,fade=t=in:d={FADE_CENA}:alpha=1,fade=t=out:st={dur - FADE_CENA:.3f}:d={FADE_CENA}:alpha=1,"
                 f"setpts=PTS-STARTPTS+{t0:.3f}/TB[ce{k}]")
        f.append(f"[{ultimo}][ce{k}]overlay=0:0:eof_action=pass:format=auto[oc{k}]")
        ultimo = f'oc{k}'
        print(f'  cena {k}: {t0:.2f}–{t0 + dur:.2f} s na saída ({dur:.1f} s) {os.path.basename(arq)}')
    n_cenas = len(ed.get('cenas', []))
    emendas, acum = [], 0                              # emendas entre trechos, em quadros exatos da saída
    for nf in vq[:-1]:
        acum += nf
        emendas.append(acum / FPS)
    janelas_foto = []                                  # com foto na tela, o maior rosto pode ser o da paciente
    for k, img in enumerate(ed.get('imagens', [])):
        t0 = mapa(img['em'])
        if t0 is None:
            raise SystemExit(f"imagem {k}: 'em'={img['em']} fora dos trechos mantidos")
        t0 /= V                                        # tempo da saída
        dur = float(img.get('dur', IMAGEM_MAX)) / V
        # foto que começa/termina perto de uma emenda passa a começar/terminar NA emenda: senão sobram poucos
        # quadros dela em tela cheia entre a foto e o corte, e parece um tranco (Rodrigo, BR004 aos 38 s, 19/10)
        perto = [e for e in emendas if abs(e - (t0 + dur)) < 0.6]
        if perto:
            dur = perto[0] - t0
        perto = [e for e in [0.0] + emendas if abs(e - t0) < 0.6 and e < t0 + dur - 1.0]   # 0 = início do vídeo
        if perto:
            dur, t0 = dur + (t0 - perto[0]), perto[0]
        if ed.get('para_anuncio'):                 # regra do Meta, só para anúncio
            dur = min(dur, IMAGEM_MAX)
        png = os.path.join(tmp, f'imagem{k}.jpg')
        i = len(manter) + n_cenas + k
        modo = img.get('modo', 'tela_cheia')
        if modo == 'dividida':
            png_metade(os.path.join(config.PROJETO, img['arquivo']), png)
            y_ela = int(ed.get('dividida_y', 300))
            janela = f"between(t,{t0:.3f},{t0 + dur:.3f})"
            # as duas metades ligam e desligam pela MESMA janela de tempo (antes a foto saía pelo fim da
            # entrada e a janela de baixo pelo enable: 1 quadro com o rosto dela duas vezes, 19/10)
            entradas += ['-loop', '1', '-framerate', str(FPS), '-t', f'{dur + 0.5:.3f}', '-i', png]
            f.append(f"[{ultimo}]split[sa{k}][sb{k}]")
            f.append(f"[sb{k}]crop=1080:964:0:{y_ela}[ela{k}]")
            f.append(f"[sa{k}][ela{k}]overlay=0:956:enable='{janela}'[dv{k}]")
            f.append(f"[{i}:v]format=rgba,setpts=PTS-STARTPTS+{t0:.3f}/TB[im{k}]")
            f.append(f"[dv{k}][im{k}]overlay=0:0:enable='{janela}':eof_action=pass:format=auto[ov{k}]")
        else:
            png_imagem(os.path.join(config.PROJETO, img['arquivo']), png)
            entradas += ['-loop', '1', '-framerate', str(FPS), '-t', f'{dur:.3f}', '-i', png]
            f.append(f"[{i}:v]format=rgba,fade=t=in:d={FADE_IMG}:alpha=1,fade=t=out:st={dur - FADE_IMG:.3f}:d={FADE_IMG}:alpha=1,"
                     f"setpts=PTS-STARTPTS+{t0:.3f}/TB[im{k}]")
            f.append(f"[{ultimo}][im{k}]overlay=0:0:eof_action=pass:format=auto[ov{k}]")
        ultimo = f'ov{k}'
        print(f'  imagem {k} ({modo}): {t0:.2f}–{t0 + dur:.2f} s na saída ({dur:.1f} s)')
        janelas_foto.append((t0, t0 + dur))
    f.append(f"movie={filtro_caminho(legenda)},fps={FPS},format=rgba,setpts=PTS-STARTPTS[lg]")
    if abre_com_foto and ed.get('titulo_tela'):
        print('  título na tela: não entra (a foto do caso abre o vídeo em tela dividida; aprovado em 19/10)')
    if ed.get('titulo_tela') and not abre_com_foto:
        pt = os.path.join(tmp, 'titulo.png')
        if tit_modo == 'texto':
            png_titulo_texto(ed['titulo_tela'], pt, TITULO_TEXTO_CY)
            tdur = TITULO_TEXTO_DUR / V
        else:
            png_texto_nativo(ed['titulo_tela'], pt, TITULO_CY)
            tdur = TITULO_DUR / V
        f.append(f"[{ultimo}][lg]overlay=0:{leg_y}:eof_action=pass:format=auto[comleg]")
        f.append(f"movie={filtro_caminho(pt)},loop=-1:1,fps={FPS},format=rgba,trim=duration={tdur},"
                 f"fade=t=out:st={tdur - 0.2}:d=0.2:alpha=1,setpts=PTS-STARTPTS[tit]")
        f.append("[comleg][tit]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v1]")
    else:
        f.append(f"[{ultimo}][lg]overlay=0:{leg_y}:eof_action=pass:format=auto,format=yuv420p[v1]")
    f.append("[v1]null[vout]")
    f.append("[ca]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    final_t = total_out
    ff([*entradas, '-filter_complex', ';'.join(f), '-map', '[vout]', '-map', '[aout]', '-t', f'{final_t:.3f}',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS),
        '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', saida])

    espaco = [{**w, 'start': round(w['start'] / velocidade, 3), 'end': round(w['end'] / velocidade, 3)} for w in espaco]
    json.dump({'language_code': tr.get('language_code', 'por'), 'text': texto, 'words': espaco,
               'origem': f'remapeada de {info["video"]} por editar_bruto.py'},
              open(saida.replace('/videos/', '/transcricoes/').replace('.mp4', '.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    final = os.path.join(config.SAIDA_DIR, 'brutos', vid, 'sem gancho', f'{vid} sem gancho.mp4')
    os.makedirs(os.path.dirname(final), exist_ok=True)
    shutil.copyfile(saida, final)
    print(f'{vid}: {len(manter)} trechos, {final_t:.1f} s (fala {velocidade}×) → {saida}\n  sem gancho: {final}')
    fotos_saida = [(a - 0.1, b + 0.1) for a, b in janelas_foto]
    sobra = [(x, y) for x, y in fora(final)            # conferência final: o vídeo pronto, inteiro
             if not any(x < b and y > a for a, b in fotos_saida)]
    print('  olhar: ok, de frente pra câmera o vídeo todo' if not sobra else
          '  ATENÇÃO olhar no vídeo final: ' + ', '.join(f'{x:.1f}–{y:.1f} s' for x, y in sobra))


if __name__ == '__main__':
    main()

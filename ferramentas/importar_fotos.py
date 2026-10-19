#!/usr/bin/env python3
"""Importa os posts de foto (antes/depois) que chegam pela pasta compartilhada e monta um lote pro carrossel.

Cada subpasta de POSTS_FOTOS_DIR (padrão: "Posts Fernanda" no iCloud Drive) é UM post:
  - as fotos (.jpg/.jpeg/.png/.heic/.webp) entram no carrossel em ordem: nome com "antes" primeiro, "depois" em
    seguida, o resto pelo nome (IMG_9200, IMG_9201...); até 10 fotos (limite do Instagram);
  - `legenda.txt` (opcional) é a legenda do post; sem ela, o lote sai com legenda.txt vazio pra escrever depois;
  - subpasta que começa com "_" é ignorada (ex.: "_modelo").

Para cada post novo, este script:
  1. converte HEIC com o sips do macOS e gira a foto conforme o EXIF;
  2. deixa cada foto em 1080×1350 (4:5, o maior formato do feed): foto quase 4:5 é só recortada; o resto cabe
     inteiro, com o fundo preenchido pela própria foto desfocada (nada do rosto é cortado);
  3. grava JPEG sem metadado nenhum (sem GPS, sem data, sem aparelho: é foto de paciente);
  4. com --lado-a-lado e exatamente 2 fotos, põe na frente uma capa com ANTES | DEPOIS lado a lado;
  5. grava tudo em FOTOS_DIR/<lote>/<Pnn>/ (01.jpg, 02.jpg..., legenda.txt), o `lote.json` e uma folha de
     conferência (_conferencia.jpg) com todos os posts do lote.
Os originais nunca são alterados. Pasta já importada (em qualquer lote) é pulada; --de-novo NOME refaz uma.

Depois: escreva/revise as legendas vazias, olhe a _conferencia.jpg e rode
  python3 publicar/fila.py montar-fotos <lote>
  python3 publicar/publer_postar.py postar <lote> --rede instagram --inicio "AAAA-MM-DD HH:MM" --horarios "12:00" --simular

uso:
  python3 ferramentas/importar_fotos.py FOTOS-SEM44                    # todas as pastas novas
  python3 ferramentas/importar_fotos.py FOTOS-SEM44 --lado-a-lado      # com capa antes|depois
  python3 ferramentas/importar_fotos.py FOTOS-SEM44 --so "olheiras"    # só esta pasta
  python3 ferramentas/importar_fotos.py FOTOS-SEM44 --de-novo "olheiras"
"""
import argparse, datetime as dt, json, os, re, subprocess, sys, tempfile, unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps  # noqa: E402

ENTRADA = config.POSTS_FOTOS_DIR
SAIDA = config.FOTOS_DIR
REGISTRO = os.path.join(SAIDA, '_importados.json')
EXT = ('.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp')
LARG, ALT = 1080, 1350               # 4:5
TOLERANCIA = 0.04                    # até 4% fora de 4:5 recorta em vez de preencher
MAX_FOTOS = 10                       # doc Publer/Instagram: até 10 por carrossel
LIMITE_BYTES = 8 * 1000 * 1000       # doc Publer/Instagram: 8 MB por foto
NOMES_LEGENDA = ('legenda.txt', 'legenda.md', 'Legenda.txt')


def nfc(s):
    return unicodedata.normalize('NFC', s)


def chave_ordem(nome):
    n = nfc(nome).lower()
    grupo = 0 if 'antes' in n else 1 if 'depois' in n else 2
    partes = [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', n)]
    return (grupo, partes)


def baixar_do_icloud(pasta):
    """Arquivo do iCloud ainda não baixado aparece como ".nome.icloud". Pede o download e devolve os pendentes."""
    pendentes = [f for f in os.listdir(pasta) if f.startswith('.') and f.endswith('.icloud')]
    for f in pendentes:
        subprocess.run(['brctl', 'download', os.path.join(pasta, f)], capture_output=True)
    return [f[1:-len('.icloud')] for f in pendentes]


def abrir(caminho, tmp):
    """Abre a foto já girada pelo EXIF, em RGB. HEIC passa pelo sips (o Pillow daqui não lê HEIC)."""
    if caminho.lower().endswith(('.heic', '.heif')):
        destino = os.path.join(tmp, os.path.basename(caminho) + '.jpg')
        r = subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '100', caminho, '--out', destino],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(destino):
            raise RuntimeError(f'o sips não converteu {os.path.basename(caminho)}: {r.stderr.strip()[:200]}')
        caminho = destino
    im = Image.open(caminho)
    im = ImageOps.exif_transpose(im)
    return im.convert('RGB')


def cobrir(im, larg, alt):
    """Escala até cobrir larg×alt e recorta no centro."""
    return ImageOps.fit(im, (larg, alt), Image.LANCZOS, centering=(0.5, 0.5))


def em_4x5(im):
    w, h = im.size
    alvo = LARG / ALT
    if abs(w / h - alvo) / alvo <= TOLERANCIA:
        return cobrir(im, LARG, ALT)
    fundo = cobrir(im, LARG, ALT).filter(ImageFilter.GaussianBlur(40))
    fundo = Image.blend(fundo, Image.new('RGB', fundo.size, (0, 0, 0)), 0.25)
    escala = min(LARG / w, ALT / h)
    nova = im.resize((max(1, round(w * escala)), max(1, round(h * escala))), Image.LANCZOS)
    fundo.paste(nova, ((LARG - nova.width) // 2, (ALT - nova.height) // 2))
    return fundo


def fonte(tam):
    try:
        return ImageFont.truetype(config.FONTE_LEGENDA, tam)
    except OSError:
        return ImageFont.load_default()


def etiqueta(tela, texto, cx, y):
    d = ImageDraw.Draw(tela)
    f = fonte(44)
    x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=f)
    w, h = x1 - x0, y1 - y0
    pad = 18
    caixa = (cx - w // 2 - pad, y, cx + w // 2 + pad, y + h + 2 * pad)
    d.rounded_rectangle(caixa, radius=14, fill=(255, 255, 255))
    d.text((cx - w // 2 - x0, y + pad - y0), texto, font=f, fill=(20, 20, 20))


def capa_lado_a_lado(antes, depois):
    """ANTES | DEPOIS em 1080×1350, cada metade 538 px recortada no centro, com um fio branco no meio."""
    tela = Image.new('RGB', (LARG, ALT), (255, 255, 255))
    meia = (LARG - 4) // 2
    tela.paste(cobrir(antes, meia, ALT), (0, 0))
    tela.paste(cobrir(depois, meia, ALT), (LARG - meia, 0))
    etiqueta(tela, 'ANTES', meia // 2, ALT - 130)
    etiqueta(tela, 'DEPOIS', LARG - meia // 2, ALT - 130)
    return tela


def salvar_jpeg(im, destino):
    """JPEG sem EXIF/GPS. Se passar de 8 MB (não deve, em 1080×1350), baixa a qualidade."""
    for q in (92, 85, 75):
        im.save(destino, 'JPEG', quality=q, optimize=True, progressive=True)
        if os.path.getsize(destino) <= LIMITE_BYTES:
            return
    raise RuntimeError(f'{destino} passou de 8 MB mesmo com qualidade 75')


def ler_json(caminho, padrao):
    if not os.path.exists(caminho):
        return padrao
    with open(caminho, encoding='utf-8') as f:
        return json.load(f)


def gravar_json(caminho, dado):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(caminho) + '.', suffix='.part', dir=os.path.dirname(caminho))
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(dado, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def folha_conferencia(lote_dir, posts):
    """Uma linha por post: id + nome da pasta, as fotos do carrossel em miniatura, e se a legenda está vazia."""
    mini_w, mini_h, margem, topo = 216, 270, 16, 56
    colunas = max(len(p['fotos']) for p in posts)
    W = margem + colunas * (mini_w + margem)
    W = max(W, 700)
    H = margem + len(posts) * (topo + mini_h + margem)
    folha = Image.new('RGB', (W, H), (245, 245, 245))
    d = ImageDraw.Draw(folha)
    f = fonte(26)
    y = margem
    for p in posts:
        leg = open(p['legenda'], encoding='utf-8').read().strip() if os.path.exists(p['legenda']) else ''
        aviso = '' if leg else '   (SEM LEGENDA)'
        d.text((margem, y + 10), f'{p["id"]}  {p["nome"]}{aviso}', font=f, fill=(200, 0, 0) if aviso else (20, 20, 20))
        x = margem
        for foto in p['fotos']:
            with Image.open(foto) as im:
                folha.paste(im.resize((mini_w, mini_h), Image.LANCZOS), (x, y + topo))
            x += mini_w + margem
        y += topo + mini_h + margem
    destino = os.path.join(lote_dir, '_conferencia.jpg')
    folha.save(destino, 'JPEG', quality=85)
    return destino


def importar_post(origem, post_dir, lado_a_lado):
    fotos_orig = sorted((f for f in os.listdir(origem) if f.lower().endswith(EXT) and not f.startswith('.')),
                        key=chave_ordem)
    if not fotos_orig:
        raise RuntimeError('nenhuma foto na pasta')
    total = len(fotos_orig) + (1 if lado_a_lado and len(fotos_orig) == 2 else 0)
    if total > MAX_FOTOS:
        raise RuntimeError(f'{total} fotos; o carrossel do Instagram aceita até {MAX_FOTOS}')
    os.makedirs(post_dir, exist_ok=True)
    for velho in os.listdir(post_dir):                       # --de-novo: refaz do zero
        if velho.endswith('.jpg'):
            os.remove(os.path.join(post_dir, velho))
    with tempfile.TemporaryDirectory() as tmp:
        imagens = [abrir(os.path.join(origem, f), tmp) for f in fotos_orig]
    slides = [em_4x5(im) for im in imagens]
    capa = False
    if lado_a_lado:
        if len(imagens) == 2:
            slides.insert(0, capa_lado_a_lado(imagens[0], imagens[1]))
            capa = True
        else:
            print(f'  aviso: --lado-a-lado só vale com 2 fotos (antes e depois); esta pasta tem {len(imagens)}')
    saidas = []
    for i, s in enumerate(slides, 1):
        destino = os.path.join(post_dir, f'{i:02d}.jpg')
        salvar_jpeg(s, destino)
        saidas.append(destino)
    leg_orig = next((os.path.join(origem, n) for n in NOMES_LEGENDA if os.path.exists(os.path.join(origem, n))), None)
    leg_dest = os.path.join(post_dir, 'legenda.txt')
    texto = open(leg_orig, encoding='utf-8').read().strip() if leg_orig else ''
    if texto or not os.path.exists(leg_dest):                 # não apaga legenda já escrita aqui num --de-novo
        with open(leg_dest, 'w', encoding='utf-8') as f:
            f.write(texto + ('\n' if texto else ''))
    return {'fotos': saidas, 'legenda': leg_dest, 'origem_fotos': fotos_orig, 'capa_lado_a_lado': capa}


def main():
    ap = argparse.ArgumentParser(description='importa posts de foto (antes/depois) para um lote de carrossel')
    ap.add_argument('lote', help='nome do lote, que vira o nome da fila (ex.: FOTOS-SEM44)')
    ap.add_argument('--so', action='append', default=[], metavar='PASTA', help='só esta(s) subpasta(s)')
    ap.add_argument('--de-novo', action='append', default=[], metavar='PASTA', help='reimporta esta subpasta')
    ap.add_argument('--lado-a-lado', action='store_true', help='capa ANTES | DEPOIS na frente (posts com 2 fotos)')
    a = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', a.lote):
        sys.exit('nome do lote: só letras, números, - e _ (ex.: FOTOS-SEM44)')
    if not os.path.isdir(ENTRADA):
        sys.exit(f'a pasta de entrada não existe: {ENTRADA}\n(crie no iCloud Drive ou ajuste POSTS_FOTOS_DIR no config.env)')

    registro = ler_json(REGISTRO, {})
    lote_dir = os.path.join(SAIDA, a.lote)
    lote_json = os.path.join(lote_dir, 'lote.json')
    lote = ler_json(lote_json, {'lote': a.lote, 'criado': dt.datetime.now().isoformat(timespec='seconds'), 'posts': []})
    por_nome = {p['nome']: p for p in lote['posts']}
    so = {nfc(s) for s in a.so}
    de_novo = {nfc(s) for s in a.de_novo}

    pastas = sorted((nfc(d) for d in os.listdir(ENTRADA)
                     if os.path.isdir(os.path.join(ENTRADA, d)) and not d.startswith(('_', '.'))), key=chave_ordem)
    if so:
        faltam = so - set(pastas)
        if faltam:
            sys.exit(f'não achei em {ENTRADA}: {sorted(faltam)}')
        pastas = [p for p in pastas if p in so]
    novos, pulados, erros = [], [], []
    for nome in pastas:
        origem = next(os.path.join(ENTRADA, d) for d in os.listdir(ENTRADA) if nfc(d) == nome)
        ja = registro.get(nome)
        if ja and nome not in de_novo:
            pulados.append(f'{nome} (já no lote {ja["lote"]} como {ja["id"]})')
            continue
        if ja and ja['lote'] != a.lote:
            sys.exit(f'"{nome}" foi importada no lote {ja["lote"]}; refaça lá: importar_fotos.py {ja["lote"]} --de-novo "{nome}"')
        baixando = baixar_do_icloud(origem)
        if baixando:
            erros.append(f'{nome}: {len(baixando)} arquivo(s) ainda baixando do iCloud ({", ".join(baixando[:3])}); '
                         'rode de novo daqui a pouco')
            continue
        if nome in por_nome:
            pid = por_nome[nome]['id']
        else:
            usados = [int(p['id'][1:]) for p in lote['posts']]
            pid = f'P{(max(usados) + 1) if usados else 1:02d}'
        print(f'[{pid}] {nome}', flush=True)
        try:
            dados = importar_post(origem, os.path.join(lote_dir, pid), a.lado_a_lado)
        except Exception as e:
            erros.append(f'{nome}: {e}')
            continue
        post = {'id': pid, 'nome': nome, 'origem': origem, **dados,
                'importado': dt.datetime.now().isoformat(timespec='seconds')}
        if nome in por_nome:
            lote['posts'] = [post if p['nome'] == nome else p for p in lote['posts']]
        else:
            lote['posts'].append(post)
        por_nome[nome] = post
        registro[nome] = {'lote': a.lote, 'id': pid}
        gravar_json(lote_json, lote)
        gravar_json(REGISTRO, registro)
        n = len(dados['fotos'])
        print(f'  {n} foto(s)' + (' (capa antes|depois + ' + str(n - 1) + ')' if dados['capa_lado_a_lado'] else '') +
              ('' if open(dados['legenda'], encoding='utf-8').read().strip() else '; SEM LEGENDA'))
        novos.append(pid)

    if pulados:
        print('\njá importadas (puladas): ' + '; '.join(pulados))
    if erros:
        print('\nNÃO importadas:\n  ' + '\n  '.join(erros))
    if not lote['posts']:
        print('\nnenhum post no lote.')
        return 1 if erros else 0
    folha = folha_conferencia(lote_dir, lote['posts'])
    sem_leg = [p['id'] for p in lote['posts']
               if not open(p['legenda'], encoding='utf-8').read().strip()]
    print(f'\nlote {a.lote}: {len(lote["posts"])} post(s) ({len(novos)} novo(s) nesta rodada) em {lote_dir}')
    print(f'conferência: {folha}')
    if sem_leg:
        print(f'sem legenda ainda: {", ".join(sem_leg)} (escreva em {lote_dir}/<id>/legenda.txt)')
    print(f'próximo passo: python3 publicar/fila.py montar-fotos {a.lote}')
    return 1 if erros else 0


if __name__ == '__main__':
    sys.exit(main())

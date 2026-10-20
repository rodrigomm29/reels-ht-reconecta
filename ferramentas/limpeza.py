#!/usr/bin/env python3
"""Limpeza semanal: libera espaço sem arriscar o que ainda vai ao ar.

Rode 1× por semana. Por padrão SÓ MOSTRA o que sairia e quanto espaço libera; com --apagar, manda tudo para a
LIXEIRA do Mac (dá pra recuperar; o espaço volta quando você esvazia a Lixeira).

O que sai:
  1. Sobras de trabalho, sempre: dados/brutos/_tmp, áudio extraído para transcrever (dados/audio/*.wav,
     dados/brutos/_soltos/**/*.wav), saida/**/_peles_tmp e saida/**/_amostra.
  2. Vídeos de post JÁ PUBLICADOS: para cada fila em publicar/filas, pergunta ao Publer quais posts já foram ao
     ar e tira o vídeo daquele post (e todas as cópias/atalhos dele dentro de saida/, inclusive as pastas
     aprovar/). Post agendado, com erro ou não encontrado NUNCA sai.
  3. Descartados: caminhos listados em planos/_descartados.json (testes reprovados etc.).

Nunca toca em: dados/videos (só o que estiver em _descartados.json), dados/transcricoes, dados/brutos/*.json,
planos/, legendas/, publicar/filas/, brutos/entrada/ (só o que estiver em _descartados.json) e a pasta do iCloud.

uso:
  python3 ferramentas/limpeza.py              # mostra
  python3 ferramentas/limpeza.py --apagar     # manda para a Lixeira
"""
import argparse, datetime as dt, glob, json, os, shutil, sys

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, 'publicar'))
import config  # noqa: E402

LIXEIRA = os.path.expanduser('~/.Trash')
PROTEGIDOS = [os.path.join(config.REELS_BASE, 'transcricoes'), os.path.join(AQUI, 'planos'),
              os.path.join(AQUI, 'legendas'), os.path.join(AQUI, 'publicar', 'filas')]


def tamanho(caminho, contados):
    """Bytes que voltam: cada arquivo (inode) conta uma vez só, mesmo com vários links/atalhos."""
    arquivos = [caminho] if os.path.isfile(caminho) else [
        os.path.join(r, a) for r, _, arqs in os.walk(caminho) for a in arqs]
    total = 0
    for p in arquivos:
        if os.path.islink(p):
            continue
        st = os.stat(p)
        if st.st_ino not in contados:
            contados.add(st.st_ino)
            total += st.st_size
    return total


def legivel(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.0f} {u}'
        n /= 1024
    return f'{n:.1f} TB'


def protegido(caminho):
    c = os.path.realpath(caminho)
    return any(c == p or c.startswith(p + os.sep) for p in map(os.path.realpath, PROTEGIDOS))


def sobras():
    pad = [os.path.join(config.REELS_BASE, 'brutos', '_tmp'),
           *glob.glob(os.path.join(config.REELS_BASE, 'audio', '*.wav')),
           *glob.glob(os.path.join(config.REELS_BASE, 'brutos', '_soltos', '**', '*.wav'), recursive=True),
           *glob.glob(os.path.join(config.SAIDA_DIR, '**', '_peles_tmp'), recursive=True),
           *glob.glob(os.path.join(config.SAIDA_DIR, '**', '_amostra'), recursive=True)]
    return [p for p in pad if os.path.exists(p)]


def publicados_no_publer():
    """ids dos posts que o Publer diz que JÁ foram publicados (últimos 120 dias)."""
    import publer_postar as pp
    cli = pp.Cliente(pp.obter_chave(), base=pp.BASE)
    cli.workspace = pp.resolver_workspace(cli, None, True)
    de = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    ate = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    ids = set()
    for estado in ('published', 'published_posted'):
        for pagina in pp.paginas_posts(cli, {'state': estado, 'from': de, 'to': ate}):
            ids.update(p.get('id') for p in pagina if p.get('id'))
    return ids


def copias_em_saida(arquivo):
    """O arquivo e todos os links físicos dele dentro de saida/ (aprovar/, cópia solta, pasta do vídeo)."""
    try:
        ino = os.stat(arquivo).st_ino
    except FileNotFoundError:
        return []
    achados = []
    for raiz, _, arqs in os.walk(config.SAIDA_DIR):
        for a in arqs:
            p = os.path.join(raiz, a)
            try:
                if os.stat(p).st_ino == ino:
                    achados.append(p)
            except FileNotFoundError:
                pass
    # cópia solta com o mesmo nome na pasta acima (organizar_organico.py faz cópia, não link)
    solta = os.path.join(os.path.dirname(os.path.dirname(arquivo)), os.path.basename(arquivo))
    if os.path.isfile(solta) and solta not in achados:
        achados.append(solta)
    return achados


def videos_publicados(ids_publicados):
    saem, mantidos = [], 0
    for fila in sorted(glob.glob(os.path.join(AQUI, 'publicar', 'filas', '*.json'))):
        try:
            d = json.load(open(fila, encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for item in d.get('itens', []):
            estados = item.get('estado', {})
            pids = [e.get('post_id') for e in estados.values() if isinstance(e, dict) and e.get('post_id')]
            if not pids:
                continue
            if all(p in ids_publicados for p in pids) and item.get('video'):
                for c in copias_em_saida(item['video']):
                    saem.append((c, f"{os.path.basename(fila)[:-5]} · {item['id']} (publicado)"))
            else:
                mantidos += 1
    return saem, mantidos


def descartados():
    arq = os.path.join(AQUI, 'planos', '_descartados.json')
    if not os.path.exists(arq):
        return []
    lista = json.load(open(arq, encoding='utf-8')).get('caminhos', [])
    return [(os.path.join(AQUI, p), 'descartado') for p in lista if os.path.exists(os.path.join(AQUI, p))]


def para_lixeira(caminho):
    destino = os.path.join(LIXEIRA, os.path.basename(caminho.rstrip('/')))
    if os.path.exists(destino):
        destino += dt.datetime.now().strftime(' %Y%m%d-%H%M%S')
    shutil.move(caminho, destino)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apagar', action='store_true', help='manda para a Lixeira (sem isto, só mostra)')
    ap.add_argument('--sem-publer', action='store_true', help='não consulta o Publer (pula os vídeos publicados)')
    a = ap.parse_args()

    itens = [(p, 'sobra de trabalho') for p in sobras()] + descartados()
    mantidos = None
    if not a.sem_publer:
        try:
            ids = publicados_no_publer()
            saem, mantidos = videos_publicados(ids)
            itens += saem
        except Exception as e:  # sem rede/chave: não arrisca nada com os vídeos de post
            print(f'(Publer indisponível: {e}; os vídeos de post ficam)')
    vistos, lista, contados = set(), [], set()
    itens.sort(key=lambda x: len(os.path.realpath(x[0])))      # pasta antes do que está dentro dela
    for p, motivo in itens:
        r = os.path.realpath(p)
        if r in vistos or protegido(p) or not os.path.exists(p):
            continue
        if any(r.startswith(v + os.sep) for v in vistos):
            continue
        vistos.add(r)
        lista.append((p, motivo, tamanho(p, contados)))
    # espaço que de fato volta: arquivos com vários links só liberam quando TODOS os links saem
    total = sum(t for _, _, t in lista)
    for p, motivo, t in sorted(lista, key=lambda x: -x[2]):
        print(f'{legivel(t):>8}  {os.path.relpath(p, AQUI)}   [{motivo}]')
    print(f'\n{len(lista)} item(ns), ~{legivel(total)}'
          + (f'; {mantidos} vídeo(s) de post ainda não publicado(s) ficam' if mantidos is not None else ''))
    if not lista:
        return
    if not a.apagar:
        print('(só mostrando; rode com --apagar para mandar para a Lixeira)')
        return
    for p, _, _ in lista:
        para_lixeira(p)
    print(f'feito: {len(lista)} item(ns) na Lixeira. O espaço volta quando você esvaziar a Lixeira.')


if __name__ == '__main__':
    main()

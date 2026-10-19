#!/usr/bin/env python3
"""Monta a pasta de APROVAÇÃO de uma fila: uma subpasta por dia de postagem, com os vídeos daquele dia na
ordem e no horário em que vão ao ar, pra assistir antes de agendar.

  saida/SEM43/aprovar/
    _aprovar.md                         checklist da semana: dia, horário, título, gancho, legenda, [ ] aprovado
    1 · seg 19-10/
      12h00 · VD001_A · Olhar cansado mesmo depois de dormir bem.mp4
      12h00 · VD001_A · legenda.txt
      12h00 · VD001_A · tira.png        (5 quadros do vídeo, da _conferencia)
      ...

Os vídeos são LINKS FÍSICOS (hard links) dos arquivos da fila: não ocupam espaço a mais, e o que você assiste
é exatamente o que vai pro Publer. Apagar a pasta aprovar/ não mexe na fila. Rode de novo depois de um
re-render: a pasta é refeita do zero.

A grade (início, quantos por dia, intervalo) é a mesma que você vai passar ao publer_postar.py.

uso:
  python3 ferramentas/pasta_aprovacao.py SEM43-segunda-ht --inicio "2026-10-19 12:00" --por-dia 3 --intervalo 180
"""
import argparse, datetime, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from checar_fotos import trechos_parados  # noqa: E402

DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
PROIBIDOS = '/:\\'
FOTO_MAX = 2.5        # regra do Meta, só para ANÚNCIO: foto de antes/depois no máximo 2,5 s na tela


def limpo(texto):
    return ''.join('-' if c in PROIBIDOS else c for c in texto).strip()


def ligar(origem, destino):
    try:
        os.link(origem, destino)
    except OSError:                    # outro disco: cai pra cópia
        shutil.copyfile(origem, destino)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fila', help='nome da fila em publicar/filas (ex.: SEM43-segunda-ht)')
    ap.add_argument('--inicio', required=True, help='"AAAA-MM-DD HH:MM" do 1º post')
    ap.add_argument('--por-dia', type=int, default=3)
    ap.add_argument('--intervalo', type=int, default=180, help='minutos entre os posts do mesmo dia')
    ap.add_argument('--anuncio', action='store_true', help='fila de anúncio: barra foto parada acima de 2,5 s')
    a = ap.parse_args()

    fila = json.load(open(os.path.join(config.PROJETO, 'publicar', 'filas', f'{a.fila}.json'), encoding='utf-8'))
    plano = json.load(open(fila['plano'], encoding='utf-8'))
    hooks = {f"{v['vd']}_{k}": (v, h) for v in plano['videos'] for k, h in v['hooks'].items()}
    semana = a.fila.split('-')[0]
    raiz = os.path.join(config.SAIDA_DIR, semana, 'aprovar')
    if os.path.isdir(raiz):
        shutil.rmtree(raiz)            # só links e cópias desta pasta; os vídeos da fila ficam intactos
    os.makedirs(raiz)
    conf = os.path.join(plano['destino'], '_conferencia')

    inicio = datetime.datetime.strptime(a.inicio, '%Y-%m-%d %H:%M')
    md = [f'# Aprovação · {a.fila}', '',
          f'{len(fila["itens"])} vídeos, {a.por_dia} por dia, de {a.intervalo} em {a.intervalo} min, '
          f'a partir de {DIAS[inicio.weekday()]} {inicio:%d/%m %H:%M}.', '',
          'Marque [x] no que está aprovado. O que precisar de ajuste: escreva o motivo na linha.', '']
    dia_atual, alerta = None, []
    for n, item in enumerate(fila['itens']):
        d, k = divmod(n, a.por_dia)
        quando = inicio + datetime.timedelta(days=d, minutes=k * a.intervalo)
        pasta_dia = os.path.join(raiz, f'{d + 1} · {DIAS[quando.weekday()]} {quando:%d-%m}')
        os.makedirs(pasta_dia, exist_ok=True)
        v, h = hooks.get(item['id'], ({}, {}))
        titulo = item.get('titulo') or h.get('titulo', '')
        base = f"{quando:%Hh%M} · {item['id']}"
        ligar(item['video'], os.path.join(pasta_dia, f"{base} · {limpo(titulo)}.mp4"))
        pasta_video = os.path.dirname(item['video'])
        leg = os.path.join(pasta_video, 'legenda.txt')
        legenda = open(leg, encoding='utf-8').read().strip() if os.path.exists(leg) else ''
        if legenda:
            ligar(leg, os.path.join(pasta_dia, f'{base} · legenda.txt'))
        tira = os.path.join(conf, f"ORG_{item['id']}.png")
        if os.path.exists(tira):
            ligar(tira, os.path.join(pasta_dia, f'{base} · tira.png'))
        if d != dia_atual:
            dia_atual = d
            md += ['', f'## {d + 1} · {DIAS[quando.weekday()]} {quando:%d/%m}', '']
            if v:
                md += [f"Reel de origem: [{v['shortcode']}](https://www.instagram.com/reel/{v['shortcode']}/)", '']
        fotos = [(x, y) for x, y in trechos_parados(item['video']) if y - x > FOTO_MAX] if a.anuncio else []
        if fotos:
            alerta.append(item['id'])
            md += [f"- ⛔ **{quando:%H:%M} · {item['id']}** · NÃO AGENDAR: imagem parada acima de {FOTO_MAX} s em "
                   + ', '.join(f'{x:.1f}–{y:.1f} s ({y - x:.1f} s)' for x, y in fotos)]
        md += [f"- [ ] **{quando:%H:%M} · {item['id']}** · {titulo}",
               f"  - gancho ({h.get('pele', '?')}): “{h.get('texto', '')}”",
               f"  - legenda: {legenda.splitlines()[0][:140] if legenda else '(sem legenda)'}…"]
    with open(os.path.join(raiz, '_aprovar.md'), 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(md) + '\n')
    print(f'{len(fila["itens"])} vídeos em {d + 1} dias → {raiz}')
    if alerta:
        print(f'⛔ {len(alerta)} com foto/imagem parada acima de {FOTO_MAX} s (regra do Meta): {", ".join(alerta)}')


if __name__ == '__main__':
    main()

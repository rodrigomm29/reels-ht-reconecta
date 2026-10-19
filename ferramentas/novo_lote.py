#!/usr/bin/env python3
"""Monta a lista de Reels base de um dia (`planos/_semXX_reels.json`), que é a entrada dos agentes de gancho.

Para cada shortcode: acha o vídeo e a transcrição em REELS_BASE, mede a duração, puxa a legenda original do
post (do .mp4.json que o baixar_reels.sh grava) e junta em `evitar` os ganchos que esse Reel já teve em planos
anteriores (planos/ht_*.json), pra os agentes não repetirem.

uso:
  python3 ferramentas/novo_lote.py --semana SEM43 --dia segunda --primeiro 1 DeVFJ2Ei65T DeMoWouilUT ...
  (--primeiro = número do primeiro VD do dia: segunda 1, terça 8, quarta 15... com 7 Reels por dia)
"""
import argparse, glob, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from checar_fotos import trechos_parados  # noqa: E402

FOTO_MAX = 2.5        # regra do Meta, só para ANÚNCIO: foto de antes/depois no máximo 2,5 s (no orgânico, só aviso)


def achar(pasta, sufixo):
    return next((f for f in sorted(os.listdir(pasta)) if f.endswith(sufixo) and not f.startswith('._')), None)


def duracao(arq):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                       capture_output=True, text=True)
    return round(float(r.stdout.strip()), 2)


def legenda_original(meta):
    if not os.path.exists(meta):
        return ''
    try:
        d = json.load(open(meta, encoding='utf-8'))
    except json.JSONDecodeError:
        return ''
    return d.get('description') or d.get('caption') or ''


def ganchos_antigos(sc):
    usados = []
    for p in glob.glob(os.path.join(config.PROJETO, 'planos', 'ht_*.json')):
        try:
            plano = json.load(open(p, encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for v in plano.get('videos', []):
            if v.get('shortcode') == sc:
                for h in v.get('hooks', {}).values():
                    usados.append({'inicio': h['inicio'], 'fim': h['fim'], 'texto': h.get('texto', ''),
                                   'plano': os.path.basename(p)})
    return usados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--semana', required=True, help='ex.: SEM43')
    ap.add_argument('--dia', required=True, choices=['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'])
    ap.add_argument('--primeiro', type=int, default=1, help='número do primeiro VD do dia')
    ap.add_argument('shortcodes', nargs='+')
    a = ap.parse_args()
    videos, transcr = os.path.join(config.REELS_BASE, 'videos'), os.path.join(config.REELS_BASE, 'transcricoes')
    saida = os.path.join(config.PROJETO, 'planos', f'_{a.semana.lower()}_reels.json')
    lote = json.load(open(saida, encoding='utf-8')) if os.path.exists(saida) else {}
    itens = []
    excl_arq = os.path.join(config.PROJETO, 'planos', '_excluidos.json')
    excluidos = json.load(open(excl_arq, encoding='utf-8')) if os.path.exists(excl_arq) else {}
    for sc in a.shortcodes:                       # decisão da equipe: estes não voltam
        base = sc[:-1] if sc.endswith('F') and sc[:-1] in excluidos else sc
        if base in excluidos and base != '_sobre':
            raise SystemExit(f'{sc}: está em planos/_excluidos.json ({excluidos[base]})')
        arq = achar(videos, f'_{sc}.mp4')
        if arq and config.DATA_CORTE and not sc.startswith('BR') and arq[:10] < config.DATA_CORTE:
            raise SystemExit(f'{sc}: publicado em {arq[:10]}, antes da DATA_CORTE {config.DATA_CORTE}')
    for n, sc in enumerate(a.shortcodes):
        arq, tr = achar(videos, f'_{sc}.mp4'), achar(transcr, f'_{sc}.json')
        if not arq:
            raise SystemExit(f'{sc}: vídeo não está em {videos} (rode o baixar_reels.sh)')
        if not tr:
            raise SystemExit(f'{sc}: sem transcrição em {transcr} (rode o transcrever_reels.sh)')
        itens.append({'vd': f'VD{a.primeiro + n:03d}', 'sc': sc, 'video': arq, 'transcr': tr,
                      'dur': duracao(os.path.join(videos, arq)), 'evitar': ganchos_antigos(sc), 'cortes_antigos': [],
                      'legenda': legenda_original(os.path.join(videos, arq + '.json'))})
    lote[a.dia] = itens
    json.dump(lote, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    barrados = []
    for i in itens:
        fotos = [(x, y) for x, y in trechos_parados(os.path.join(videos, i['video'])) if y - x > FOTO_MAX]
        print(f"{i['vd']}  {i['sc']}  {i['dur']:6.1f}s  ganchos já usados: {len(i['evitar'])}"
              + ('  (passa de 175 s: o agente lista cortes)' if i['dur'] > 175 else '')
              + (f"  (foto parada > {FOTO_MAX} s: não serve para anúncio sem limpar) " + ', '.join(f'{x:.1f}–{y:.1f}' for x, y in fotos) if fotos else ''))
        if fotos:
            barrados.append(i['sc'])
    if barrados:
        print(f"aviso: {', '.join(barrados)} mostram foto acima de {FOTO_MAX} s. Ok no orgânico; para anúncio, "
              f"gere a versão limpa com ferramentas/limpar_fotos.py")
    print('gravado:', saida)


if __name__ == '__main__':
    main()

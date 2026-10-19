#!/usr/bin/env python3
"""Monta o plano de UM DIA do HT com peles (7+ Reels × 3 ganchos) a partir dos rascunhos dos agentes de gancho.

uso:
  python3 montar_plano_dia.py --dia quinta --rascunho planos/_rascunho_sem41_quinta --modelo planos/ht_sem41_quarta.json \
      --cy '{"VD021|5 ou 6 clínicas": 1180}' [--sem-momento "VD022|2 extremos"] [--simular]

Regras (decididas com o Sávio em 06/10/2026):
  - cada Reel sai nas 3 peles (manchete / cinema / dinâmica) e nas 3 aberturas (flash / rebobinar / pergunta);
  - "pergunta" nunca com "manchete" (o título apareceria duas vezes);
  - rodízio por Reel: na fila intercalada (todos os A, depois os B, depois os C) a pele nunca repete em posts seguidos;
  - LUT do cinema gira entre SWOFF / OFELIA / LOUISE (deslocada pelo dia, pra não repetir a mesma LUT no mesmo Reel-posição);
  - destaque de número só entra com `cy` informado (altura escolhida olhando o quadro); sem `cy`, fica de fora.
Copia do modelo: tela final, SFX, folgas, variantes (HT com tela final; ORG ≤ 179,5 s).
"""
import argparse, glob, json, os, unicodedata
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402

BASE = config.REELS_BASE
LUTS = [(str(i), config.lut(i)) for i in range(3)]   # só a pele "cinema" usa (LUT_1..3 no config.env)
PELES = ['manchete', 'cinema', 'dinamica']
# padrões de abertura pra ordem de peles (A,B,C); cada um respeita "pergunta nunca com manchete"
ABERTURAS = [('flash', 'pergunta', 'rebobinar'), ('rebobinar', 'flash', 'pergunta'), ('flash', 'rebobinar', 'pergunta')]
PELES_CLEAN = ['limpa', 'zoom', 'texto']
ABERTURA_CLEAN = {'limpa': 'corte', 'zoom': 'flash', 'texto': 'corte'}
# tela dividida (13/10): todos na mesma pele; a abertura gira entre corte e flash
ABERTURAS_DIVIDIDA = [('corte', 'flash', 'corte'), ('flash', 'corte', 'flash')]
DIAS = {'segunda': 0, 'terça': 1, 'quarta': 2, 'quinta': 3, 'sexta': 4}

def achar(pasta, sufixo):
    return next((f for f in os.listdir(pasta) if f.endswith(sufixo) and not f.startswith('._')), None)

def distribuir_broll(videos, ok, semente):
    """Cada Reel recebe o acervo embaralhado (sorteio fixo pela semana/dia/VD) e o divide em 3 fatias SEM
    interseção, uma por versão: as 3 versões do mesmo Reel nunca mostram o mesmo clipe em cima.
    Entre Reels diferentes o embaralhamento muda, então a ordem e o começo nunca se repetem."""
    import random
    for v in videos:
        rnd = random.Random(f"{semente}-{v['vd']}")
        pool = sorted(ok)
        rnd.shuffle(pool)
        n = len(pool) // 3
        for k, letra in enumerate(sorted(v['hooks'])):
            v['hooks'][letra]['broll'] = pool[k * n:(k + 1) * n]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dia', required=True, choices=list(DIAS))
    ap.add_argument('--rascunho', required=True)
    ap.add_argument('--modelo', default=None, help='plano/modelo pra copiar tela final, SFX, variantes '
                    '(padrão: planos/modelo_organico.json)')
    ap.add_argument('--semana', help='ex.: SEM43; define pasta de saída, fila e prefixo dos arquivos')
    ap.add_argument('--cy', default='{}', help='JSON {"VDxxx|exibir": cy}')
    ap.add_argument('--sem-momento', nargs='*', default=[])
    ap.add_argument('--saida')
    ap.add_argument('--simular', action='store_true')
    ap.add_argument('--estilo', default='peles', choices=['peles', 'clean', 'dividida'],
                    help='clean (12/10): limpa+corte / zoom+flash / texto+corte; dividida (13/10): B-roll em cima, '
                         'pessoa embaixo, legenda na emenda, headline 4 s')
    ap.add_argument('--dividida-y', help='dividida: JSON {shortcode: {"y": topo da janela da pessoa}}')
    ap.add_argument('--broll-triagem', help='dividida: JSON da triagem ({"pasta", "ok": [...]}) do B-roll')
    ap.add_argument('--abertura-fotos', help='dividida: pasta de antes/depois (.jpg/.png); cada gancho abre com '
                                             'um deles em cima por 2,4 s, A/B/C sempre com fotos diferentes')
    a = ap.parse_args()
    a.modelo = a.modelo or os.path.join(config.PROJETO, 'planos', 'modelo_organico.json')
    modelo = json.load(open(a.modelo, encoding='utf-8'))
    for k in ('destino', 'tela_final', 'sfx'):          # o _template.json usa ${SAIDA_DIR}, ${TELA_FINAL}...
        if isinstance(modelo.get(k), str):
            modelo[k] = config.expandir(modelo[k])
    for var in modelo['variantes']:                # "auto": tela final só se o TELA_FINAL existir
        if var.get('tela_final') == 'auto':
            var['tela_final'] = bool(modelo.get('tela_final')) and os.path.isfile(modelo['tela_final'])
    cy = json.loads(a.cy)
    sem = set(a.sem_momento)
    semana = a.semana or modelo['fila'].split('-')[0]              # SEM41
    if semana == 'SEMXX':
        raise SystemExit('passe --semana (ex.: --semana SEM43)')
    if a.semana:                                   # saída e prefixo da semana pedida
        import datetime, re
        modelo['destino'] = os.path.join(config.SAIDA_DIR, semana, 'modelo')
        aa = datetime.date.today().strftime('%y')
        for var in modelo['variantes']:
            var['prefixo'] = re.sub(r'^\[[^\]]*\] \[[^\]]*\]', f'[{aa}] [{semana[3:]}]', var['prefixo'])
    rascunhos = sorted(f for f in glob.glob(os.path.join(a.rascunho, 'VD*.json')) if '_novo' not in f)
    videos, legendas = [], {}
    if a.estilo == 'dividida':
        if not a.broll_triagem:
            raise SystemExit('estilo dividida pede --broll-triagem (gere com ferramentas/triagem_broll.py)')
        ys = json.load(open(a.dividida_y, encoding='utf-8')) if a.dividida_y else {}
        triagem = json.load(open(a.broll_triagem, encoding='utf-8'))
        triagem.setdefault('pasta', config.BROLL_DIR)
    for i, r in enumerate(rascunhos):
        d = json.load(open(r, encoding='utf-8'))
        novo = r.replace('.json', '_novo.json')                  # troca de Reel feita depois (prevalece)
        if os.path.exists(novo):
            d = json.load(open(novo, encoding='utf-8'))
        sc = d['shortcode']
        arq, tr = achar(f'{BASE}/videos', f'_{sc}.mp4'), achar(f'{BASE}/transcricoes', f'_{sc}.json')
        if not (arq and tr):
            raise SystemExit(f'{sc}: vídeo ou transcrição não encontrado')
        lista = {'clean': PELES_CLEAN, 'dividida': ['dividida'] * 3}.get(a.estilo, PELES)
        ordem = [lista[(i + k) % 3] for k in range(3)]           # A, B, C
        # abertura: escolhe o padrão cuja "pergunta" não cai na manchete
        for desl in range(3):
            if a.estilo == 'clean':
                ab = tuple(ABERTURA_CLEAN[p] for p in ordem)
                break
            if a.estilo == 'dividida':
                ab = ABERTURAS_DIVIDIDA[i % 2]
                break
            ab = ABERTURAS[(i + desl) % 3]
            if all(not (p == 'manchete' and x == 'pergunta') for p, x in zip(ordem, ab)):
                break
        hooks = {}
        for (l, h), pele, abertura in zip(sorted(d['hooks'].items()), ordem, ab):
            hk = {'inicio': h['inicio'], 'fim': h['fim'], 'texto': h['texto'], 'titulo': h['titulo'],
                  'pele': pele, 'abertura': abertura}
            if a.estilo == 'dividida':
                hk['headline'] = h['titulo']
            for k in ('fim_video', 'ini_corte_min', 'titulo_cy'):
                if h.get(k) is not None:
                    hk[k] = h[k]
            hooks[l] = hk
        momentos = []
        for m in d.get('momentos') or []:
            chave = f"{d['vd']}|{m.get('exibir')}"
            if a.estilo != 'clean' and m.get('tipo') == 'numero' and chave in cy and chave not in sem:
                mm = {'tipo': 'numero', 'inicio': m['inicio'], 'fim': m['fim'], 'exibir': m['exibir'], 'cy': cy[chave]}
                if m.get('linha2'):
                    mm['linha2'] = m['linha2']
                momentos.append(mm)
        item = {'vd': d['vd'], 'shortcode': sc, 'arquivo': f'{BASE}/videos/{arq}',
                'transcricao': f'{BASE}/transcricoes/{tr}',
                'lut': LUTS[(i + DIAS[a.dia]) % 3][1], 'momentos': momentos, 'hooks': hooks}
        if d.get('cortes_versao_curta'):            # trechos que saem se o orgânico passar de 179,5 s
            item['cortes_curta'] = [{'inicio_corte': c['inicio_corte'], 'fim_corte': c['fim_corte'],
                                     'texto': c.get('texto', '')} for c in d['cortes_versao_curta']]
        if d.get('legendas'):
            legendas[d['vd']] = d['legendas']
        if a.estilo == 'dividida':
            if sc not in ys:                     # sem medição: usa o padrão do config e avisa
                print(f'  aviso: {sc} sem y medido; usando DIVIDIDA_Y_PADRAO={config.DIVIDIDA_Y_PADRAO} '
                      f'(meça com ferramentas/medir_janela.py)')
            item['dividida_y'] = int(ys.get(sc, {}).get('y', config.DIVIDIDA_Y_PADRAO))
        videos.append(item)
    if a.estilo == 'dividida':
        distribuir_broll(videos, triagem['ok'], f"{semana}-{a.dia}")
        if a.abertura_fotos:
            fotos = sorted(os.path.join(a.abertura_fotos, f) for f in os.listdir(a.abertura_fotos)
                           if f.lower().endswith(('.jpg', '.jpeg', '.png')) and not f.startswith('.'))
            n = 0
            for v in videos:
                for letra in sorted(v['hooks']):
                    v['hooks'][letra]['abertura_foto'] = fotos[n % len(fotos)]
                    n += 1
    destino = unicodedata.normalize('NFC', modelo['destino'].rsplit('/', 1)[0] + '/' + a.dia)
    plano = {'_sobre': f'HT {semana} {a.dia.upper()}: {len(videos)} Reels base × 3 ganchos × anúncio + orgânico; '
                       'peles e aberturas em rodízio; montado por montar_plano_dia.py',
             'destino': destino, 'fila': f'{semana}-{a.dia.replace("ç", "c")}' + ('-ht' if a.semana else ''),
             **{k: modelo[k] for k in ('acel_max', 'tela_final', 'pausa', 'fusao', 'fade_voz', 'sfx', 'sfx_gain_db',
                                        'sfx_pico', 'flash', 'pad_antes', 'pad_depois', 'variantes')},
             **({'broll_pasta': triagem['pasta']} if a.estilo == 'dividida' else {}),
             'videos': videos}
    from collections import Counter
    hs = [h for v in videos for h in v['hooks'].values()]
    print(f"{len(videos)} Reels, {len(hs)} ganchos | peles {dict(Counter(h['pele'] for h in hs))} | "
          f"aberturas {dict(Counter(h['abertura'] for h in hs))}")
    print('destaques:', [(v['vd'], [m['exibir'] for m in v['momentos']]) for v in videos if v['momentos']])
    saida = a.saida or os.path.join(config.PROJETO, 'planos', f"ht_{semana.lower()}_{a.dia.replace('ç', 'c')}.json")
    if a.simular:
        print('(simulação, nada gravado):', saida)
        return
    json.dump(plano, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    if legendas:                                   # entrada do escrever_legendas.py
        json.dump(legendas, open(os.path.join(a.rascunho, '_legendas.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('legendas do post:', os.path.join(a.rascunho, '_legendas.json'))
    print('plano:', saida, '| destino:', destino)

if __name__ == '__main__':
    main()

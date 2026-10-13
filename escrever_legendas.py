#!/usr/bin/env python3
"""Grava legenda + título de cada vídeo orgânico de um plano (repo e pasta do orgânico) e o índice.

uso: python3 escrever_legendas.py planos/ht_sem41_quinta.json legendas_quinta.json
legendas_quinta.json = {"VD021": {"A": "texto", "B": "...", "C": "..."}, ...}  (troca leve sobre a legenda
original do Reel, mesma tese/forma/emojis; linha em branco escrita como "\\n\\n" vira U+2800).
Título = o `titulo` do gancho no plano. Termina toda legenda com as 4 hashtags (pedido de 05/10/2026);
se a legenda original tinha hashtag própria (ex.: #estetica), passe ela em "_hashtag_extra": {"VD014": "#estetica"}.
"""
import json, os, sys
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402

HASH = config.HASHTAGS
BRANCO = '\n⠀\n'                      # linha "em branco" que Instagram/TikTok não engolem

def main():
    plano = json.load(open(sys.argv[1], encoding='utf-8'))
    legs = json.load(open(sys.argv[2], encoding='utf-8'))
    extra = legs.pop('_hashtag_extra', {})
    var = next(v for v in plano['variantes'] if v['id'] == 'ORG')
    dia = os.path.basename(plano['destino'])
    semana = plano['fila'].split('-')[0]
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'legendas', f'{semana} orgânico {dia}')
    dst = os.path.join(plano['destino'], var['subpasta'])
    for p in (repo, dst):
        os.makedirs(p, exist_ok=True)
    ind = [f'# Legendas e títulos do orgânico — {semana} {dia}', '',
           'Legenda: troca leve sobre a legenda original do Reel + as 4 hashtags. Título: o do gancho (faixa da Manchete, '
           'abertura Pergunta e YouTube Shorts).', '']
    n = 0
    for v in plano['videos']:
        meta = json.load(open(v['arquivo'] + '.json', encoding='utf-8')) if os.path.exists(v['arquivo'] + '.json') else {}
        ind += [f"## {v['vd']} · Reel [{v['shortcode']}](https://www.instagram.com/reel/{v['shortcode']}/)", '',
                '> ' + (meta.get('description') or '').replace('\n', '\n> '), '']
        tags = (extra.get(v['vd'], '') + ' ' + HASH).strip()
        for l, h in sorted(v['hooks'].items()):
            texto = legs[v['vd']][l].replace('\n\n', BRANCO)
            nome = f"{var['prefixo']}{v['vd']}_{l}"
            for p in (repo, dst):
                open(os.path.join(p, f'{nome}.txt'), 'w', encoding='utf-8').write(texto + BRANCO + tags)
                open(os.path.join(p, f'{nome} - título.txt'), 'w', encoding='utf-8').write(h['titulo'])
            ind += [f"**{nome}.mp4** · {h['pele']} / {h['abertura']} · «{h['texto'][:70]}…»", '',
                    f"- Título ({len(h['titulo'])} car.): **{h['titulo']}**", '', '> ' + texto.replace(BRANCO, '\n>\n> '), '']
            n += 1
    for p in (repo, dst):
        open(os.path.join(p, '_legendas-e-titulos.md'), 'w', encoding='utf-8').write('\n'.join(ind) + '\n')
    print(f'{n} legendas e títulos em {repo} e {dst}')

if __name__ == '__main__':
    main()

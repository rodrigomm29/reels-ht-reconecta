#!/usr/bin/env python3
"""Ranqueia os Reels de um perfil do Instagram por curtidas + comentários e deixa os escolhidos
prontos pra virar anúncio HT: lista (gallery-dl), puxa comentários (yt-dlp), baixa o que falta e
transcreve (Scribe v2) — tudo com a sessão do Chrome, um pedido por vez, com pausa entre eles.

uso:
  python3 ranquear_reels.py                       # só o ranking (tabela + ranking_<perfil>_<data>.json)
  python3 ranquear_reels.py --baixar --transcrever  # ranking + baixa os escolhidos que faltam + transcreve
  python3 ranquear_reels.py --dias 30 --top 7 --listar 60 --sem-comentarios

Regras que o script aplica (decididas em 21/09/2026):
  - janela = últimos --dias (padrão 30); post com menos de 7 dias é PROVISÓRIO (listado, fora do top);
  - live/republicação (duração > 10 min) fica de fora;
  - nota = posição em curtidas + posição em comentários (desempate por curtidas);
  - post FORA da janela por até 3 dias que seja o maior da conta entra AVISADO ("fora da janela por N dias");
  - tudo com sessão do navegador (NAVEGADOR do config.env) — só com autorização do dono da conta.
"""
import argparse, datetime, json, os, subprocess, sys, time
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402

BASE = config.REELS_BASE
PIPELINE = os.path.join(config.PROJETO, 'scribe')
NAVEGADOR = config.NAVEGADOR
HOJE = datetime.date.today()

def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)

def listar(perfil, quantidade):
    """gallery-dl -j: metadados sem baixar. Guarda o json bruto com a data, pra auditoria."""
    saida = os.path.join(BASE, f'lista_{perfil}_{HOJE}.json')
    r = sh(['uvx', '--quiet', '--from', 'gallery-dl@latest', '--with', 'yt-dlp', 'gallery-dl',
            '--cookies-from-browser', NAVEGADOR, '-o', 'sleep-request=2', '-j',
            '--range', f'1-{quantidade}', f'https://www.instagram.com/{perfil}/reels/'])
    open(saida, 'w', encoding='utf-8').write(r.stdout)
    try:
        msgs = json.loads(r.stdout)
    except json.JSONDecodeError:
        sys.exit(f"listagem falhou (sessão do navegador?): {r.stderr[-800:]}")
    reels = {}
    for m in msgs:
        if isinstance(m, list) and len(m) >= 3 and m[0] == 3 and isinstance(m[2], dict) and m[2].get('post_shortcode'):
            k = m[2]
            reels.setdefault(k['post_shortcode'], {
                'shortcode': k['post_shortcode'], 'data': str(k.get('date'))[:10], 'curtidas': k.get('likes') or 0,
                'fixado': bool(k.get('pinned')), 'legenda': (k.get('description') or '')[:90].replace('\n', ' ')})
    for x in reels.values():
        x['idade'] = (HOJE - datetime.date.fromisoformat(x['data'])).days
    return list(reels.values())

def comentarios(shortcode):
    """yt-dlp -j dá comment_count e duration (view_count vem None no Instagram)."""
    r = sh(['uvx', '--quiet', 'yt-dlp@latest', '--cookies-from-browser', NAVEGADOR, '--no-download', '-j',
            f'https://www.instagram.com/reel/{shortcode}/'])
    try:
        d = json.loads(r.stdout)
        return d.get('comment_count'), d.get('duration')
    except json.JSONDecodeError:
        return None, None

def no_ssd(shortcode):
    v = [f for f in os.listdir(os.path.join(BASE, 'videos')) if f.endswith(f'_{shortcode}.mp4') and not f.startswith('._')]
    t = [f for f in os.listdir(os.path.join(BASE, 'transcricoes')) if f.endswith(f'_{shortcode}.json') and not f.startswith('._')]
    return (v[0] if v else None), (t[0] if t else None)

def ranquear(reels, dias, top, com_comentarios):
    janela = [x for x in reels if x['idade'] <= dias]
    maduros = [x for x in janela if x['idade'] >= 7]
    provisorios = [x for x in janela if x['idade'] < 7]
    # maior da conta logo fora da janela (até 3 dias) entra avisado
    quase = [x for x in reels if dias < x['idade'] <= dias + 3 and maduros and x['curtidas'] > max(m['curtidas'] for m in maduros)]
    for x in quase:
        x['aviso'] = f"fora da janela por {x['idade'] - dias} dia(s); entrou por ser o maior da conta"
    candidatos = sorted(maduros + quase, key=lambda x: -x['curtidas'])[:top + 8]
    if com_comentarios:
        for x in candidatos:
            x['comentarios'], x['duracao'] = comentarios(x['shortcode'])
            time.sleep(2)
    for x in candidatos:
        if x.get('duracao') and x['duracao'] > 600:
            x['aviso'] = (x.get('aviso', '') + ' LIVE/republicação (> 10 min), fora').strip()
    validos = [x for x in candidatos if not (x.get('duracao') and x['duracao'] > 600)]
    por_curtida = {x['shortcode']: i for i, x in enumerate(sorted(validos, key=lambda x: -x['curtidas']), 1)}
    tem_com = com_comentarios and any(x.get('comentarios') is not None for x in validos)
    por_com = {x['shortcode']: i for i, x in enumerate(sorted(validos, key=lambda x: -(x.get('comentarios') or 0)), 1)} if tem_com else {}
    for x in validos:
        x['pos_curtidas'] = por_curtida[x['shortcode']]
        x['pos_comentarios'] = por_com.get(x['shortcode'])
        x['nota'] = x['pos_curtidas'] + (x['pos_comentarios'] or 0)
    escolhidos = sorted(validos, key=lambda x: (x['nota'], -x['curtidas']))[:top]
    return escolhidos, validos, provisorios

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--perfil', default=config.IG_PERFIL)
    ap.add_argument('--dias', type=int, default=30)
    ap.add_argument('--top', type=int, default=7)
    ap.add_argument('--listar', type=int, default=60, help='quantos itens listar (fixados vêm no topo, dá folga)')
    ap.add_argument('--sem-comentarios', action='store_true')
    ap.add_argument('--baixar', action='store_true', help='baixa os escolhidos que não estão no SSD')
    ap.add_argument('--transcrever', action='store_true', help='transcreve (Scribe v2) os escolhidos sem transcrição')
    a = ap.parse_args()
    os.makedirs(os.path.join(BASE, 'videos'), exist_ok=True)
    os.makedirs(os.path.join(BASE, 'transcricoes'), exist_ok=True)
    os.makedirs(os.path.join(BASE, 'audio'), exist_ok=True)

    print(f"1) listando {a.listar} Reels de @{a.perfil} ({NAVEGADOR})…")
    reels = listar(a.perfil, a.listar)
    print(f"   {len(reels)} listados; janela de {a.dias} dias; comentários: {'não' if a.sem_comentarios else 'sim (yt-dlp, ~3 s por Reel)'}")
    escolhidos, validos, provisorios = ranquear(reels, a.dias, a.top, not a.sem_comentarios)

    print(f"\n2) ranking (nota = posição em curtidas + posição em comentários; menor é melhor)")
    print(f"   {'#':>2} {'reel':12} {'data':10} {'d+':>4} {'curt.':>6} {'coment.':>7} {'dur':>5}  nota  aviso / legenda")
    for i, x in enumerate(sorted(validos, key=lambda x: (x['nota'], -x['curtidas'])), 1):
        marca = '★' if x in escolhidos else ' '
        dur = f"{int(x['duracao'] // 60)}:{int(x['duracao'] % 60):02d}" if x.get('duracao') else '?'
        print(f" {marca}{i:>2} {x['shortcode']:12} {x['data']:10} {x['idade']:>4} {x['curtidas']:>6} {str(x.get('comentarios') or '-'):>7} {dur:>5}  {x['nota']:>4}  "
              f"{x.get('aviso') or ''}{' [fixado]' if x['fixado'] else ''} {x['legenda'][:50]!r}")
    if provisorios:
        print("   provisórios (menos de 7 dias, ainda crescendo, fora do top): " +
              ', '.join(f"{x['shortcode']} ({x['curtidas']})" for x in sorted(provisorios, key=lambda x: -x['curtidas'])))

    for x in escolhidos:
        x['video'], x['transcricao'] = no_ssd(x['shortcode'])
    faltam = [x for x in escolhidos if not x['video']]
    print(f"\n3) escolhidos: {len(escolhidos)}; sem vídeo no SSD: {len(faltam)}; sem transcrição: {sum(1 for x in escolhidos if not x['transcricao'])}")

    if a.baixar and faltam:
        sel = os.path.join(BASE, f'selecionados_ht_{HOJE}.txt')
        open(sel, 'w').write(''.join(f"https://www.instagram.com/reel/{x['shortcode']}/\n" for x in faltam))
        print(f"   baixando {len(faltam)}…")
        r = sh(['uvx', '--quiet', '--from', 'gallery-dl@latest', '--with', 'yt-dlp', 'gallery-dl',
                '--cookies-from-browser', NAVEGADOR, '-o', 'sleep-request=2', '--write-metadata',
                '-D', os.path.join(BASE, 'videos'), '-f', '{date:%Y-%m-%d}_{post_shortcode}.{extension}', '-i', sel])
        print('   ' + '\n   '.join(l for l in r.stdout.splitlines() if l.endswith('.mp4')))
        for x in escolhidos:
            x['video'], x['transcricao'] = no_ssd(x['shortcode'])

    if a.transcrever:
        for x in escolhidos:
            if x['transcricao'] or not x['video']:
                continue
            nome = x['video'][:-4]
            wav = os.path.join(BASE, 'audio', nome + '.wav')
            saida = os.path.join(BASE, 'transcricoes', nome + '.json')
            print(f"   transcrevendo {nome}…")
            sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', os.path.join(BASE, 'videos', x['video']),
                '-vn', '-ac', '1', '-ar', '16000', wav])
            sh(['zsh', os.path.join(PIPELINE, 'transcrever_scribe.sh'), wav, saida])   # usa scribe/vocab.txt ou o exemplo
            x['transcricao'] = os.path.basename(saida) if os.path.exists(saida) else None
            time.sleep(1)

    saida = os.path.join(BASE, f'ranking_{a.perfil}_{HOJE}.json')
    json.dump({'perfil': a.perfil, 'data': str(HOJE), 'dias': a.dias, 'top': a.top,
               'escolhidos': escolhidos, 'candidatos': validos, 'provisorios': provisorios},
              open(saida, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f"\n4) gravado: {saida}")
    print("   próximo passo: frases.py em cada transcrição → escolher 2 ganchos por Reel → planos/ht_semXX.json")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Rotina semanal do TikTok: leva para o TikTok o conteúdo novo do Instagram, no fim da fila.

O que entra:
  1. Vídeo NOVO da Fernanda (bruto, id BRnnn) que já rodou como Trial Reel no Instagram há 3+ dias: vai a VERSÃO
     VENCEDORA (A/B/C) — maior video_views (ou alcance, se o Instagram não deu views) pelas métricas do Publer. O
     Trial é mostrado a quem não segue, o mesmo público do TikTok.
  2. Reel que ela postou DIRETO no Instagram (fora do sistema): baixa os mais recentes do perfil e pega os que
     ainda não estão em nenhuma fila do TikTok (nem são os nossos posts de feed, nem excluídos, nem antes da
     DATA_CORTE, nem sem fala).

Saída: publicar/filas/TIKTOK-<AAAA-MM-DD>.json (itens com "legenda_pendente": a legenda do TikTok é escrita
seguindo planos/_instrucoes_legenda_tiktok.md), o plano de horários (continua o rodízio depois do último post
agendado no TikTok) e saida/tiktok/semana_<data>.md para revisar. NADA é agendado sem --agendar.

uso:
  python3 publicar/tiktok_semana.py                 # monta a fila da semana e o arquivo de revisão
  python3 publicar/tiktok_semana.py --sem-baixar    # sem baixar do Instagram (só vencedores dos Trials)
  python3 publicar/tiktok_semana.py --agendar TIKTOK-2026-10-26   # depois do OK: agenda e atualiza o calendário
  python3 publicar/tiktok_semana.py --sem-baixar --teste   # só mostra, não grava nada
  python3 publicar/tiktok_semana.py --calendario    # só refaz saida/tiktok/calendario_tiktok.{md,csv}
"""
import argparse, datetime as dt, glob, json, os, re, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, RAIZ)
import config  # noqa: E402
import publer_postar as pp  # noqa: E402

FILAS = os.path.join(AQUI, 'filas')
SAIDA = os.path.join(config.SAIDA_DIR, 'tiktok')
HORARIOS = ['12:30', '19:30', '21:00']          # rodízio do teste de horário (19/10/2026)
CONTA_IG = '6ad5006bccc4b084d6c05e56'
DIAS_TRIAL = 3                                   # espera antes de escolher a versão vencedora
FUSO = pp.FUSO
DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']


def ler(caminho):
    return json.load(open(caminho, encoding='utf-8'))


def filas(prefixo):
    for f in sorted(glob.glob(os.path.join(FILAS, f'{prefixo}*.json'))):
        if f.endswith('_legendas.json'):
            continue
        try:
            yield os.path.basename(f)[:-5], ler(f)
        except (json.JSONDecodeError, OSError):
            continue


def ja_no_tiktok():
    """reels (shortcode ou BRnnn) que já estão em alguma fila do TikTok."""
    ja = set()
    for _, d in filas('TIKTOK-'):
        for i in d.get('itens', []):
            r = i.get('reel', '')
            ja.add(r)
            ja.add(r[:-1] if r.endswith(('E', 'F')) else r)
            ja.add(r.rstrip('FE'))
    return ja


def cliente():
    cli = pp.Cliente(pp.obter_chave(), base=pp.BASE)
    cli.workspace = pp.resolver_workspace(cli, None, True)
    return cli


def metricas_ig(cli, de, ate):
    """[(quando, métrica, texto)] dos posts do Instagram no período (Publer post_insights)."""
    out, pagina = [], 0
    while True:
        r = cli.json('GET', f'/analytics/{CONTA_IG}/post_insights',
                     consulta={'from': de, 'to': ate, 'page': pagina})
        posts = r.get('posts', []) if isinstance(r, dict) else []
        for p in posts:
            a = p.get('analytics') or {}
            v = (a.get('video_views') or {}).get('value')
            alc = (a.get('reach') or {}).get('value')
            try:
                q = dt.datetime.fromisoformat(str(p.get('scheduled_at')).replace('Z', '+00:00'))
            except ValueError:
                continue
            out.append((q, v if v is not None else alc, 'views' if v is not None else 'alcance', p.get('text') or ''))
        if not posts or len(out) >= (r.get('total') or 0):
            return out
        pagina += 1


def vencedores(cli, ja):
    """Vídeos novos (BRnnn) cujas 3 versões de Trial já rodaram DIAS_TRIAL dias: a versão com mais views."""
    agora = dt.datetime.now(FUSO)
    grupos = {}
    for nome, d in filas('SEM'):
        for i in d.get('itens', []):
            e = (i.get('estado') or {}).get('instagram') or {}
            if not str(i.get('reel', '')).startswith('BR') or not e.get('scheduled_at'):
                continue
            grupos.setdefault((nome, i['id'].split('_')[0]), []).append((i, dt.datetime.fromisoformat(e['scheduled_at'])))
    if not grupos:
        return [], []
    prontos, esperando = [], []
    for (nome, vd), itens in sorted(grupos.items()):
        reel = itens[0][0]['reel']
        base = reel.rstrip('FE')
        if base in ja or reel in ja:
            continue
        ultimo = max(q for _, q in itens)
        if agora - ultimo < dt.timedelta(days=DIAS_TRIAL):
            esperando.append(f'{base} ({nome} {vd}): última versão saiu {ultimo:%d/%m}; decide depois de {DIAS_TRIAL} dias')
            continue
        de = (min(q for _, q in itens) - dt.timedelta(days=1)).date().isoformat()
        met = metricas_ig(cli, de, (ultimo + dt.timedelta(days=1)).date().isoformat())
        placar = []
        for i, q in itens:
            perto = [m for m in met if abs((m[0] - q).total_seconds()) <= 600 and m[1] is not None]
            if perto:
                placar.append((perto[0][1], perto[0][2], i))
        if len(placar) < len(itens):
            esperando.append(f'{base} ({nome} {vd}): o Publer ainda não tem as métricas das {len(itens)} versões '
                             f'({len(placar)} com dados); tenta de novo na próxima rodada')
            continue
        valor, tipo, vence = max(placar, key=lambda x: x[0])
        prontos.append({'reel': base, 'origem': f'{nome} {vence["id"]}', 'video': vence['video'],
                        'legenda_instagram': vence.get('legenda', ''),
                        'motivo': f'vencedora do Trial ({vence["id"][-1]}, {valor} {tipo}; '
                                  + ', '.join(f'{x[2]["id"][-1]}={x[0]}' for x in sorted(placar, key=lambda x: x[2]['id'])) + ')'})
    return prontos, esperando


def postados_fora(ja, baixar=True):
    """Reels do perfil que não passaram pelo sistema (baixa os 15 mais recentes)."""
    if baixar:
        subprocess.run(['zsh', os.path.join(RAIZ, 'baixar_reels.sh')], cwd=RAIZ, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['zsh', os.path.join(RAIZ, 'transcrever_reels.sh')], cwd=RAIZ, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    excl = ler(os.path.join(RAIZ, 'planos', '_excluidos.json')) if os.path.exists(
        os.path.join(RAIZ, 'planos', '_excluidos.json')) else {}
    # nossos posts de feed (vão como vencedores dos Trials, não de novo pelo perfil)
    feed = set()
    for _, d in filas('FEED-'):
        for i in d.get('itens', []):
            feed.add(re.sub(r'\W', '', (i.get('legenda') or '').split('\n')[0].lower())[:40])
    novos = []
    for f in sorted(glob.glob(os.path.join(config.REELS_BASE, 'videos', '*.mp4'))):
        b = os.path.basename(f)
        data, sc = b[:10], b[11:-4]
        if sc.startswith('BR') or sc.endswith('F') or sc in excl or sc in ja:
            continue
        if config.DATA_CORTE and data < config.DATA_CORTE:
            continue
        meta = ler(f + '.json') if os.path.exists(f + '.json') else {}
        leg = (meta.get('description') or '').strip()
        if re.sub(r'\W', '', leg.split('\n')[0].lower())[:40] in feed:
            continue
        tr = f.replace('/videos/', '/transcricoes/').replace('.mp4', '.json')
        palavras = [w for w in ler(tr).get('words', []) if w.get('type') == 'word'] if os.path.exists(tr) else []
        if len(palavras) < 20:
            continue                                     # sem fala (ou ainda sem transcrição)
        novos.append({'reel': sc, 'origem': f'Instagram {data}', 'video': f, 'legenda_instagram': leg,
                      'motivo': 'postado direto no Instagram'})
    return novos


def proximos_horarios(n):
    """n horários depois do último post agendado no TikTok, continuando o rodízio de HORARIOS."""
    tk = []
    for _, d in filas('TIKTOK-'):
        for i in d.get('itens', []):
            e = (i.get('estado') or {}).get('tiktok') or {}
            if e.get('scheduled_at'):
                tk.append(dt.datetime.fromisoformat(e['scheduled_at']))
    ultimo = max(tk) if tk else dt.datetime.now(FUSO)
    hora = f'{ultimo:%H:%M}'
    k = (HORARIOS.index(hora) + 1) % len(HORARIOS) if hora in HORARIOS else 0
    dia = ultimo.date() + dt.timedelta(days=1)
    out = []
    for j in range(n):
        h, m = map(int, HORARIOS[(k + j) % len(HORARIOS)].split(':'))
        out.append(dt.datetime.combine(dia + dt.timedelta(days=j), dt.time(h, m), tzinfo=FUSO))
    return out


def calendario():
    """saida/tiktok/calendario_tiktok.{md,csv} com tudo o que está agendado (todas as filas do TikTok)."""
    linhas = []
    for nome, d in filas('TIKTOK-'):
        for i in d.get('itens', []):
            e = (i.get('estado') or {}).get('tiktok') or {}
            q = e.get('scheduled_at') or i.get('previsto')
            if q:
                linhas.append((dt.datetime.fromisoformat(q), (i.get('legenda') or '').split('\n')[0].strip()[:70],
                               'agendado' if e.get('scheduled_at') else 'a agendar'))
    linhas.sort()
    os.makedirs(SAIDA, exist_ok=True)
    md = ['# TikTok · Dra. Fernanda Porto · horários dos posts', '',
          'Responder os comentários de preferência na 1ª hora depois de cada post.', '',
          '| Dia | Data | Hora | Assunto | Situação |', '|---|---|---|---|---|']
    md += [f'| {DIAS[q.weekday()]} | {q:%d/%m} | {q:%H:%M} | {a} | {s} |' for q, a, s in linhas]
    open(os.path.join(SAIDA, 'calendario_tiktok.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    open(os.path.join(SAIDA, 'calendario_tiktok.csv'), 'w', encoding='utf-8').write(
        'dia;data;hora;assunto;situacao\n' + ''.join(f'{DIAS[q.weekday()]};{q:%d/%m};{q:%H:%M};{a};{s}\n'
                                                    for q, a, s in linhas))
    return len(linhas)


def montar(baixar, teste=False):
    cli = cliente()
    ja = ja_no_tiktok()
    venc, esperando = vencedores(cli, ja)
    fora = postados_fora(ja | {v['reel'] for v in venc}, baixar)
    novos = venc + fora
    hoje = dt.date.today().isoformat()
    nome = f'TIKTOK-{hoje}'
    os.makedirs(SAIDA, exist_ok=True)
    rel = [f'# TikTok · semana de {dt.date.today():%d/%m/%Y}', '']
    if esperando:
        rel += ['## Esperando', ''] + [f'- {e}' for e in esperando] + ['']
    if not novos:
        rel += ['Nada novo para o TikTok nesta semana.']
        if teste:
            print('\n'.join(rel))
            return None
        open(os.path.join(SAIDA, f'semana_{hoje}.md'), 'w', encoding='utf-8').write('\n'.join(rel) + '\n')
        print('\n'.join(rel))
        return None
    slots = proximos_horarios(len(novos))
    if teste:
        for v, q in zip(novos, slots):
            print(f"{DIAS[q.weekday()]} {q:%d/%m %H:%M}  {v['reel']}  {v['motivo']}")
        print('\n'.join(rel))
        return None
    itens = []
    for n, (v, q) in enumerate(zip(novos, slots), 1):
        itens.append({'id': f'TK{hoje[5:7]}{hoje[8:]}_{n:02d}_{v["reel"]}', 'nome': v['reel'], 'reel': v['reel'],
                      'video': os.path.abspath(v['video']), 'titulo': '', 'legenda': v['legenda_instagram'],
                      'legenda_instagram': v['legenda_instagram'], 'legenda_pendente': True,
                      'motivo': v['motivo'], 'previsto': q.isoformat(), 'bytes': os.path.getsize(v['video']),
                      'estado': {'tiktok': {'status': 'pendente'}, 'instagram': {'status': 'nao_se_aplica'},
                                 'youtube': {'status': 'nao_se_aplica'}}})
    json.dump({'semana': nome, 'tipo': 'tiktok', 'horarios': [f'{q:%H:%M}' for q in slots],
               'inicio': slots[0].strftime('%Y-%m-%d %H:%M'), 'itens': itens},
              open(os.path.join(FILAS, f'{nome}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    rel += ['## Entra no TikTok', '']
    for i in itens:
        q = dt.datetime.fromisoformat(i['previsto'])
        rel += [f"- **{DIAS[q.weekday()]} {q:%d/%m %H:%M}** · {i['reel']} · {i['motivo']}"]
    rel += ['', f'Fila: publicar/filas/{nome}.json (legendas do TikTok a escrever: planos/_instrucoes_legenda_tiktok.md).',
            f'Depois do OK: `python3 publicar/tiktok_semana.py --agendar {nome}`']
    open(os.path.join(SAIDA, f'semana_{hoje}.md'), 'w', encoding='utf-8').write('\n'.join(rel) + '\n')
    calendario()
    print('\n'.join(rel))
    return nome


def agendar(nome):
    caminho = os.path.join(FILAS, f'{nome}.json')
    d = ler(caminho)
    pend = [i['id'] for i in d['itens'] if i.get('legenda_pendente')]
    if pend:
        sys.exit(f'legenda do TikTok ainda pendente em: {", ".join(pend)}')
    hs = list(dict.fromkeys(d['horarios']))          # rodízio na ordem dos horários previstos
    cmd = [sys.executable, os.path.join(AQUI, 'publer_postar.py'), 'postar', nome, '--rede', 'tiktok',
           '--inicio', d['inicio'], '--horarios', ','.join(hs), '--rodizio', '--por-dia', str(len(hs))]
    r = subprocess.run(cmd, cwd=AQUI)
    n = calendario()
    print(f'calendário atualizado: {n} posts em {SAIDA}/calendario_tiktok.md')
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sem-baixar', action='store_true')
    ap.add_argument('--agendar', metavar='FILA')
    ap.add_argument('--calendario', action='store_true')
    ap.add_argument('--teste', action='store_true', help='só mostra o que entraria; não grava nada')
    a = ap.parse_args()
    if a.calendario:
        print(f'{calendario()} posts no calendário')
    elif a.agendar:
        agendar(a.agendar)
    else:
        montar(not a.sem_baixar, a.teste)


if __name__ == '__main__':
    main()

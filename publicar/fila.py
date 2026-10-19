#!/usr/bin/env python3
"""Fila de postagem do orgânico (TikTok + YouTube Shorts + Instagram Trial Reels) a partir de um plano HT.

Lê `orgânico/<nome>/` (vídeo + título.txt + legenda.txt, montado pelo organizar_organico.py) e grava
`publicar/filas/<fila>.json` (uma por dia, ex.: SEM41-terca), com o estado de cada vídeo em cada rede
(item.estado.<rede>.status). O publicador (publer_postar.py --rede tiktok|instagram; publer_tiktok.py é o
invólucro do TikTok) consome essa fila e marca o que postou: nada sai duplicado, e uma queda no meio não perde
o controle. Postado fora do script (TikTok Studio, YouTube Studio, mLabs) = status "postado_manual": nunca sai.

Migração: item sem a chave de uma rede ganha {"status": "pendente"} ao carregar/montar (nada é apagado).
Estado malformado (estado.<rede> que não é objeto, objeto sem "status", "estado" que não é objeto) NÃO vira
pendente: a fila não carrega até alguém corrigir à mão. Marcação manual certa:
  "instagram": {"status": "postado_manual", "obs": "postado pelo mLabs em 05/10"}

Trava: montar e intercalar pegam a mesma trava do publicador (filas/<fila>.lock). Com uma rodada publicando a
fila, eles não rodam (gravariam por cima do "agendando" que o publicador escreve antes de criar o post).

Disco fora: o montar nunca tira da fila um item que já estava nela. Vídeo que não foi achado (disco desmontado,
"Cyberpunk 1") fica com o estado e os dados antigos, marcado "faltando"; se nenhum vídeo for achado, nada é
gravado. Item antigo que saiu do plano só some se estiver pendente em todas as redes; senão fica, marcado
"fora_do_plano" (o publicador não posta item fora_do_plano em rede nenhuma).

uso:
  python3 fila.py montar ../planos/ht_sem41_segunda.json  # cria/atualiza a fila (preserva o que já foi postado)
  python3 fila.py ver SEM41-segunda                      # mostra o andamento por rede
  python3 fila.py intercalar SEM41                       # alterna os Reels (VD001, VD002, VD003, VD001…) na ordem de postagem
  python3 fila.py montar-fotos FOTOS-SEM44               # fila de carrosséis do lote do importar_fotos.py (só Instagram)

Fila de fotos: cada item tem "fotos" (lista de JPEGs, na ordem do carrossel) no lugar de "video"; o publicador vê
isso e agenda um carrossel no feed do Instagram. TikTok e YouTube ficam "nao_se_aplica" (nunca saem).
"""
import argparse, datetime as dt, fcntl, json, os, sys, tempfile, unicodedata
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
FILAS = os.path.join(AQUI, 'filas')
REDES = ('tiktok', 'youtube', 'instagram')


class EstadoMalformado(ValueError):
    """estado.<rede> de um item não está no formato {"status": "..."}: ninguém adivinha o que era."""


class TravaOcupada(Exception):
    def __init__(self, caminho, dono):
        super().__init__(caminho)
        self.caminho, self.dono = caminho, dono


def nfc(s):
    return unicodedata.normalize('NFC', s)

def achar(pasta, nome):
    alvo = nfc(nome)
    for f in os.listdir(pasta):
        if nfc(f) == alvo:
            return os.path.join(pasta, f)
    return None

def caminho_fila(semana):
    return os.path.join(FILAS, f'{semana}.json')

def caminho_trava(nome):
    return os.path.join(FILAS, f'{nome}.lock')

def travar(nome, dono):
    """Trava exclusiva em filas/<nome>.lock (o sistema solta sozinho se o processo morrer). Devolve o descritor;
    fechar o descritor solta a trava. Ocupada: levanta TravaOcupada com quem está segurando."""
    os.makedirs(FILAS, exist_ok=True)
    caminho = caminho_trava(nome)
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            atual = os.pread(fd, 200, 0).decode('utf-8', 'replace').strip()
        except OSError:
            atual = ''
        os.close(fd)
        raise TravaOcupada(caminho, atual) from None
    os.ftruncate(fd, 0)
    agora = dt.datetime.now(ZoneInfo(config.FUSO))
    os.pwrite(fd, f'pid {os.getpid()}, {dono}, desde {agora:%d/%m %H:%M}\n'.encode(), 0)
    return fd

def travar_ou_sair(semana, dono):
    try:
        return travar(semana, dono)
    except TravaOcupada as e:
        sys.exit(f'Tem uma rodada publicando a fila {semana}' + (f' ({e.dono})' if e.dono else '') +
                 '. Nada foi gravado: espere ela terminar e rode de novo.\n'
                 f'(trava: {e.caminho})')

def completar_redes(item):
    """Migração sem perda: só a rede que FALTA no estado do item entra como pendente; o resto fica como está.
    Estado que existe mas está malformado levanta EstadoMalformado (nunca vira pendente em silêncio)."""
    rid = item.get('id', '?')
    if 'estado' not in item:
        item['estado'] = {}
    est = item['estado']
    if not isinstance(est, dict):
        raise EstadoMalformado(f'o "estado" do item {rid} está malformado ({json.dumps(est, ensure_ascii=False)[:80]})')
    for r in REDES:
        if r not in est:
            est[r] = {'status': 'pendente'}
            continue
        v = est[r]
        if not isinstance(v, dict) or not isinstance(v.get('status'), str) or not v['status'].strip():
            raise EstadoMalformado(f'estado.{r} do item {rid} está malformado '
                                   f'({json.dumps(v, ensure_ascii=False)[:120]}): falta "status"')
    return item

def carregar(semana):
    p = caminho_fila(semana)
    if not os.path.exists(p):
        sys.exit(f'fila {semana} não existe: rode "fila.py montar <plano>" antes')
    with open(p, encoding='utf-8') as f:
        fila = json.load(f)
    try:
        for item in fila.get('itens', []):
            completar_redes(item)
    except EstadoMalformado as e:
        sys.exit(f'fila {semana}: {e}.\nCorrija à mão no {p} (ex.: "instagram": {{"status": "postado_manual", '
                 '"obs": "postado pelo mLabs em 05/10"}). Nada foi lido nem gravado.')
    return fila

def salvar(fila):
    """Grava inteiro num .part de nome único e troca (queda não corrompe a fila; duas gravações não dividem .part)."""
    os.makedirs(FILAS, exist_ok=True)
    p = caminho_fila(fila['semana'])
    try:
        modo = os.stat(p).st_mode & 0o777
    except OSError:
        modo = 0o644
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(p) + '.', suffix='.part', dir=FILAS)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(fila, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, modo)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def so_pendente(item):
    """True se o item não saiu (nem tentou sair) em rede nenhuma: pode sumir da fila sem perder nada."""
    return all((item.get('estado') or {}).get(r, {}).get('status') == 'pendente' for r in REDES)

def intercalados(itens):
    grupos = {}
    for i in itens:
        grupos.setdefault(i['id'].split('_')[0], []).append(i)
    ordem = []
    while any(grupos.values()):
        for vd in sorted(grupos):
            if grupos[vd]:
                ordem.append(grupos[vd].pop(0))
    return ordem

def montar(plano_path):
    plano = json.load(open(plano_path, encoding='utf-8'))
    var = next((v for v in plano.get('variantes', []) if v.get('id') == 'ORG'), None)
    if not var:
        sys.exit('o plano não tem a versão ORG (orgânico)')
    # nome da fila: campo `fila` do plano (ex.: SEM41-terca, com a semana organizada por dia) ou a pasta destino
    semana = plano.get('fila') or os.path.basename(plano['destino'].rstrip('/'))
    raiz = os.path.join(plano['destino'], var['subpasta'])
    trava = travar_ou_sair(semana, 'fila.py montar')
    try:
        antiga, meta_antiga = {}, {}
        if os.path.exists(caminho_fila(semana)):
            velha = carregar(semana)
            antiga = {i['id']: i for i in velha['itens']}
            # preserva os metadados da fila (conta de destino, ordem) ao remontar
            meta_antiga = {k: v for k, v in velha.items() if k not in ('semana', 'plano', 'itens')}
        itens, faltando, mantidos, achados = [], [], [], 0
        for v in plano['videos']:
            for letra in sorted(v['hooks']):
                nome = f"{var['prefixo']}{v['vd']}_{letra}"
                rid = f"{v['vd']}_{letra}"
                pasta = os.path.join(raiz, nome)
                video = achar(pasta, nome + '.mp4') if os.path.isdir(pasta) else None
                tit = achar(pasta, 'título.txt') if os.path.isdir(pasta) else None
                leg = achar(pasta, 'legenda.txt') if os.path.isdir(pasta) else None
                if not (video and tit and leg):
                    faltando.append(nome)
                    if rid in antiga:                        # nunca some: fica com o estado e os dados antigos
                        velho = dict(antiga[rid])
                        velho['faltando'] = True
                        itens.append(velho)
                        mantidos.append(rid)
                    continue
                achados += 1
                item = {
                    'id': rid, 'nome': nome, 'reel': v['shortcode'], 'video': video,
                    'titulo': open(tit, encoding='utf-8').read().strip(),
                    'legenda': open(leg, encoding='utf-8').read().strip(),
                    'bytes': os.path.getsize(video),
                    'estado': {r: {'status': 'pendente'} for r in REDES},
                }
                if rid in antiga:                            # preserva o que já foi postado/tentado
                    item['estado'] = antiga[rid]['estado']
                    completar_redes(item)                    # rede nova (ex.: instagram) entra como pendente
                itens.append(item)
        if not achados:
            sys.exit(f'nenhum vídeo do plano foi achado em {raiz}: o disco está montado? '
                     f'Nada foi gravado (a fila {semana} continua como estava).')
        # item antigo que não está mais no plano: só sai se nunca saiu em rede nenhuma
        no_plano = {i['id'] for i in itens} | {f"{v['vd']}_{l}" for v in plano['videos'] for l in v['hooks']}
        fora = []
        for rid, velho in antiga.items():
            if rid in no_plano or so_pendente(velho):
                continue
            velho = dict(velho)
            velho['fora_do_plano'] = True
            itens.append(velho)
            fora.append(rid)
        fila = {'semana': semana, 'plano': os.path.abspath(plano_path), **meta_antiga, 'itens': itens}
        if fila.get('ordem') == 'intercalada':             # remontar não desfaz a intercalação
            fila['itens'] = intercalados(itens)
        salvar(fila)
    finally:
        os.close(trava)
    print(f'fila {semana}: {achados} vídeos achados' +
          (f'; FALTANDO {len(faltando)}: {faltando}' if faltando else '') +
          (f'\n  mantidos com o estado antigo, marcados "faltando" (o disco está montado?): {mantidos}' if mantidos else '') +
          (f'\n  fora do plano, mas já saíram/tentaram sair em alguma rede (mantidos, marcados "fora_do_plano"): {fora}'
           if fora else ''))
    return fila

NAO_SE_APLICA = 'nao_se_aplica'
REDES_FOTOS = ('instagram',)

def montar_fotos(lote):
    """Fila <lote> a partir de FOTOS_DIR/<lote>/lote.json (gravado pelo ferramentas/importar_fotos.py)."""
    lote_json = os.path.join(config.FOTOS_DIR, lote, 'lote.json')
    if not os.path.exists(lote_json):
        sys.exit(f'lote {lote} não existe ({lote_json}): rode antes ferramentas/importar_fotos.py {lote}')
    with open(lote_json, encoding='utf-8') as f:
        dados = json.load(f)
    semana = dados['lote']
    trava = travar_ou_sair(semana, 'fila.py montar-fotos')
    try:
        antiga, meta_antiga = {}, {}
        if os.path.exists(caminho_fila(semana)):
            velha = carregar(semana)
            if any(i.get('video') for i in velha['itens']):
                sys.exit(f'a fila {semana} já existe e é de VÍDEOS: use outro nome de lote. Nada foi gravado.')
            antiga = {i['id']: i for i in velha['itens']}
            meta_antiga = {k: v for k, v in velha.items() if k not in ('semana', 'plano', 'itens')}
        itens, sem_legenda, sem_fotos = [], [], []
        for p in dados['posts']:
            fotos = [f for f in p['fotos'] if os.path.isfile(f)]
            legenda = open(p['legenda'], encoding='utf-8').read().strip() if os.path.isfile(p['legenda']) else ''
            if len(fotos) != len(p['fotos']) or not fotos:
                sem_fotos.append(p['id'])
            if not legenda:
                sem_legenda.append(p['id'])
            item = {
                'id': p['id'], 'nome': p['nome'], 'fotos': p['fotos'], 'legenda': legenda,
                'bytes': sum(os.path.getsize(f) for f in fotos),
                'estado': {r: ({'status': 'pendente'} if r in REDES_FOTOS else {'status': NAO_SE_APLICA})
                           for r in REDES},
            }
            if p['id'] in antiga:                            # preserva o que já foi postado/tentado
                item['estado'] = antiga[p['id']]['estado']
                completar_redes(item)
                st = item['estado']['instagram']['status']
                if st != 'pendente' and (item['legenda'] != antiga[p['id']].get('legenda')
                                         or item['fotos'] != antiga[p['id']].get('fotos')):
                    print(f'aviso: {p["id"]} já está "{st}" no Instagram; a legenda/fotos novas NÃO mudam o post '
                          'que já foi pro Publer (edite lá)')
            itens.append(item)
        if sem_fotos or sem_legenda:
            sys.exit('Nada foi gravado. Antes de montar a fila:'
                     + (f'\n  fotos faltando em: {", ".join(sem_fotos)} (reimporte com --de-novo)' if sem_fotos else '')
                     + (f'\n  legenda vazia em: {", ".join(sem_legenda)} '
                        f'(escreva em {os.path.join(config.FOTOS_DIR, lote)}/<id>/legenda.txt)' if sem_legenda else ''))
        ids = {i['id'] for i in itens}
        fora = []
        for rid, velho in antiga.items():                    # saiu do lote: só some se nunca saiu
            if rid in ids or so_pendente_fotos(velho):
                continue
            velho = dict(velho)
            velho['fora_do_plano'] = True
            itens.append(velho)
            fora.append(rid)
        fila = {'semana': semana, 'plano': os.path.abspath(lote_json), 'tipo': 'carrossel', **meta_antiga,
                'itens': itens}
        salvar(fila)
    finally:
        os.close(trava)
    print(f'fila {semana}: {len(itens)} carrossel(éis), {sum(len(i["fotos"]) for i in itens)} fotos'
          + (f'\n  fora do lote, mas já saíram/tentaram sair (mantidos, marcados "fora_do_plano"): {fora}' if fora else ''))
    print(f'próximo passo: python3 publicar/publer_postar.py postar {semana} --rede instagram '
          '--inicio "AAAA-MM-DD HH:MM" --horarios "12:00" --simular')
    return fila

def so_pendente_fotos(item):
    return all(v.get('status') in ('pendente', NAO_SE_APLICA) for v in (item.get('estado') or {}).values())

def ver(semana):
    fila = carregar(semana)
    for r in REDES:
        cont = {}
        for i in fila['itens']:
            s = i['estado'][r]['status']
            cont[s] = cont.get(s, 0) + 1
        print(f'{r:9} ' + '  '.join(f'{k}: {n}' for k, n in sorted(cont.items())))
    marcados = [i['id'] for i in fila['itens'] if i.get('faltando') or i.get('fora_do_plano')]
    if marcados:
        print(f'marcados "faltando"/"fora_do_plano": {marcados}')

def intercalar(semana):
    """Reordena a fila alternando os Reels de origem, mantendo a ordem dos ganchos de cada um.
    Evita postar 6-7 variações da mesma história em sequência."""
    trava = travar_ou_sair(semana, 'fila.py intercalar')
    try:
        fila = carregar(semana)
        ordem = intercalados(fila['itens'])
        fila['itens'] = ordem
        fila['ordem'] = 'intercalada'
        salvar(fila)
    finally:
        os.close(trava)
    print('ordem: ' + ' '.join(i['id'] for i in ordem))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('montar'); m.add_argument('plano')
    v = sub.add_parser('ver'); v.add_argument('semana')
    t = sub.add_parser('intercalar'); t.add_argument('semana')
    f = sub.add_parser('montar-fotos'); f.add_argument('lote')
    a = ap.parse_args()
    if a.cmd == 'montar':
        montar(a.plano)
    elif a.cmd == 'montar-fotos':
        montar_fotos(a.lote)
    elif a.cmd == 'intercalar':
        intercalar(a.semana)
    else:
        ver(a.semana)

if __name__ == '__main__':
    main()

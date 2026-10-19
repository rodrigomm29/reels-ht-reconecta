#!/usr/bin/env python3
"""Apaga no Publer posts AGENDADOS de uma fila (ainda não publicados) e devolve esses itens para "pendente",
pra serem reagendados pelo publer_postar.py (ex.: o vídeo foi refeito depois de agendado).

CUIDADO (doc do Publer, DELETE /posts): sem `post_ids`, a API apaga TODOS os posts não publicados do workspace.
Por isso este script só manda ids que estão na fila, recusa lista vazia e confere a resposta (`deleted_ids`).

uso:
  python3 publer_apagar.py SEM43-segunda-ht --rede instagram VD002_A VD002_B ...      # só mostra
  python3 publer_apagar.py SEM43-segunda-ht --rede instagram VD002_A VD002_B ... --confirmar
"""
import argparse, datetime, json, os, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from publer_postar import BASE, Cliente, obter_chave, resolver_workspace  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fila')
    ap.add_argument('ids', nargs='+', help='ids da fila (ex.: VD002_A)')
    ap.add_argument('--rede', required=True, choices=('instagram', 'tiktok'))
    ap.add_argument('--confirmar', action='store_true', help='apaga de verdade (sem isto, só mostra)')
    a = ap.parse_args()
    caminho = os.path.join(AQUI, 'filas', f'{a.fila}.json')
    fila = json.load(open(caminho, encoding='utf-8'))
    por_id = {i['id']: i for i in fila['itens']}
    alvo = []
    for vid in a.ids:
        item = por_id.get(vid)
        if not item:
            sys.exit(f'{vid}: não está na fila {a.fila}')
        e = item['estado'].get(a.rede, {})
        if e.get('status') != 'agendado_publer' or not e.get('post_id'):
            sys.exit(f'{vid}: não está agendado no Publer ({e.get("status")}); nada a apagar')
        alvo.append((vid, e['post_id'], e.get('scheduled_at')))
    if not alvo or len(alvo) != len(set(p for _, p, _ in alvo)):
        sys.exit('lista de posts vazia ou repetida; nada enviado')
    for vid, pid, quando in alvo:
        print(f'  {vid}  post {pid}  agendado para {quando}')
    if not a.confirmar:
        print(f'(só mostrando: {len(alvo)} post(s); rode com --confirmar para apagar)')
        return
    cli = Cliente(obter_chave(), base=BASE)
    cli.workspace = resolver_workspace(cli, None, True)
    ids = [p for _, p, _ in alvo]
    # Rails: lista vai como post_ids[]=a&post_ids[]=b (com post_ids=a&post_ids=b só o ÚLTIMO é lido; medido 19/10)
    resp = cli.json('DELETE', '/posts', consulta={'post_ids[]': ids})
    apagados = set((resp or {}).get('deleted_ids') or [])
    agora = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    for vid, pid, quando in alvo:
        e = por_id[vid]['estado'][a.rede]
        if pid in apagados:
            por_id[vid]['estado'][a.rede] = {'status': 'pendente',
                                             'apagado': {'em': agora, 'post_id': pid, 'scheduled_at': quando}}
            print(f'  apagado: {vid} ({pid})')
        else:
            print(f'  NÃO apagado: {vid} ({pid}); confira no Publer')
    with open(caminho + '.tmp', 'w', encoding='utf-8') as fp:
        json.dump(fila, fp, ensure_ascii=False, indent=1)
    os.replace(caminho + '.tmp', caminho)
    print(f'{len(apagados & set(ids))} de {len(ids)} apagado(s); fila atualizada')
    sys.exit(0 if apagados >= set(ids) else 1)


if __name__ == '__main__':
    main()

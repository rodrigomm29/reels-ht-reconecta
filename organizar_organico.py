#!/usr/bin/env python3
"""Organiza a pasta do orgânico (Trial Reels / Shorts / TikTok): UMA PASTA POR VÍDEO, com o vídeo,
o título do Shorts e a legenda (pedido do Sávio, 05/10/2026).

  orgânico/
    [26] [41] [ORG] VD001_A/
      [26] [41] [ORG] VD001_A.mp4
      título.txt
      legenda.txt
    ...
    _legendas-e-titulos.md      (índice geral, continua na raiz)
    [26] [41] [ORG] VD001_A.mp4 (CÓPIA solta de cada vídeo na raiz — pedido do Sávio, 05/10; --sem-copia desliga)

uso: python3 organizar_organico.py planos/ht_sem41.json [--versao ORG] [--simular]

Só MOVE (nunca apaga). Pode rodar de novo: o que já está na pasta certa fica onde está.
Leva junto o "._arquivo" do exFAT quando o sistema não levou sozinho.
Nomes comparados em NFC: o exFAT do Mac pode gravar "título" decomposto (NFD).
"""
import argparse, json, os, sys, unicodedata

def nfc(s):
    return unicodedata.normalize('NFC', s)

def achar(pasta, nome):
    """Caminho real do arquivo `nome` em `pasta`, tolerando NFC/NFD. None se não existir."""
    alvo = nfc(nome)
    for f in os.listdir(pasta):
        if nfc(f) == alvo:
            return os.path.join(pasta, f)
    return None

def mover(origem, destino, simular):
    pasta, nome = os.path.split(origem)
    if simular:
        print(f"   mover {nome} → {os.path.relpath(destino, os.path.dirname(pasta))}")
        return
    os.rename(origem, destino)
    # o exFAT guarda metadados em "._nome"; se o sistema não levou junto, leva
    sombra = achar(pasta, '._' + nome)
    if sombra:
        d_pasta, d_nome = os.path.split(destino)
        os.rename(sombra, os.path.join(d_pasta, '._' + d_nome))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plano')
    ap.add_argument('--versao', default='ORG', help='id da versão orgânica no plano (padrão ORG)')
    ap.add_argument('--simular', action='store_true', help='só mostra o que faria')
    ap.add_argument('--sem-copia', action='store_true', help='não deixa a cópia solta dos vídeos na raiz')
    a = ap.parse_args()
    plano = json.load(open(a.plano, encoding='utf-8'))
    var = next((v for v in plano.get('variantes', []) if v.get('id') == a.versao), None)
    if not var:
        sys.exit(f"versão {a.versao} não está no plano")
    raiz = os.path.join(plano['destino'], var['subpasta'])
    movidos, prontos, faltando = 0, 0, []
    for v in plano['videos']:
        for letra in sorted(v['hooks']):
            nome = f"{var['prefixo']}{v['vd']}_{letra}"
            pasta = os.path.join(raiz, nome)
            itens = [(nome + '.mp4', nome + '.mp4'),          # (nome solto na raiz, nome dentro da pasta)
                     (nome + ' - título.txt', 'título.txt'),
                     (nome + '.txt', 'legenda.txt')]
            if not a.simular:
                os.makedirs(pasta, exist_ok=True)
            for solto, dentro in itens:
                if os.path.isdir(pasta) and achar(pasta, dentro):
                    prontos += 1
                    continue
                origem = achar(raiz, solto)
                if not origem:
                    faltando.append(f"{nome}: {dentro}")
                    continue
                mover(origem, os.path.join(pasta, dentro), a.simular)
                movidos += 1
    copias = 0
    if not a.sem_copia and not a.simular:
        import shutil
        for v in plano['videos']:
            for letra in sorted(v['hooks']):
                nome = f"{var['prefixo']}{v['vd']}_{letra}"
                dentro = achar(os.path.join(raiz, nome), nome + '.mp4') if os.path.isdir(os.path.join(raiz, nome)) else None
                solta = os.path.join(raiz, nome + '.mp4')
                if dentro and not achar(raiz, nome + '.mp4'):
                    shutil.copyfile(dentro, solta + '.part')   # .part: queda no meio não deixa vídeo pela metade
                    os.rename(solta + '.part', solta)
                    copias += 1
    print(f"== {movidos} arquivos movidos, {prontos} já estavam no lugar, {copias} cópias soltas, {len(faltando)} faltando")
    for f in faltando:
        print(f"   FALTA {f}")
    sys.exit(1 if faltando else 0)

if __name__ == '__main__':
    main()

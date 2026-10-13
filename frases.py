#!/usr/bin/env python3
"""Quebra uma transcrição do Scribe v2 (tempo por palavra) em frases cronometradas e lista
janelas candidatas a gancho (1 a 3 frases seguidas somando 3,5 s a 6,5 s).

uso: python3 frases.py <transcricao.json> [--min 3.5] [--max 6.5]
Serve pra ESCOLHER o gancho lendo, não escolhe sozinho: a decisão editorial é de quem lê.
"""
import json, sys, argparse

FIM_DE_FRASE = ('.', '!', '?', '…')

def carregar(caminho):
    dados = json.load(open(caminho, encoding='utf-8'))
    return [w for w in dados['words'] if w.get('type') == 'word']

def frases(palavras):
    """Agrupa palavras até a pontuação final. Devolve [(inicio, fim, texto)]."""
    saida, atual = [], []
    for w in palavras:
        atual.append(w)
        if w['text'].rstrip('"»)').endswith(FIM_DE_FRASE):
            saida.append((atual[0]['start'], atual[-1]['end'], ' '.join(x['text'] for x in atual)))
            atual = []
    if atual:
        saida.append((atual[0]['start'], atual[-1]['end'], ' '.join(x['text'] for x in atual)))
    return saida

def janelas(fr, minimo, maximo):
    """Sequências de 1 a 3 frases seguidas cuja duração (do 1º ao último word) cabe na faixa."""
    for i in range(len(fr)):
        for n in (1, 2, 3):
            if i + n > len(fr):
                break
            ini, fim = fr[i][0], fr[i + n - 1][1]
            dur = fim - ini
            if minimo <= dur <= maximo:
                yield ini, fim, dur, ' '.join(f[2] for f in fr[i:i + n])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('json')
    ap.add_argument('--min', type=float, default=3.5)
    ap.add_argument('--max', type=float, default=6.5)
    ap.add_argument('--so-frases', action='store_true', help='só lista as frases, sem janelas')
    a = ap.parse_args()
    palavras = carregar(a.json)
    fr = frases(palavras)
    print(f"# {a.json.rsplit('/',1)[-1]} — {len(palavras)} palavras, {len(fr)} frases, {palavras[-1]['end']:.1f}s\n")
    print("## Frases")
    for i, (ini, fim, txt) in enumerate(fr, 1):
        print(f"{i:3d} [{ini:6.2f} → {fim:6.2f}] ({fim-ini:4.1f}s) {txt}")
    if a.so_frases:
        return
    print(f"\n## Janelas de {a.min}s a {a.max}s (frases inteiras)")
    for ini, fim, dur, txt in janelas(fr, a.min, a.max):
        print(f"[{ini:6.2f} → {fim:6.2f}] ({dur:4.1f}s) {txt}")

if __name__ == '__main__':
    main()

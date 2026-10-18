#!/usr/bin/env python3
"""Transcreve um WAV localmente com Whisper (mlx-whisper, Apple Silicon) e grava no MESMO formato do Scribe
(text, language_code, words com text/start/end/type), pra frases.py, blocos_legenda.py e o resto não mudarem.
Alternativa grátis ao Scribe pra testes: a qualidade da grafia é menor e não usa o vocab.txt como keyterms
(só como dica no initial_prompt).
ATENÇÃO (18/10/2026): o fim das palavras sai até ~0,2 s cedo, e o corte do gancho comeu o fim de "facial"
no piloto. Serve pra ler a fala e escolher Reel; pra cortar gancho, use o Scribe.

uso (o uv baixa o mlx-whisper e o modelo na primeira vez, ~1,6 GB):
  uv run --python 3.12 --with mlx-whisper scribe/transcrever_local.py <audio.wav> <saida.json> [vocab.txt]
"""
import json, os, sys

import mlx_whisper

MODELO = os.environ.get('WHISPER_MODELO', 'mlx-community/whisper-large-v3-turbo')


def main():
    audio, saida = sys.argv[1], sys.argv[2]
    vocab = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vocab.txt')
    if not os.path.exists(vocab):
        vocab = os.path.join(os.path.dirname(vocab), 'vocab.exemplo.txt')
    termos = [t.strip() for t in open(vocab, encoding='utf-8') if t.strip() and not t.startswith('#')]
    r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODELO, language='pt', word_timestamps=True,
                               initial_prompt=', '.join(termos), condition_on_previous_text=False)
    words, fim_ant = [], None
    for seg in r['segments']:
        for w in seg.get('words', []):
            txt = w['word'].strip()
            if not txt:
                continue
            ini, fim = round(w['start'], 3), round(w['end'], 3)
            if fim_ant is not None:              # o Scribe intercala "spacing" entre as palavras
                words.append({'text': ' ', 'start': fim_ant, 'end': ini, 'type': 'spacing'})
            words.append({'text': txt, 'start': ini, 'end': fim, 'type': 'word', 'logprob': w.get('probability', 0)})
            fim_ant = fim
    texto = ' '.join(w['text'] for w in words if w['type'] == 'word')
    json.dump({'language_code': 'por', 'language_probability': 1.0, 'text': texto, 'words': words,
               'origem': f'whisper-local:{MODELO}'}, open(saida, 'w', encoding='utf-8'), ensure_ascii=False)
    ws = [w for w in words if w['type'] == 'word']
    print(f"palavras: {len(ws)} | fim: {ws[-1]['end'] if ws else 0:.2f}s | início: {texto[:120]}")


if __name__ == '__main__':
    main()

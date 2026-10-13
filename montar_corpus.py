# Junta as transcrições dos Reels num corpus de fala da Ana, em ordem cronológica, com data, link,
# duração, curtidas e a legenda original de cada vídeo. A fala fica LITERAL: só a grafia da marca é
# corrigida, porque a concordância torta e a repetição são justamente o que soa humano.
# Gera dois arquivos: corpus_fala_ana.md (pra leitura) e corpus_fala_ana.txt (só a fala, pro --corpus do detector).
import json
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402
import re
from pathlib import Path

base = Path(config.REELS_BASE)
grafias = {r'\bsuper ?caso\b': 'SUPERCASO', r'\breconecta\b': 'Reconecta'}


def corrigirGrafia(texto):
    for padrao, certo in grafias.items():
        texto = re.sub(padrao, certo, texto, flags=re.I)
    return texto


blocos = []
for arquivo in sorted((base / 'transcricoes').glob('*.json')):
    # o SSD é exFAT: o macOS cria um "._nome.json" binário do lado de cada arquivo
    if arquivo.name.startswith('._'):
        continue
    dados = json.loads(arquivo.read_text(encoding='utf-8'))
    if 'text' not in dados:
        print(f'sem transcrição (erro da API?): {arquivo.name}')
        continue
    nome = arquivo.stem  # AAAA-MM-DD_shortcode
    data, codigo = nome.split('_', 1)
    metaArquivo = base / 'videos' / f'{nome}.mp4.json'
    meta = json.loads(metaArquivo.read_text(encoding='utf-8')) if metaArquivo.exists() else {}
    fala = corrigirGrafia(dados['text'].strip())
    palavras = [p for p in dados.get('words', []) if p.get('type') == 'word']
    duracao = palavras[-1]['end'] if palavras else 0
    (base / 'transcricoes' / f'{nome}.txt').write_text(fala + '\n', encoding='utf-8')
    blocos.append({'data': data, 'codigo': codigo, 'duracao': duracao, 'meta': meta, 'fala': fala})

with open(base / 'corpus_fala_ana.md', 'w', encoding='utf-8') as md, open(base / 'corpus_fala_ana.txt', 'w', encoding='utf-8') as txt:
    md.write(f'# Corpus de fala (Reels @{config.IG_PERFIL})\n\n')
    for bloco in blocos:
        curtidas = bloco['meta'].get('likes', bloco['meta'].get('like_count'))
        cabecalho = f"## {bloco['data']} · https://www.instagram.com/reel/{bloco['codigo']}/ · {bloco['duracao']:.0f}s"
        if curtidas is not None:
            cabecalho += f' · {curtidas} curtidas'
        md.write(cabecalho + '\n\n')
        legenda = (bloco['meta'].get('description') or '').strip()
        if legenda:
            md.write('**Legenda original:** ' + legenda.replace('\n', ' ') + '\n\n')
        md.write(bloco['fala'] + '\n\n')
        txt.write(bloco['fala'] + '\n\n')

totalPalavras = sum(len(b['fala'].split()) for b in blocos)
totalSegundos = sum(b['duracao'] for b in blocos)
print(f"{len(blocos)} transcrições no corpus ({totalPalavras} palavras, {totalSegundos / 60:.1f} min de fala)")
print(f"leitura: {base / 'corpus_fala_ana.md'}")
print(f"detector: {base / 'corpus_fala_ana.txt'}")

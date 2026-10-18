#!/usr/bin/env python3
"""Importa vídeos brutos (ainda não postados) pro fluxo do projeto.

Cada subpasta de `brutos/entrada/` é UM vídeo final:
  - os vídeos (.mov/.mp4) são os takes da fala, juntados na ordem em que foram gravados;
  - as imagens (.jpg/.png/.heic) são material de apoio (ex.: antes/depois), que o editar_bruto.py põe na tela.

Para cada pasta nova, este script:
  1. normaliza cada take para 1080×1920, 30 fps constantes, H.264 + AAC 48 kHz (celular grava HEVC, 720p,
     às vezes com fps variável, e o render do projeto supõe 1080×1920 CFR);
  2. junta os takes em `dados/videos/<data>_BRnnn.mp4` (o id BRnnn faz o papel do shortcode nos outros scripts);
  3. grava `dados/brutos/BRnnn.json` com a origem, o início de cada take no vídeo juntado e as imagens;
  4. transcreve com o transcrever_reels.sh (só o que ainda não tem transcrição).
Os originais nunca são alterados. Pasta já importada é pulada (o registro fica em dados/brutos/_importados.json).

uso:
  python3 ferramentas/importar_brutos.py                 # todas as pastas novas de brutos/entrada/
  python3 ferramentas/importar_brutos.py teste1          # só esta pasta
"""
import datetime, glob, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

ENTRADA = os.path.join(config.PROJETO, 'brutos', 'entrada')
REG_DIR = os.path.join(config.REELS_BASE, 'brutos')
VIDEOS = os.path.join(config.REELS_BASE, 'videos')
EXT_VIDEO = ('.mov', '.mp4', '.m4v')
EXT_IMAGEM = ('.jpg', '.jpeg', '.png', '.heic', '.webp')


def sonda(arq, entradas):
    r = subprocess.run(['ffprobe', '-v', 'error', *entradas, '-of', 'json', arq], capture_output=True, text=True)
    return json.loads(r.stdout or '{}')


def gravado_em(arq):
    """Data de gravação do metadado do celular; se não houver, a data do arquivo."""
    tags = sonda(arq, ['-show_entries', 'format_tags']).get('format', {}).get('tags', {})
    for k in ('com.apple.quicktime.creationdate', 'creation_time'):
        if tags.get(k):
            try:
                return datetime.datetime.fromisoformat(tags[k].replace('Z', '+00:00'))
            except ValueError:
                pass
    return datetime.datetime.fromtimestamp(os.path.getmtime(arq), datetime.timezone.utc)


def duracao(arq):
    return float(sonda(arq, ['-show_entries', 'format=duration'])['format']['duration'])


def normalizar(origem, destino):
    """1080×1920 30 fps CFR. Deitado ou fora de 9:16 é recortado no centro (sem esticar)."""
    vf = ('scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,'
          'fps=30,setsar=1,format=yuv420p')
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', origem, '-vf', vf,
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-c:a', 'aac', '-b:a', '192k',
                    '-ar', '48000', '-ac', '2', '-movflags', '+faststart', destino], check=True)


def proximo_id(registro):
    usados = [int(v['id'][2:]) for v in registro.values()]
    return f'BR{max(usados, default=0) + 1:03d}'


def importar(pasta, registro):
    nome = os.path.basename(pasta.rstrip('/'))
    arqs = sorted(os.listdir(pasta))
    takes = [os.path.join(pasta, f) for f in arqs if f.lower().endswith(EXT_VIDEO) and not f.startswith('.')]
    imagens = [os.path.join(pasta, f) for f in arqs if f.lower().endswith(EXT_IMAGEM) and not f.startswith('.')]
    if not takes:
        print(f'{nome}: nenhum vídeo, pulando')
        return
    takes.sort(key=gravado_em)
    vid = proximo_id(registro)
    data = gravado_em(takes[0]).astimezone().strftime('%Y-%m-%d')
    tmp = os.path.join(REG_DIR, '_tmp', vid)
    os.makedirs(tmp, exist_ok=True)
    partes, inicios, t = [], [], 0.0
    for n, take in enumerate(takes):
        parte = os.path.join(tmp, f'{n:02d}.mp4')
        print(f'  {vid} take {n + 1}/{len(takes)}: {os.path.basename(take)}')
        normalizar(take, parte)
        partes.append(parte)
        inicios.append({'take': os.path.basename(take), 'inicio': round(t, 3)})
        t += duracao(parte)
    lista = os.path.join(tmp, 'lista.txt')
    with open(lista, 'w', encoding='utf-8') as fp:
        fp.write(''.join(f"file '{p}'\n" for p in partes))
    saida = os.path.join(VIDEOS, f'{data}_{vid}.mp4')
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lista,
                    '-c', 'copy', '-movflags', '+faststart', saida], check=True)
    for p in partes + [lista]:
        os.remove(p)
    os.rmdir(tmp)
    info = {'id': vid, 'pasta': os.path.relpath(pasta, config.PROJETO), 'video': os.path.basename(saida),
            'duracao': round(duracao(saida), 2), 'takes': inicios, 'imagens': imagens}
    json.dump(info, open(os.path.join(REG_DIR, f'{vid}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    registro[nome] = {'id': vid, 'video': info['video']}
    print(f'{nome} → {vid}: {len(takes)} takes, {info["duracao"]:.1f} s, {len(imagens)} imagem(ns) → {saida}')


def main():
    os.makedirs(REG_DIR, exist_ok=True)
    caminho_reg = os.path.join(REG_DIR, '_importados.json')
    registro = json.load(open(caminho_reg, encoding='utf-8')) if os.path.exists(caminho_reg) else {}
    pastas = [os.path.join(ENTRADA, p) for p in sys.argv[1:]] or sorted(
        p for p in glob.glob(os.path.join(ENTRADA, '*')) if os.path.isdir(p))
    novas = 0
    for pasta in pastas:
        if os.path.basename(pasta.rstrip('/')) in registro:
            print(f'{os.path.basename(pasta)}: já importada como {registro[os.path.basename(pasta)]["id"]}')
            continue
        importar(pasta, registro)
        json.dump(registro, open(caminho_reg, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        novas += 1
    if novas:
        subprocess.run(['zsh', os.path.join(config.PROJETO, 'transcrever_reels.sh')], check=False)


if __name__ == '__main__':
    main()

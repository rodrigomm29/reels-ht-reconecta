#!/usr/bin/env python3
"""Prepara um acervo de B-roll pro estilo "dividida": cada clipe vira 1080×956 (a metade de cima da tela),
preenchendo sem tarja (escala Lanczos + corte central), H.264 CRF 18, sem mexer nos originais.

uso:
  python3 ferramentas/normalizar_broll.py <pasta de origem> [<pasta de destino>]   (destino padrão: BROLL_DIR)

- Mantém as subpastas da origem (use subpastas por tema: 01-clinica, 02-reacao...).
- Pula o que já existe no destino (pode rodar de novo depois de pôr clipe novo na origem).
- Por que 956 e não 960: a costura da tela fica em y=956; altura ímpar não existe em yuv420p.
- Clipe com faixa de cor "cheia" (yuvj/pc) é convertido pra faixa limitada; sem isso ele sai lavado.
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

EXT = ('.mp4', '.mov', '.m4v', '.webm', '.mkv', '.gif')


def faixa_cheia(arq):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                        'stream=color_range,pix_fmt', '-of', 'json', arq], capture_output=True, text=True)
    try:
        s = json.loads(r.stdout)['streams'][0]
    except (json.JSONDecodeError, KeyError, IndexError):
        return False
    return s.get('color_range') == 'pc' or str(s.get('pix_fmt', '')).startswith('yuvj')


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    origem = os.path.abspath(sys.argv[1])
    destino = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else config.BROLL_DIR
    if not destino:
        raise SystemExit('defina BROLL_DIR no config.env ou passe a pasta de destino')
    feitos = pulados = falhas = 0
    for raiz, _, arquivos in os.walk(origem):
        for nome in sorted(arquivos):
            if nome.startswith('._') or not nome.lower().endswith(EXT):
                continue
            arq = os.path.join(raiz, nome)
            rel = os.path.relpath(arq, origem)
            saida = os.path.join(destino, os.path.splitext(rel)[0] + '.mp4')
            if os.path.exists(saida):
                pulados += 1
                continue
            os.makedirs(os.path.dirname(saida), exist_ok=True)
            faixa = ':in_range=pc:out_range=tv' if faixa_cheia(arq) else ''
            vf = (f"scale=1080:956:force_original_aspect_ratio=increase:flags=lanczos{faixa},"
                  "crop=1080:956,setsar=1,format=yuv420p")
            r = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', arq, '-vf', vf,
                                '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-color_range', 'tv',
                                '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', saida + '.part.mp4'])
            if r.returncode == 0:
                os.replace(saida + '.part.mp4', saida)
                feitos += 1
                print('ok   ', rel)
            else:
                falhas += 1
                print('FALHA', rel)
    print(f'\n{feitos} normalizados, {pulados} já existiam, {falhas} falhas -> {destino}')
    print('próximo passo: python3 ferramentas/triagem_broll.py')


if __name__ == '__main__':
    main()

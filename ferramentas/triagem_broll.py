#!/usr/bin/env python3
"""Gera a triagem do B-roll (`planos/_broll_triagem.json`) + folhas de contato pra revisar no olho.

uso:
  python3 ferramentas/triagem_broll.py            # usa BROLL_DIR do config.env

Começa com TODOS os clipes em "ok". Abra as folhas em `planos/_broll_folhas/` (3 quadros por clipe, com o
número/nome) e mova pra "excluir" (com o motivo) o que não pode aparecer. Regras que a gente usa:
  - nada de criança (nem de relance, nem personagem criança de desenho);
  - nada sensual ou sugestivo;
  - nada de outra doutora/profissional atendendo (parece concorrente);
  - nada de pessoa falando pra câmera (lê como depoimento falso);
  - nada com texto grande queimado (briga com a legenda e a headline);
  - nada parado demais.
Dra. Fernanda (18/10/2026): o tom é clínica premium e naturalidade, então o melhor B-roll é o dela mesma
(clínica, aparelho, pele em close, bastidor). Exclua também:
  - meme, celebridade ou clipe de humor (briga com o tom);
  - agulha, sangue ou procedimento em close que assuste;
  - paciente identificável sem autorização de imagem;
  - antes/depois que não seja da própria Fernanda.
Na dúvida, exclua. Rodar de novo preserva o que já foi excluído e só acrescenta clipes novos.
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

POR_FOLHA = 12


def duracao(arq):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def quadro(arq, t):
    r = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-ss', f'{t:.2f}', '-i', arq, '-frames:v', '1',
                        '-vf', 'scale=260:230', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True)
    if len(r.stdout) != 260 * 230 * 3:
        return Image.new('RGB', (260, 230), (40, 40, 40))
    return Image.frombytes('RGB', (260, 230), r.stdout)


def main():
    pasta = config.BROLL_DIR
    if not pasta or not os.path.isdir(pasta):
        raise SystemExit('defina BROLL_DIR no config.env (pasta do acervo já normalizado)')
    saida = os.path.join(config.PROJETO, 'planos', '_broll_triagem.json')
    velho = json.load(open(saida, encoding='utf-8')) if os.path.exists(saida) else {'excluir': {}}
    clipes = sorted(os.path.relpath(os.path.join(r, f), pasta) for r, _, fs in os.walk(pasta)
                    for f in fs if f.endswith('.mp4') and not f.startswith('._'))
    excluir = {k: v for k, v in velho.get('excluir', {}).items() if k in clipes}
    ok = [c for c in clipes if c not in excluir]
    json.dump({'pasta': pasta, 'ok': ok, 'excluir': excluir,
               'obs': 'mova pra "excluir" (com motivo) o que não pode aparecer; ver o cabeçalho do triagem_broll.py'},
              open(saida, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    folhas = os.path.join(config.PROJETO, 'planos', '_broll_folhas')
    os.makedirs(folhas, exist_ok=True)
    for i in range(0, len(clipes), POR_FOLHA):
        grupo = clipes[i:i + POR_FOLHA]
        img = Image.new('RGB', (3 * 270 + 20, len(grupo) * 262), (255, 255, 255))
        d = ImageDraw.Draw(img)
        for j, c in enumerate(grupo):
            arq = os.path.join(pasta, c)
            dur = duracao(arq)
            for k, frac in enumerate((0.2, 0.5, 0.8)):
                img.paste(quadro(arq, dur * frac), (10 + k * 270, j * 262 + 26))
            d.text((10, j * 262 + 6), c + ('   [JÁ EXCLUÍDO]' if c in excluir else ''), fill=(0, 0, 0))
        img.save(os.path.join(folhas, f'folha_{i // POR_FOLHA + 1:02d}.jpg'), quality=85)
        print(f'folha {i // POR_FOLHA + 1:02d}: {len(grupo)} clipes')
    print(f'\n{len(ok)} ok, {len(excluir)} excluídos -> {saida}\nfolhas pra revisar: {folhas}')
    if len(ok) < 60:
        print('aviso: com menos de ~60 clipes, as 3 versões de um Reel vão repetir clipe entre si')


if __name__ == '__main__':
    main()

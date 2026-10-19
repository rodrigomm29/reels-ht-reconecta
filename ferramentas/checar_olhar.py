#!/usr/bin/env python3
"""Ela está olhando para a câmera? Mede, quadro a quadro, para onde o rosto aponta (Vision da Apple,
bin/olhar_camera) e acha os trechos em que ela vira o rosto: olhou para o lado, para baixo lendo o roteiro,
virou para quem está filmando. Isso a transcrição não mostra.

Medido em 19/10/2026: de frente para a câmera o yaw fica em ±10°; virando para o lado ou repassando o texto,
−33° a −60°. Conta como fora: |yaw| > 35° por 0,15 s, ou > 20° por 0,5 s (inclinar a cabeça falando é gesto, não desvio). Sem rosto no quadro também conta como "fora".

uso:
  python3 ferramentas/checar_olhar.py <vídeo> [<vídeo> ...]           # trechos fora da câmera ≥ 0,3 s
  python3 ferramentas/checar_olhar.py <vídeo> --de 40 --ate 60        # linha do tempo (yaw a cada 0,1 s)
Funções: `perfil(video, de, ate, fps)` → [(t, yaw ou None)]; `fora(video, ...)` → [(início, fim)].
"""
import argparse, os, subprocess, sys, tempfile

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLHAR = os.path.join(AQUI, 'bin', 'olhar_camera')
YAW_MAX = 20.0        # de frente fica em ±10°; acima de 20° o rosto já está virando
YAW_FORTE = 35.0      # desvio de verdade (olhou pro lado, leu o texto): −37° a −60° nos erros de 19/10
MIN_FORA = 0.15       # com desvio forte, até 0,15 s aparece (Rodrigo viu um giro de 0,3 s no BR003)
MIN_LEVE = 0.5        # entre 20° e 35° é gesto (inclinar a cabeça falando); só conta se durar ≥ 0,5 s


def perfil(video, de=0.0, ate=None, fps=10):
    """[(t, yaw)] no tempo do vídeo; yaw None = sem rosto."""
    with tempfile.TemporaryDirectory() as d:
        cmd = ['ffmpeg', '-nostdin', '-loglevel', 'error', '-ss', f'{de:.3f}']
        if ate is not None:
            cmd += ['-t', f'{max(0.05, ate - de):.3f}']
        cmd += ['-i', video, '-vf', f'fps={fps},scale=360:640', os.path.join(d, 'q%05d.png')]
        subprocess.run(cmd, check=True)
        pngs = sorted(os.path.join(d, f) for f in os.listdir(d))
        if not pngs:
            return []
        out = subprocess.run([OLHAR, *pngs], capture_output=True, text=True).stdout
        yaw = {}
        for linha in out.splitlines():
            p = linha.split('\t')
            yaw[p[0]] = float(p[1]) if len(p) > 2 else None
        return [(round(de + i / fps, 2), yaw.get(p)) for i, p in enumerate(pngs)]


def e_fora(y):
    return y is None or abs(y) > YAW_MAX


def fora(video, de=0.0, ate=None, fps=10, min_fora=MIN_FORA):
    """Trechos (início, fim) em que ela não está de frente para a câmera por pelo menos `min_fora` s."""
    pf = perfil(video, de, ate, fps)
    trechos, ini = [], None
    for t, y in pf + [(None, 0.0)]:
        if t is not None and e_fora(y):
            ini = t if ini is None else ini
        elif ini is not None:
            fim = (t if t is not None else pf[-1][0] + 1 / fps)
            # quadro sem rosto rápido = transição (flash, corte): só conta se durar ≥ MIN_LEVE
            pico = max((abs(y) if y is not None else 0) for tt, y in pf if ini <= tt < fim)
            if (pico > YAW_FORTE and fim - ini >= min_fora - 1e-6) or fim - ini >= MIN_LEVE - 1e-6:
                trechos.append((ini, round(fim, 2)))
            ini = None
    return trechos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('videos', nargs='+')
    ap.add_argument('--de', type=float)
    ap.add_argument('--ate', type=float)
    a = ap.parse_args()
    if a.de is not None:
        for t, y in perfil(a.videos[0], a.de, a.ate):
            print(f"{t:7.2f}  {'sem rosto' if y is None else f'{y:6.1f}°'}  {'FORA' if e_fora(y) else ''}")
        return
    ruim = 0
    for v in a.videos:
        tr = fora(v)
        ruim += bool(tr)
        nome = v.rsplit('/', 1)[-1]
        print(f"{'FORA  ' if tr else 'ok    '} {nome}" + (': ' + ', '.join(f'{x:.1f}–{y:.1f}' for x, y in tr) if tr else ''))
    sys.exit(1 if ruim else 0)


if __name__ == '__main__':
    main()

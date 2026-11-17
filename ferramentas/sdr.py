"""Vídeo HDR do iPhone (HLG/PQ, 10 bits, BT.2020) → cor normal (SDR, BT.709) com o ajuste de tom do macOS.

O ffmpeg daqui não tem zscale: convertido direto, o HDR sai lavado, com a pele branca demais (Caso Hannah, 27/10/2026).
O `avconvert` (AVFoundation) faz o tone mapping certo e já entrega o vídeo de pé (aplica a rotação).
"""
import os, subprocess

HDR = ('arib-std-b67', 'smpte2084')


def eh_hdr(arq):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=color_transfer',
                        '-of', 'default=nw=1:nk=1', arq], capture_output=True, text=True).stdout.split()
    return any(x.strip(',') in HDR for x in r)


def garantir_sdr(arq, cache):
    """Devolve o próprio arquivo, se já é SDR, ou uma cópia SDR em `cache` (feita uma vez só)."""
    if not eh_hdr(arq):
        return arq
    os.makedirs(cache, exist_ok=True)
    saida = os.path.join(cache, os.path.splitext(os.path.basename(arq))[0] + '_sdr.mov')
    if not os.path.exists(saida) or os.path.getmtime(saida) < os.path.getmtime(arq):
        subprocess.run(['avconvert', '--source', arq, '--preset', 'Preset1920x1080', '--output', saida, '--replace'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return saida

#!/usr/bin/env python3
"""Monta anúncios HT a partir de Reels: GANCHO (trecho do meio do vídeo) → flash branco + SFX →
vídeo inteiro do início → (opcional) dissolve pra tela final de CTA. Um render por vez, brutos intocáveis.

uso:
  python3 montar_ht_hooks.py plano.json                      # tudo: prévias + todas as versões + conferência
  python3 montar_ht_hooks.py plano.json --so-previews        # só os clipes curtos dos ganchos
  python3 montar_ht_hooks.py plano.json --so VD003_A         # uma saída (todas as versões dela)
  python3 montar_ht_hooks.py plano.json --so VD003_A --versao TR --forcar   # uma versão só, refazendo

VERSÕES (campo `variantes` do plano; sem ele vale a versão única antiga com `prefixo` e tela final):
  {"id": "HT", "subpasta": "anúncio",     "prefixo": "[26] [40] [HT] ", "tela_final": true}
  {"id": "TR", "subpasta": "trial reels", "prefixo": "[26] [40] [TR] ", "tela_final": false, "dur_max": 179.5}
  - tela_final false: termina onde o Reel termina (micro-fade de 30 ms no áudio pra não estalar).
  - dur_max: se gancho + Reel passar disso, o vídeo INTEIRO é acelerado só o necessário (setpts + atempo:
    o atempo estica o tempo sem mexer no tom da voz). Trial Reel acima de 3 min não é recomendado pra
    não-seguidores. Aceleração acima de `acel_max` (padrão 1,08) vira alerta no relatório.

O plano descreve tela final, SFX, folgas e, por vídeo, os ganchos A e B (início/fim = tempo da
1ª e da última PALAVRA, vindos da transcrição do Scribe). O script calcula o corte real:
  - folga antes/depois sem invadir a palavra vizinha (usa no máximo metade do silêncio disponível);
  - se a fala emenda direto na frase seguinte, congela o último frame (tpad) em vez de deixar o
    flash branco cobrir a última palavra;
  - o flash é fade-out pra branco nos últimos `flash` s do gancho + fade-in do branco nos
    primeiros `flash` s do corpo, SEM sobreposição: áudio e vídeo do corpo começam juntos no 0.
  - SFX alinhado pelo pico dele com o instante do branco cheio (o corte).
  - tela final: mesma regra do montar_tela_final.sh (dissolve por cima da fala, PAUSA congela o
    1º frame da tela, voz com fade curto, alimiter de segurança no mix).
MEMÓRIA: gancho e corpo entram como DUAS entradas do mesmo arquivo (-ss/-t), nunca split → concat
(isso segurava o corpo inteiro em RAM: 68 GB e reboot em 21/09/2026). Pico medido: ~1,1 GB por render.
"""
import argparse, json, math, os, subprocess

def ffprobe(caminho, *entradas):
    return subprocess.run(['ffprobe', '-v', 'error', *entradas, '-of', 'csv=p=0', caminho],
                          capture_output=True, text=True, check=True).stdout.strip()

def duracao(caminho):
    return float(ffprobe(caminho, '-show_entries', 'format=duration'))

def fps_de(caminho):
    num, den = ffprobe(caminho, '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate').split('/')
    return int(round(int(num) / int(den)))

def palavras(transcricao):
    dados = json.load(open(transcricao, encoding='utf-8'))
    return [w for w in dados['words'] if w.get('type') == 'word']

def corte_real(pals, inicio, fim, pad_antes, pad_depois, flash):
    """Devolve (ini_corte, fim_corte, extra_congelado). inicio/fim = tempos da 1ª e última palavra."""
    ant = [w['end'] for w in pals if w['end'] < inicio]
    prox = [w['start'] for w in pals if w['start'] > fim]
    fim_ant = max(ant) if ant else 0.0
    ini_prox = min(prox) if prox else fim + 10.0
    folga_antes = min(pad_antes, max(0.0, (inicio - fim_ant) * 0.5))
    folga_depois = min(pad_depois, max(0.0, (ini_prox - fim) * 0.5))
    ini_corte = max(0.0, inicio - folga_antes)
    fim_corte = fim + folga_depois
    # o flash cobre os últimos `flash` s: se a folga não cobre, congela o último frame por fora
    extra = max(0.0, flash - folga_depois)
    return round(ini_corte, 3), round(fim_corte, 3), round(extra, 3)

def corte_do_gancho(pals, hk, cfg):
    """Corte real de um gancho + ajustes finos vindos do blocos_legenda.py:
    - `ini_corte_min`: começa A/V mais tarde (pula 1-3 quadros em que a legenda anterior ainda está na tela);
    - `fim_video`: último instante de VÍDEO usado; dali em diante o quadro congela (tpad) enquanto o áudio
      termina — evita mostrar o bloco de legenda seguinte, que às vezes entra antes da última palavra acabar.
    Devolve (ini, fim, extra_congelado, fim_video)."""
    ini, fim, extra = corte_real(pals, hk['inicio'], hk['fim'], cfg['pad_antes'], cfg['pad_depois'], cfg['flash'])
    if hk.get('ini_corte_min') is not None:
        ini = round(max(ini, min(hk['ini_corte_min'], hk['inicio'])), 3)
    fim_v = fim
    if hk.get('fim_video') is not None:
        fim_v = round(max(ini + 0.5, min(fim, hk['fim_video'])), 3)
    return ini, fim, extra, fim_v

def luma_frame(caminho, t=None, sseof=None):
    """Luma média de um quadro. Com -sseof muito curto o ffmpeg às vezes não acha quadro nenhum
    (acontece até no Reel original): recua até achar, em vez de devolver 0 falso."""
    tentativas = [sseof, -0.3, -1.0] if sseof is not None else [None]
    for s in tentativas:
        args = ['ffmpeg', '-nostdin', '-loglevel', 'error']
        if s is not None:
            args += ['-sseof', str(s)]
        elif t is not None:
            args += ['-ss', str(t)]
        args += ['-i', caminho, '-frames:v', '1', '-vf', 'scale=64:64,format=gray', '-f', 'rawvideo', '-']
        raw = subprocess.run(args, capture_output=True).stdout
        if raw:
            return round(sum(raw) / len(raw))
    return None

def variantes_do(cfg):
    if cfg.get('variantes'):
        return cfg['variantes']
    return [{'id': None, 'subpasta': '', 'prefixo': cfg['prefixo'], 'tela_final': True}]

def previsao(cfg, var, h, dur_corpo):
    """(duração final prevista, fator de aceleração) de uma versão."""
    if var.get('tela_final', True):
        return h + dur_corpo + duracao(cfg['tela_final']) + cfg['pausa'] - cfg['fusao'], 1.0
    bruto = h + dur_corpo
    lim = var.get('dur_max')
    fator = 1.0
    if lim and bruto > lim:
        fator = math.ceil(bruto / lim * 1000) / 1000        # arredonda pra cima: nunca passa do limite
    return bruto / fator, fator

def render_preview(video, ini, fim, saida, fps):
    dur = fim - ini
    vf = f"setpts=PTS-STARTPTS,fps={fps},scale=540:960,setsar=1,format=yuv420p"
    af = f"asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={dur-0.03:.3f}:d=0.03"
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                    '-ss', f"{ini:.3f}", '-t', f"{dur:.3f}", '-i', video, '-vf', vf, '-af', af,
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart', saida], check=True)

def render_final(cfg, var, video, ini, fim, extra, saida, fim_v=None):
    fps = fps_de(video)
    dur_corpo = duracao(video)
    flash = cfg['flash']
    h = (fim - ini) + extra                              # duração do gancho na tela (antes de acelerar)
    total, fator = previsao(cfg, var, h, dur_corpo)
    com_tela = var.get('tela_final', True)
    atraso_sfx = max(0.0, h - cfg['sfx_pico'])          # pico do SFX cai no branco cheio
    fim_v = fim if fim_v is None else fim_v
    congela_v = round((fim - fim_v) + extra, 3)          # vídeo congelado no fim do gancho
    trim_v = f"trim=end={fim_v - ini:.3f}," if fim_v < fim else ""
    pad_v = f",tpad=stop_duration={congela_v}:stop_mode=clone" if congela_v > 0 else ""
    pad_a = f",apad=pad_dur={extra}" if extra > 0 else ""
    fmt_a = "aformat=sample_rates=48000:channel_layouts=stereo"
    entradas = ['-ss', f"{ini:.3f}", '-t', f"{fim - ini:.3f}", '-i', video,   # 0 = gancho (seek na entrada)
                '-i', video]                                                  # 1 = corpo inteiro
    if com_tela:
        entradas += ['-i', cfg['tela_final']]                                 # 2 = tela
    entradas += ['-i', cfg['sfx']]                                            # último = sfx
    i_sfx = 3 if com_tela else 2
    f = []
    f.append(f"[0:v]{trim_v}setpts=PTS-STARTPTS,fps={fps},scale=1080:1920,setsar=1,"
             f"format=yuv420p{pad_v},fade=t=out:st={h-flash:.3f}:d={flash}:color=white[hv]")
    f.append(f"[0:a]asetpts=PTS-STARTPTS,{fmt_a}{pad_a},"
             f"afade=t=in:d=0.02,afade=t=out:st={h-0.03:.3f}:d=0.03[ha]")
    f.append(f"[1:v]fps={fps},scale=1080:1920,setsar=1,format=yuv420p,fade=t=in:st=0:d={flash}:color=white[bv]")
    f.append(f"[1:a]{fmt_a}[ba]")
    f.append("[hv][ha][bv][ba]concat=n=2:v=1:a=1[cv][ca]")
    ms = int(round(atraso_sfx * 1000))
    f.append(f"[{i_sfx}:a]{fmt_a},volume={cfg['sfx_gain_db']}dB,adelay=delays={ms}|{ms}:all=1[sfx]")
    f.append("[ca][sfx]amix=inputs=2:duration=first:normalize=0[mv]")
    if com_tela:
        pausa, fusao, fade_voz = cfg['pausa'], cfg['fusao'], cfg['fade_voz']
        pad_tela = f",tpad=start_duration={pausa}:start_mode=clone" if pausa > 0 else ""
        # xfade exige a mesma base de tempo nos dois lados: o concat sai em 1/1000000 e a tela em 1/fps
        f.append(f"[2:v]fps={fps},scale=1080:1920,setsar=1,format=yuv420p{pad_tela},settb=AVTB[tv]")
        f.append("[cv]settb=AVTB[cv2]")
        f.append(f"[cv2][tv]xfade=transition=fade:duration={fusao}:offset={h+dur_corpo-fusao:.3f}[vout]")
        f.append(f"[mv]afade=t=out:st={h+dur_corpo-fade_voz:.3f}:d={fade_voz},apad=whole_dur={total:.3f},"
                 f"alimiter=limit=0.89:level=false[aout]")
    else:
        bruto = h + dur_corpo
        if fator > 1.0:
            # atempo muda a duração sem mudar o tom; setpts+fps acompanha no vídeo (descarta quadros)
            f.append(f"[cv]setpts=PTS/{fator},fps={fps}[vout]")
            f.append(f"[mv]afade=t=out:st={bruto-0.03:.3f}:d=0.03,atempo={fator},"
                     f"alimiter=limit=0.89:level=false[aout]")
        else:
            f.append("[cv]null[vout]")
            f.append(f"[mv]afade=t=out:st={bruto-0.03:.3f}:d=0.03,alimiter=limit=0.89:level=false[aout]")
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', *entradas,
                    '-filter_complex', ";".join(f), '-map', '[vout]', '-map', '[aout]',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', saida], check=True)
    return h / fator, total, fps, fator

def frames_conferencia(saida, h, total, destino_png):
    """4 frames lado a lado: abertura, fim do gancho, início do corpo, último frame (tela ou fim do Reel)."""
    pontos = [0.0, max(0.0, h - 0.20), h + 0.20, max(0.0, total - 0.10)]
    entradas = []
    for t in pontos:
        entradas += ['-ss', f"{t:.3f}", '-i', saida]
    filtro = "".join(f"[{i}:v]scale=270:480[f{i}];" for i in range(4)) + "[f0][f1][f2][f3]hstack=inputs=4"
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', *entradas,
                    '-filter_complex', filtro, '-frames:v', '1', destino_png], check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plano')
    ap.add_argument('--so-previews', action='store_true')
    ap.add_argument('--so', help='só esta saída, ex.: VD003_A (todas as versões dela)')
    ap.add_argument('--versao', help='só esta versão, ex.: HT ou TR')
    ap.add_argument('--forcar', action='store_true', help='re-renderiza mesmo que a saída já exista completa')
    a = ap.parse_args()
    cfg = json.load(open(a.plano, encoding='utf-8'))
    destino = cfg['destino']
    acel_max = cfg.get('acel_max', 1.08)
    pasta_prev = os.path.join(destino, '_ganchos-previa')
    pasta_conf = os.path.join(destino, '_conferencia')
    for p in (destino, pasta_prev, pasta_conf):
        os.makedirs(p, exist_ok=True)
    relatorio = []
    for v in cfg['videos']:
        pals = palavras(v['transcricao'])
        dur_corpo = duracao(v['arquivo'])
        fps = fps_de(v['arquivo'])
        for letra, hk in sorted(v['hooks'].items()):
            rotulo = f"{v['vd']}_{letra}"
            if a.so and a.so != rotulo:
                continue
            ini, fim, extra, fim_v = corte_do_gancho(pals, hk, cfg)
            h = fim - ini + extra
            base = {'reel': v['shortcode'], 'gancho': hk['texto'], 'palavra_ini': hk['inicio'],
                    'palavra_fim': hk['fim'], 'corte_ini': ini, 'corte_fim': fim, 'congelado': extra,
                    'dur_gancho': round(h, 3), 'fim_video': fim_v if fim_v < fim else None}
            prev = os.path.join(pasta_prev, f"{rotulo}.mp4")
            render_preview(v['arquivo'], ini, fim, prev, fps)
            print(f"[{rotulo}] gancho {ini:.2f}→{fim:.2f} ({h:.2f}s, congela {extra}s)  prévia ok")
            if a.so_previews:
                relatorio.append({'saida': rotulo, **base})
                continue
            for var in variantes_do(cfg):
                if a.versao and var.get('id') != a.versao:
                    continue
                chave = f"{var['id']} {rotulo}" if var.get('id') else rotulo
                pasta = os.path.join(destino, var.get('subpasta', ''))
                os.makedirs(pasta, exist_ok=True)
                final = os.path.join(pasta, f"{var['prefixo']}{rotulo}.mp4")
                # orgânico organizado por organizar_organico.py: o vídeo mora em <pasta>/<nome>/<nome>.mp4
                pasta_propria = os.path.join(pasta, f"{var['prefixo']}{rotulo}")
                if os.path.isdir(pasta_propria):
                    final = os.path.join(pasta_propria, f"{var['prefixo']}{rotulo}.mp4")
                total_prev, fator_prev = previsao(cfg, var, h, dur_corpo)
                # retomada: saída completa (duração bate com a prevista) não é refeita; parcial é refeita
                if not a.forcar and os.path.exists(final):
                    try:
                        if abs(duracao(final) - total_prev) <= 0.15:
                            relatorio.append({'saida': chave, 'versao': var.get('id'), **base,
                                              'arquivo': os.path.relpath(final, destino), 'fps': fps,
                                              'aceleracao': fator_prev, 'dur_prevista': round(total_prev, 2),
                                              'dur_real': round(duracao(final), 2),
                                              'luma_frame0': luma_frame(final, t=0),
                                              'luma_final': luma_frame(final, sseof=-0.05),
                                              'alertas': ['ACELERAÇÃO ACIMA DO TETO'] if fator_prev > acel_max else []})
                            print(f"   [{chave}] já pronto, pulando")
                            continue
                        print(f"   [{chave}] arquivo existente com duração errada, refazendo")
                    except Exception:
                        print(f"   [{chave}] arquivo existente ilegível (render interrompido), refazendo")
                h_out, total, fps, fator = render_final(cfg, var, v['arquivo'], ini, fim, extra, final, fim_v)
                dur_real = duracao(final)
                png = os.path.join(pasta_conf, f"{var['id']}_{rotulo}.png" if var.get('id') else f"{rotulo}.png")
                frames_conferencia(final, h_out, total, png)
                l0 = luma_frame(final, t=0)
                lf = luma_frame(final, sseof=-0.05)
                alerta = []
                if l0 is None or l0 < 25: alerta.append("ABRE NO PRETO")
                if abs(dur_real - total) > 0.15: alerta.append('DURAÇÃO NÃO FECHA')
                if fator > acel_max: alerta.append('ACELERAÇÃO ACIMA DO TETO')
                if var.get('dur_max') and dur_real > var['dur_max'] + 0.1: alerta.append('PASSOU DO LIMITE')
                relatorio.append({'saida': chave, 'versao': var.get('id'), **base,
                                  'arquivo': os.path.relpath(final, destino), 'fps': fps, 'aceleracao': fator,
                                  'dur_prevista': round(total, 2), 'dur_real': round(dur_real, 2),
                                  'luma_frame0': l0, 'luma_final': lf, 'alertas': alerta})
                acel = f"  acel {fator:.3f}×" if fator > 1 else ""
                print(f"   [{chave}] {os.path.basename(final)}  {dur_real:.2f}s (previsto {total:.2f}){acel}  "
                      f"fps {fps}  luma0 {l0}  lumaFim {lf}  {' '.join(alerta) or 'ok'}")
    # com --so, cada processo grava o próprio relatório; nome sem ":" porque o exFAT não aceita
    sufixo = "_".join(x for x in (a.so, a.versao) if x)
    nome_rel = f"_relatorio_{sufixo}.json" if sufixo else "_relatorio.json"
    with open(os.path.join(destino, nome_rel), 'w', encoding='utf-8') as fp:
        json.dump(relatorio, fp, ensure_ascii=False, indent=2)
    print(f"== {len(relatorio)} saídas; relatório em {destino}/{nome_rel}")

if __name__ == '__main__':
    main()

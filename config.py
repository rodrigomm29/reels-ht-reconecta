"""Configuração única do projeto: lê o `config.env` da raiz (fora do git) e deixa variável de ambiente
sobrescrever. Os scripts .sh leem o mesmo arquivo pelo `config.sh`.

Copie `config.exemplo.env` para `config.env` e ajuste os caminhos da SUA máquina.
"""
import os

PROJETO = os.path.dirname(os.path.abspath(__file__))


def _ler_env(caminho):
    valores = {}
    if not os.path.exists(caminho):
        return valores
    for linha in open(caminho, encoding='utf-8'):
        linha = linha.strip()
        if not linha or linha.startswith('#') or '=' not in linha:
            continue
        chave, valor = linha.split('=', 1)
        chave = chave.strip().removeprefix('export ').strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in '"\'':
            valor = valor[1:-1]
        valores[chave] = valor
    return valores


_ARQ = _ler_env(os.path.join(PROJETO, 'config.env'))


def valor(chave, padrao=None):
    """Ambiente > config.env > padrão. Expande ~, $HOME, $PROJETO e outras variáveis já definidas."""
    v = os.environ.get(chave, _ARQ.get(chave))
    if v is None or v == '':
        v = padrao
    if isinstance(v, str):
        ambiente = {**_ARQ, **os.environ, 'PROJETO': PROJETO}
        for _ in range(3):                      # deixa uma variável usar outra (ex.: KIT_DIR=$REELS_BASE/kit_peles)
            for k, x in ambiente.items():
                v = v.replace('${' + k + '}', x).replace('$' + k + '/', x + '/')
        v = os.path.expanduser(v)
    return v


def expandir(texto):
    """Troca ${VAR} (do config.env ou do ambiente) e ~ num texto, ex.: o destino do planos/_template.json."""
    return valor('__nenhuma__', texto)


def obrigatorio(chave, para_que):
    v = valor(chave)
    if not v:
        raise SystemExit(f'Falta {chave} no config.env ({para_que}). Veja config.exemplo.env e o README.')
    return v


# ---- pastas
REELS_BASE = valor('REELS_BASE', os.path.join(PROJETO, 'dados'))          # videos/, transcricoes/, audio/
SAIDA_DIR = valor('SAIDA_DIR', os.path.join(PROJETO, 'saida'))             # vídeos prontos
KIT_DIR = valor('KIT_DIR', os.path.join(REELS_BASE, 'kit_peles'))           # efeitos e SFX (kit.json)
BROLL_DIR = valor('BROLL_DIR', '')                                           # acervo 1080×956 (estilo dividida)
FONTES_DIR = valor('FONTES_DIR', os.path.join(PROJETO, 'fontes'))
LUTS_DIR = valor('LUTS_DIR', '')
LUTS = [x for x in (valor('LUT_1', ''), valor('LUT_2', ''), valor('LUT_3', '')) if x]
CINEVA_DIR = valor('CINEVA_DIR', '')
PACK_EDITOR_DIR = valor('PACK_EDITOR_DIR', '')
TELA_FINAL = valor('TELA_FINAL', '')

# ---- fontes (Inter vem no repo; as outras são opcionais e pagas)
FONTE_FORTE = valor('FONTE_FORTE', os.path.join(FONTES_DIR, 'Grift-Black.ttf'))
FONTE_VHS = valor('FONTE_VHS', os.path.join(FONTES_DIR, '403DegradMono-Bold.ttf'))
FONTE_NATIVA = valor('FONTE_NATIVA', os.path.join(FONTES_DIR, 'Inter-SemiBold.otf'))
FONTE_LEGENDA = valor('FONTE_LEGENDA', os.path.join(FONTES_DIR, 'Inter-Bold.otf'))

# ---- contas e conteúdo
IG_PERFIL = valor('IG_PERFIL', 'drafernanda.porto')
NAVEGADOR = valor('NAVEGADOR', 'chrome')
CONTA_INSTAGRAM = valor('CONTA_INSTAGRAM', '@' + IG_PERFIL)
CONTA_TIKTOK = valor('CONTA_TIKTOK', '@' + IG_PERFIL)
HASHTAGS = valor('HASHTAGS', '#rejuvenescimentofacial #harmonizacaofacial #ultherapy #joaopessoa')
FUSO = valor('FUSO', 'America/Sao_Paulo')
DIVIDIDA_Y_PADRAO = int(valor('DIVIDIDA_Y_PADRAO', '300'))
# faixa onde fica a legenda queimada dos Reels originais (1080×1920), lida pelo OCR do blocos_legenda.py
LEGENDA_FAIXA_Y = valor('LEGENDA_FAIXA_Y', '1200')          # número ou "auto" (medida por vídeo)
LEGENDA_FAIXA_H = int(valor('LEGENDA_FAIXA_H', '440'))
LEGENDA_MIN_TEXTO = int(valor('LEGENDA_MIN_TEXTO', '240'))   # pixels brancos mínimos pra contar como legenda
TITULO_CY = int(valor('TITULO_CY', '1130'))   # centro vertical da caixa de título (pele texto) em 1080×1920

# ---- segredos: variável de ambiente primeiro; no Mac, cai pro Keychain (nunca impressos)
KEYCHAIN_PUBLER = valor('KEYCHAIN_PUBLER', 'reconecta-publer')
KEYCHAIN_ELEVENLABS = valor('KEYCHAIN_ELEVENLABS', 'elevenlabs-api-key')


def lut(i):
    """Caminho da i-ésima LUT (gira entre as que existirem); None se não houver nenhuma configurada."""
    if not LUTS:
        return None
    nome = LUTS[i % len(LUTS)]
    return nome if os.path.isabs(nome) else os.path.join(LUTS_DIR, nome)

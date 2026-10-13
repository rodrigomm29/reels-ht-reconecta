#!/usr/bin/env python3
"""Agenda no TikTok ou no Instagram (Trial Reels) de @anadareconecta, pela API REST oficial do Publer, os
vídeos da fila do orgânico. Uma rede por rodada: --rede tiktok | --rede instagram.

Lê `publicar/filas/<fila>.json` (montada pelo fila.py; uma fila por dia, ex.: SEM41-terca), sobe cada mp4
pendente pro Publer em streaming do disco (POST /media), cria o post agendado (POST /posts/schedule),
acompanha o job (GET /job_status/{id}) e grava o resultado em item.estado.<rede> depois de CADA vídeo.
Em erro, grava e PARA. O publer_tiktok.py virou um invólucro deste arquivo com --rede tiktok fixo.

Doc oficial seguida (índice em https://publer.com/docs/llms.txt):
  lida em 05/10/2026 (TikTok):
  - base https://app.publer.com/api/v1 ; headers "Authorization: Bearer-API <chave>" + "Publer-Workspace-Id"
  - limite: 100 requisições por janela fixa de 2 min (HTTP 429 + X-RateLimit-Reset)
  - upload direto: multipart/form-data, campo "file" com Content-Type video/mp4 (octet-stream a API real recusa: HTTP 400
    "File is not supported", medido 06/10), até 200 MB, síncrono, devolve id
  - vídeo no TikTok: networks.tiktok {type "video", text <= 2200, media [{id, type, thumbnails[]}],
    details {privacy, comment, duet, stitch}} ; accounts[].scheduled_at em ISO 8601 com fuso, >= 1 min no futuro
  - as miniaturas (thumbnails[]) saem de GET /media/{id}; o upload só devolve uma "thumbnail" solta
  - media[].path NÃO vai no post: é opcional e, enquanto o Publer processa o vídeo, é um endereço provisório
  - conta (GET /accounts) só tem id, provider, name (nome de exibição), social_id, picture, type: não há @username
  relida em 06/10/2026 (Instagram), páginas getting-started/rate-limits, api-reference/{accounts,posts,media},
  posting/create-posts (+ networks, media-handling, content-types/video-posts e
  platform-specific-formats/reels-shorts-and-stories) e a central de ajuda "How to schedule Instagram Trial Reels":
  - Reel: networks.instagram {type "video", text, media [{id, type "video", thumbnails[], default_thumbnail}],
    details {type "reel", trial_reel "MANUAL"|"SS_PERFORMANCE"}}; trial_reel só vale com details.type "reel";
    MANUAL = fica em teste até você liberar pros seguidores no app; SS_PERFORMANCE = o Instagram pode liberar
    sozinho se for bem (ajuda: "usually within 72 hours"); com Trial ligado "the Reel will not be posted to your
    feed" (por isso o corpo NÃO leva details.feed); exige conta com 1.000+ seguidores
  - default_thumbnail = índice da miniatura, "0-based" (content-types/video-posts); usamos 0 (a 1ª miniatura)
  - conta Instagram: provider "instagram", type "business"; legenda até 2.200 caracteres (networks)
  - limite diário do Publer (rolling 24 h em UTC): "Instagram Posts & Reels" 25 no plano Business (TikTok 25);
    a Meta permite 100 posts via API por conta a cada 24 h: vale o menor, 25
  - duração do Reel: a página de Reels e a de networks dizem "3–90 seconds"; a de vídeo diz "Reels: 3 s–15 min"
    e a Meta aceita 3 s–15 min/300 MB. Conflito: acima de 90 s só AVISA; abaixo de 3 s ou acima de 15 min bloqueia
  - o upload devolve validity.<rede> (compatibilidade calculada pelo Publer); validity.instagram.reel false
    = "cannot be used for Instagram Reels": aí o item para na etapa "midia" (nada criado, dá pra repetir)
  - GET /posts filtra por account_ids[], from/to (data) e state; PostSummary traz id, text, state, account_id,
    scheduled_at: a conciliação por conta + horário + começo da legenda serve igual pras duas redes
  relida em 06/10/2026 (revisão): quickstart, api-reference/{posts,accounts,media}, create-posts, rate-limits:
  - job_status: plan.locked = "Whether the workspace is locked" (em data.result.plan; na quickstart, plan no topo);
    estados de post agendado que não saem: scheduled_locked, scheduled_reauth, scheduled_pending, scheduled_declined
  - "There's another post at this time. A one minute gap is required between posts" (quickstart): 1 min por conta
  - GET /media/{id} traz validity "derived from size, dimensions, format and duration" (vídeo já processado)
  - Account: id, provider, name, social_id, picture, type (Instagram = "business"); "status" só no exemplo

Proteção contra post duplicado (não existe chave de idempotência na API):
  - o item vira "agendando" na fila ANTES do POST /posts/schedule (e ganha o job_id logo que ele chega); todo
    POST também vai pro diário filas/<fila>.posts.log (só acréscimo);
  - "agendando" ou erro depois do POST nunca é repostado direto: a rodada seguinte confere no Publer
    (job_status e GET /posts) e marca agendado_publer se achar; sem confirmação, só sai com --forcar <id>;
    --forcar é recusado enquanto o job antigo ainda está rodando, e a tentativa antiga fica em "anteriores";
  - uma execução por fila, de qualquer rede (trava em filas/<fila>.lock, a mesma do fila.py montar/intercalar)
    e uma por rede, de qualquer fila (filas/.rede-<rede>.lock); o status é relido antes de cada vídeo e cada
    gravação só acontece se o item ainda estiver como o script deixou (compare-and-swap); se depois do POST o
    item tiver voltado pra "pendente" (cópia velha da fila gravada por cima), o registro do POST é regravado;
  - SIGHUP (fechar o Terminal) e SIGTERM viram interrupção normal e o erro fica gravado;
  - cada rede só lê e grava item.estado.<rede>: postado_manual (ex.: segunda postada pelo mLabs) nunca entra.

Post criado mas travado (workspace travado, conta pedindo reautorização, aprovação pendente/recusada): depois do
job, plan.locked e o estado do post são conferidos; travado vira "agendado_travado" (o post existe, não sai
sozinho), o lote PARA no 1º, e a rodada seguinte confere esses itens antes de subir qualquer vídeo.

Agenda: --horarios "09:00,13:00,19:00" (como antes) OU --intervalo MIN com --por-dia N: N horários a partir da
hora do --inicio, de MIN em MIN; o que sobra vai pro dia seguinte, no mesmo horário de início. Horário a menos
de 1 min de post já agendado na conta (em qualquer fila OU no Publer, inclusive posts feitos fora das filas) é
pulado, e nenhuma janela de 24 h pode passar do limite diário da rede (filas + Publer + o plano). Horário que já
passou (ou falta < 15 min) é pulado com AVISO no plano; se a rodada parar por horário, rode o MESMO comando.

Segredos ficam no Keychain e nunca são impressos nem gravados:
  security add-generic-password -s reconecta-publer -a api-key -U -w        (o -w no fim faz o macOS PEDIR a chave)
  security add-generic-password -s reconecta-publer -a workspace-id -U -w   (opcional)

uso:
  python3 publer_postar.py contas
  python3 publer_postar.py postar SEM41-terca --rede instagram --inicio "2026-10-07 08:00" --intervalo 20 --por-dia 21 --simular
  python3 publer_postar.py postar SEM41-terca --rede instagram --inicio "2026-10-07 08:00" --intervalo 20 --por-dia 21 --max 1
  python3 publer_postar.py postar SEM41-terca --rede tiktok --inicio "2026-10-07 09:00" --horarios "09:00,13:00,19:00"
  python3 publer_postar.py postar SEM41-terca --rede instagram --inicio "2026-10-08 08:00" --intervalo 20 --por-dia 21 --forcar VD005_A
  python3 publer_postar.py autoteste
"""
import argparse
import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))   # raiz do projeto, onde mora o config.py
import config  # noqa: E402
import datetime as dt
import email.utils
import hashlib
import http.client
import json
import mimetypes
import os
import re
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import uuid
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import fila as filamod  # noqa: E402  carregar/caminho da fila (a gravação daqui usa .part de nome único)

BASE = 'https://app.publer.com/api/v1'
FUSO = ZoneInfo('America/Sao_Paulo')
KC_SERVICO = config.KEYCHAIN_PUBLER
BLOCO = 1024 * 1024                    # upload em blocos de 1 MiB: o vídeo nunca entra inteiro na memória
LIMITE_UPLOAD = 200 * 1000 * 1000      # doc: "200MB per file" (lido no sentido mais conservador)
LIMITE_TEXTO = 2200                    # doc: legenda máx. 2.200 caracteres (TikTok e Instagram)
LIMITE_TIKTOK_DIA = 25                 # doc: TikTok Videos no plano Business, por 24 h corridas (UTC)
LIMITE_INSTAGRAM_DIA = min(25, 100)    # doc Publer: Instagram Posts & Reels 25/24 h (Business); Meta: 100/24 h via API
PRIVACIDADES = ('PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR', 'SELF_ONLY')
TRIAL_MODOS = ('MANUAL', 'SS_PERFORMANCE')   # doc: networks.instagram.details.trial_reel
TRIAL_PADRAO = 'MANUAL'                # decisão do Sávio (06/10/2026): só a vencedora vai pros seguidores, à mão
# o que muda por rede; durações em segundos (None = sem checagem local)
REDES = {
    'tiktok': {'nome': 'TikTok', 'provider': 'tiktok', 'limite_dia': LIMITE_TIKTOK_DIA, 'max_hashtags': None,
               'dur_min': None, 'dur_max': None, 'dur_aviso': None, 'tipo_conta': None},
    'instagram': {'nome': 'Instagram', 'provider': 'instagram', 'limite_dia': LIMITE_INSTAGRAM_DIA,
                  'max_hashtags': 30,                    # Meta: no máx. 30 hashtags por legenda
                  'dur_min': 3, 'dur_max': 15 * 60,      # Meta (e a página de vídeo do Publer): 3 s–15 min
                  'dur_aviso': 90,                       # páginas de Reels/networks do Publer: "3–90 seconds"
                  'tipo_conta': 'business'},             # doc (Accounts): Instagram só existe como "business" na API
}
TIPOS_CONTA_DOC = ('page', 'profile', 'group', 'business', 'channel', 'location', 'blog')   # enum Account.type
# status que contam como post (possivelmente) já no Publer; "agendado_travado" = o post existe, mas o Publer o
# segurou (workspace travado, conta pedindo reautorização, aprovação pendente/recusada): não sai sozinho
OCUPADOS = ('agendado_publer', 'agendando', 'agendado_travado')
TRAVADO = 'agendado_travado'
AVISO_TRAVADO = ('o post existe no Publer, mas não vai sair assim: resolva lá (destravar o workspace, reconectar a '
                 'conta, aprovar o post) e rode de novo, que a rodada confere antes de tudo; se apagar o post no '
                 'Publer, repita com --forcar <id>')
# filtros de GET /posts (doc, "State Values") que indicam post agendado que NÃO vai sair como está
FILTROS_TRAVA = ('scheduled_locked', 'scheduled_reauth', 'scheduled_pending', 'scheduled_declined')
HORARIOS_PADRAO = '09:00,13:00,19:00'
MARGEM_PLANO = dt.timedelta(minutes=15)    # no plano, horário a menos de 15 min de agora é pulado
MARGEM_POST = dt.timedelta(minutes=2)      # na hora de agendar, tem que faltar >= 2 min (doc exige >= 1 min)
TIMEOUT_JSON = 60
TIMEOUT_UPLOAD = 300                   # por operação de socket: generoso pra 140 MB em rede lenta
TENTATIVAS = 6
# ritmo das esperas (segundos); o autoteste encurta
ESPERA = {'job_ini': 2.0, 'job_max': 15.0, 'job_total': 600.0,
          'midia_ini': 3.0, 'midia_max': 15.0, 'midia_total': 300.0,
          'backoff': 5.0}
DIAS = ('seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom')
FIM_JOB = ('complete', 'completed')
JOB_RODANDO = ('working', 'pending', 'queued', 'processing')   # doc: "working" = "The job is still processing"
# erro nestas etapas = nada foi criado no Publer, dá pra repetir com --repetir-erros.
# Erro em "agendar"/"job" (ou status "agendando") = o post PODE existir: precisa conferir no Publer antes.
ETAPAS_REPETIVEIS = ('upload', 'midia', 'montar', 'recusado')
PULADO_CONFERIR = 'aguardando conferência no Publer'


class ErroPubler(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


class PostRecusado(ErroPubler):
    """O job terminou com falha explícita do Publer: o post não foi criado."""


class HorarioPassou(Exception):
    """O horário do slot ficou perto demais/no passado antes de agendar: para sem marcar o item."""


class ConflitoFila(Exception):
    """O item mudou na fila (à mão ou por outro programa) desde a última leitura: para sem sobrescrever."""


# ---------------------------------------------------------------- segredos (Keychain)

def ler_keychain(conta):
    try:
        r = subprocess.run(['security', 'find-generic-password', '-s', KC_SERVICO, '-a', conta, '-w'],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def obter_chave():
    chave = os.environ.get('PUBLER_API_KEY') or config.valor('PUBLER_API_KEY') or ler_keychain('api-key')
    if not chave:
        sys.exit('Chave do Publer não encontrada no Keychain (serviço "reconecta-publer", conta "api-key").\n'
                 'Grave assim (com o -w no FIM o macOS pede a chave, e ela não passa pelo histórico do shell):\n'
                 '  security add-generic-password -s reconecta-publer -a api-key -U -w\n'
                 'A chave sai do Publer em Settings > Access & Login > API Keys (plano Business;\n'
                 'a central de ajuda do Publer também chama essa tela de "API & Webhooks"),\n'
                 'com os escopos workspaces, accounts, posts e media.')
    return chave


# ---------------------------------------------------------------- cliente HTTP (só biblioteca padrão)

def decodificar(bruto):
    try:
        return json.loads(bruto.decode('utf-8')) if bruto else None
    except (UnicodeDecodeError, ValueError):
        return None


def mensagem_erro(dado, bruto):
    if isinstance(dado, dict):
        for k in ('errors', 'error', 'message'):
            v = dado.get(k)
            if v:
                return '; '.join(map(str, v)) if isinstance(v, list) else str(v)
    return (bruto or b'').decode('utf-8', 'replace')[:300] or '(sem corpo)'


def desembrulhar(dado):
    """A doc mostra dois envelopes: {"job_id": ...} e {"success": true, "data": {...}}. Aceita os dois."""
    if isinstance(dado, dict) and 'success' in dado and isinstance(dado.get('data'), (dict, list)):
        return dado['data']
    return dado


def segundos_de_espera(cab, tentativa):
    """Quanto esperar num 429: Retry-After (segundos ou data) > X-RateLimit-Reset (UNIX) > backoff exponencial."""
    ra = cab.get('Retry-After')
    if ra:
        try:
            return max(1.0, float(ra))
        except ValueError:
            try:
                return max(1.0, email.utils.parsedate_to_datetime(ra).timestamp() - time.time())
            except (TypeError, ValueError):
                pass
    reset = cab.get('X-RateLimit-Reset')
    if reset:
        try:
            falta = float(reset) - time.time() + 1
            if falta > 0:
                return min(falta, 300.0)
        except ValueError:
            pass
    return min(ESPERA['backoff'] * (2 ** tentativa), 120.0)


def nome_ascii(nome):
    s = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode()
    for c in '"\\\r\n':
        s = s.replace(c, '_')
    return s.strip() or 'video.mp4'


class Cliente:
    def __init__(self, chave, workspace=None, base=BASE):
        self._chave = chave
        self.workspace = workspace
        u = urllib.parse.urlsplit(base)
        self._https = u.scheme == 'https'
        self._host, self._porta = u.hostname, u.port
        self._prefixo = u.path.rstrip('/')

    def __repr__(self):
        return f'<Cliente Publer {self._host}>'          # nunca mostra a chave

    def _conexao(self, timeout):
        cls = http.client.HTTPSConnection if self._https else http.client.HTTPConnection
        return cls(self._host, self._porta, timeout=timeout)

    def _headers(self, com_workspace):
        h = {'Authorization': f'Bearer-API {self._chave}', 'Accept': 'application/json',
             'User-Agent': 'reconecta-publer-postar/1.1'}
        if com_workspace:
            if not self.workspace:
                raise ErroPubler('workspace do Publer não definido')
            h['Publer-Workspace-Id'] = self.workspace
        return h

    @staticmethod
    def _respeitar_limite(cab):
        """Doc: com X-RateLimit-Remaining 0, a próxima vaga abre em X-RateLimit-Reset (timestamp UNIX)."""
        try:
            resta, reset = cab.get('X-RateLimit-Remaining'), cab.get('X-RateLimit-Reset')
            if resta is not None and reset and int(resta) <= 0:
                falta = float(reset) - time.time() + 1
                if 0 < falta <= 300:
                    print(f'  limite de requisições do Publer zerado; aguardando {falta:.0f}s', flush=True)
                    time.sleep(falta)
        except ValueError:
            pass

    def json(self, metodo, caminho, corpo=None, consulta=None, com_workspace=True):
        """Requisição JSON. GET repete em queda de rede/5xx; qualquer método repete em 429 (não foi processado)."""
        url = self._prefixo + caminho + ('?' + urllib.parse.urlencode(consulta, doseq=True) if consulta else '')
        h = self._headers(com_workspace)
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo, ensure_ascii=False).encode('utf-8')
            h['Content-Type'] = 'application/json'
        idempotente = metodo == 'GET'
        for tentativa in range(TENTATIVAS):
            ultima = tentativa == TENTATIVAS - 1
            conn = self._conexao(TIMEOUT_JSON)
            try:
                conn.request(metodo, url, body=dados, headers=h)
                resp = conn.getresponse()
                status, cab, bruto = resp.status, resp.headers, resp.read()
            except (OSError, http.client.HTTPException) as e:
                if idempotente and not ultima:
                    espera = min(2.0 * 2 ** tentativa, 30.0)
                    print(f'  falha de rede em {metodo} {caminho} ({type(e).__name__}); repito em {espera:.0f}s', flush=True)
                    time.sleep(espera)
                    continue
                raise ErroPubler(f'falha de rede em {metodo} {caminho}: {type(e).__name__}: {e}') from None
            finally:
                conn.close()
            if status == 429 and not ultima:
                espera = segundos_de_espera(cab, tentativa)
                print(f'  Publer devolveu 429 (limite) em {metodo} {caminho}; aguardando {espera:.0f}s', flush=True)
                time.sleep(espera)
                continue
            if status >= 500 and idempotente and not ultima:
                espera = min(2.0 * 2 ** tentativa, 30.0)
                print(f'  Publer devolveu {status} em {metodo} {caminho}; repito em {espera:.0f}s', flush=True)
                time.sleep(espera)
                continue
            self._respeitar_limite(cab)
            dado = decodificar(bruto)
            if status >= 400:
                raise ErroPubler(f'{metodo} {caminho} -> HTTP {status}: {mensagem_erro(dado, bruto)}', status)
            return dado
        raise ErroPubler(f'{metodo} {caminho}: tentativas esgotadas')

    def upload(self, caminho_arquivo, campos=None, progresso=True):
        """POST /media multipart em STREAMING: Content-Length calculado antes, corpo enviado em blocos de 1 MiB."""
        fronteira = '----reconecta' + uuid.uuid4().hex
        pre = b''
        for k, v in (campos or {}).items():
            pre += f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        nome = nome_ascii(os.path.basename(caminho_arquivo))
        # medido 06/10/2026 contra a API real: "application/octet-stream" volta HTTP 400 "File is not supported";
        # com o tipo do arquivo (video/mp4) o upload passa
        tipo_arq = mimetypes.guess_type(caminho_arquivo)[0] or 'application/octet-stream'
        pre += (f'--{fronteira}\r\nContent-Disposition: form-data; name="file"; filename="{nome}"\r\n'
                f'Content-Type: {tipo_arq}\r\n\r\n').encode()
        pos = f'\r\n--{fronteira}--\r\n'.encode()
        url = self._prefixo + '/media'
        for tentativa in range(TENTATIVAS):
            ultima = tentativa == TENTATIVAS - 1
            with open(caminho_arquivo, 'rb') as f:
                tamanho = os.fstat(f.fileno()).st_size
                if tamanho > LIMITE_UPLOAD:
                    raise ErroPubler(f'arquivo com {tamanho / 1e6:.1f} MB passa do limite de 200 MB do upload direto')
                h = self._headers(True)
                h['Content-Type'] = f'multipart/form-data; boundary={fronteira}'
                h['Content-Length'] = str(len(pre) + tamanho + len(pos))
                conn = self._conexao(TIMEOUT_UPLOAD)
                try:
                    status, cab, bruto = self._enviar_em_blocos(conn, url, h, pre, f, tamanho, pos, progresso)
                except (OSError, http.client.HTTPException) as e:
                    # upload que cai não cria post nenhum: dá pra repetir sem risco de duplicar
                    if tentativa < 2:
                        espera = 10.0 * (tentativa + 1)
                        print(f'  upload caiu ({type(e).__name__}); repito em {espera:.0f}s', flush=True)
                        time.sleep(espera)
                        continue
                    raise ErroPubler(f'upload falhou: {type(e).__name__}: {e}') from None
                finally:
                    conn.close()
            if status == 429 and not ultima:
                espera = segundos_de_espera(cab, tentativa)
                print(f'  Publer devolveu 429 (limite) no upload; aguardando {espera:.0f}s e reenvio', flush=True)
                time.sleep(espera)
                continue
            if status in (502, 503, 504) and tentativa < 2:
                print(f'  Publer devolveu {status} no upload; reenvio em 15s', flush=True)
                time.sleep(15)
                continue
            self._respeitar_limite(cab)
            dado = decodificar(bruto)
            if status >= 400:
                raise ErroPubler(f'POST /media -> HTTP {status}: {mensagem_erro(dado, bruto)}', status)
            return dado
        raise ErroPubler('POST /media: tentativas esgotadas')

    @staticmethod
    def _enviar_em_blocos(conn, url, h, pre, f, tamanho, pos, progresso):
        conn.putrequest('POST', url, skip_accept_encoding=True)
        for k, v in h.items():
            conn.putheader(k, v)
        conn.endheaders()
        buf = bytearray(BLOCO)                    # um único buffer de 1 MiB reaproveitado o envio inteiro
        vista = memoryview(buf)
        enviados, marco, t0 = 0, 0.25, time.monotonic()
        try:
            conn.send(pre)
            while True:
                n = f.readinto(buf)
                if not n:
                    break
                conn.send(vista[:n])
                enviados += n
                if progresso and tamanho and enviados / tamanho >= marco:
                    seg = max(time.monotonic() - t0, 1e-6)
                    print(f'    enviado {enviados / tamanho:4.0%} ({enviados / 1e6:.0f}/{tamanho / 1e6:.0f} MB, '
                          f'{enviados / 1e6 / seg:.1f} MB/s)', flush=True)
                    while enviados / tamanho >= marco:
                        marco += 0.25
            if enviados != tamanho:
                raise ErroPubler(f'o arquivo mudou durante o envio ({enviados} de {tamanho} bytes)')
            conn.send(pos)
        except OSError:
            # servidor pode ter respondido e fechado no meio (ex.: 413); tenta ler a resposta antes de desistir
            try:
                resp = conn.getresponse()
                return resp.status, resp.headers, resp.read()
            except Exception:
                pass
            raise
        resp = conn.getresponse()
        return resp.status, resp.headers, resp.read()


# ---------------------------------------------------------------- leitura das respostas do Publer

def lista_de(dado, chave):
    dado = desembrulhar(dado)
    if isinstance(dado, dict):
        dado = dado.get(chave)
    return dado if isinstance(dado, list) else []


def listar_workspaces(cli):
    return lista_de(cli.json('GET', '/workspaces', com_workspace=False), 'workspaces')


def listar_contas(cli):
    return lista_de(cli.json('GET', '/accounts'), 'accounts')


def normalizar(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return ''.join(c for c in s if c.isalnum())


def descrever_conta(c):
    # a doc (schema Account) não tem username/@: o que identifica a conta é o "name" (nome de exibição).
    # "type" está no schema (Instagram = "business"); "status" só aparece no exemplo da quickstart ("active")
    partes = [str(c.get('id')), f"{c.get('provider') or '?':10}", str(c.get('name') or ''),
              f"[tipo: {c.get('type') or '?'}]"]
    if c.get('status') and c.get('status') != 'active':
        partes.append(f"[status: {c.get('status')}]")
    return '  '.join(partes)


def problema_tipo_conta(conta, rede):
    """(bloqueia, mensagem) se o tipo da conta não serve pra rede; None se serve.
    Doc (Accounts > Supported Providers): Instagram na API só tem o tipo "business" (conta profissional), e
    Trial Reel exige conta profissional. Tipo da doc diferente de business bloqueia ANTES de subir vídeo;
    tipo ausente ou fora da lista da doc só avisa (não dá pra afirmar nada)."""
    esperado = REDES[rede].get('tipo_conta')
    if not esperado:
        return None
    tipo = str(conta.get('type') or '').strip().lower()
    # medido 06/10/2026: o GET /accounts devolve "ig_business" pro Instagram profissional (a doc diz "business")
    if tipo == esperado or tipo == f'ig_{esperado}':
        return None
    nome = conta.get('name') or '?'
    if not tipo:
        return False, (f'aviso: o Publer não informou o tipo da conta "{nome}"; Trial Reel exige conta '
                       f'{REDES[rede]["nome"]} profissional ("{esperado}")')
    if tipo in TIPOS_CONTA_DOC:
        return True, (f'a conta "{nome}" ({conta.get("id")}) é do tipo "{tipo}" no Publer; Trial Reel pela API '
                      f'exige conta {REDES[rede]["nome"]} "{esperado}" (profissional). Nada foi enviado.\n'
                      f'  Reconecte no Publer a conta profissional do {REDES[rede]["nome"]} e rode "contas" pra conferir.')
    return False, (f'aviso: tipo de conta "{tipo}" fora da lista da doc do Publer; o esperado pro '
                   f'{REDES[rede]["nome"]} é "{esperado}"')


def eh_da_rede(conta, rede):
    return str(conta.get('provider') or '').lower() == REDES[rede]['provider']


def achar_conta(contas, alvo, rede):
    """Conta da rede cujo nome de exibição bate com o @ da fila (ignora @, espaço, acento e caixa)."""
    nome_rede = REDES[rede]['nome']
    da_rede = [c for c in contas if eh_da_rede(c, rede)]
    a = normalizar(alvo)
    achadas = [c for c in da_rede if normalizar(c.get('name')) == a]
    if len(achadas) == 1:
        return achadas[0]
    lista = '\n'.join('  ' + descrever_conta(c) for c in da_rede) or f'  (nenhuma conta {nome_rede} no workspace)'
    sys.exit(f'{"Nenhuma" if not achadas else str(len(achadas))} conta(s) {nome_rede} têm nome que bate com {alvo}. '
             f'Contas {nome_rede} deste workspace:\n{lista}\n'
             'Passe a certa com --conta <id> --conta-confirmada "<nome exato da conta>".')


def achar_conta_tiktok(contas, alvo):
    return achar_conta(contas, alvo, 'tiktok')


def conferir_conta_explicita(conta, alvo, confirmada, rede):
    """--conta informado à mão: o nome da conta tem que bater com o @ da fila, ou vir confirmado por extenso."""
    nome = str(conta.get('name') or '')
    if normalizar(nome) == normalizar(alvo):
        return
    if confirmada is not None and confirmada.strip() == nome.strip():
        print(f'conta confirmada à mão: "{nome}" (a fila pede {alvo})')
        return
    sys.exit(f'--conta {conta.get("id")} se chama "{nome}" no Publer, e isso não bate com {alvo} (contas.{rede} '
             f'da fila). Nada foi enviado.\nSe essa é mesmo a conta certa, confirme repetindo o nome exato:\n'
             f'  --conta {conta.get("id")} --conta-confirmada "{nome}"')


def resolver_workspace(cli, arg, usar_keychain=True):
    if arg:
        return arg
    if usar_keychain:
        w = config.valor('PUBLER_WORKSPACE_ID') or ler_keychain('workspace-id')
        if w:
            return w
    ws = listar_workspaces(cli)
    if len(ws) == 1 and ws[0].get('id'):
        print(f"workspace: {ws[0].get('name') or '?'} ({ws[0]['id']})")
        return ws[0]['id']
    if not ws:
        sys.exit('A chave não enxerga nenhum workspace no Publer (confira o escopo "workspaces").')
    lista = '\n'.join(f"  {w.get('id')}  {w.get('name')}" for w in ws)
    sys.exit(f'A conta tem {len(ws)} workspaces:\n{lista}\nPasse --workspace <id> ou grave no Keychain:\n'
             '  security add-generic-password -s reconecta-publer -a workspace-id -U -w')


def ler_job(dado):
    """Status, payload, falhas e plano do job nos dois formatos da doc: o da quickstart ({status, payload, plan})
    e o do schema JobStatusResponse ({success, data:{status, result:{status, payload, plan}}}).
    plan.locked = "Whether the workspace is locked" (doc)."""
    d = desembrulhar(dado)
    d = d if isinstance(d, dict) else {}
    res = d.get('result') if isinstance(d.get('result'), dict) else {}
    status = str(res.get('status') or d.get('status') or '').lower()
    payload = d.get('payload') if isinstance(d.get('payload'), dict) else (
        res.get('payload') if isinstance(res.get('payload'), dict) else {})
    plano = res.get('plan') if isinstance(res.get('plan'), dict) else (
        d.get('plan') if isinstance(d.get('plan'), dict) else {})
    return status, payload, payload.get('failures'), plano


def plano_travado(plano):
    return isinstance(plano, dict) and plano.get('locked') is True


def listar_falhas(falhas):
    """A doc mostra failures como objeto ({}) e como lista de {account_id, provider, message}."""
    if not falhas:
        return []
    if isinstance(falhas, dict):
        itens = [v if isinstance(v, dict) else {'message': v} for v in falhas.values()]
    elif isinstance(falhas, list):
        itens = falhas
    else:
        itens = [falhas]
    return [str(f.get('message') or f.get('error') or json.dumps(f, ensure_ascii=False)) if isinstance(f, dict)
            else str(f) for f in itens]


def esperar_job(cli, job_id):
    """Espera o job terminar. Recusa explícita -> PostRecusado. Concluído -> devolve o "plan" do job (o chamador
    confere plan.locked e o estado do post antes de dar o item como agendado)."""
    t0, intervalo = time.monotonic(), ESPERA['job_ini']
    status = ''
    while True:
        status, payload, falhas, plano = ler_job(cli.json('GET', f'/job_status/{urllib.parse.quote(job_id)}'))
        erros = listar_falhas(falhas)
        if status in FIM_JOB + ('failed',):
            if status == 'failed' or erros:
                raise PostRecusado('o Publer recusou o post: ' +
                                   ('; '.join(erros) or json.dumps(payload, ensure_ascii=False)[:300]))
            return plano
        if time.monotonic() - t0 > ESPERA['job_total']:
            raise ErroPubler(f'o job {job_id} não terminou em {ESPERA["job_total"] / 60:.0f} min '
                             f'(último status: {status or "?"})')
        time.sleep(intervalo)
        intervalo = min(intervalo * 1.5, ESPERA['job_max'])


def validade_da_rede(enviado, rede):
    """validity.<rede> devolvido pelo upload (None se o Publer não mandou)."""
    v = enviado.get('validity') if isinstance(enviado, dict) else None
    return v.get(rede) if isinstance(v, dict) else None


def checar_midia_enviada(enviado, rede, duracao=None):
    if not isinstance(enviado, dict) or not enviado.get('id'):
        raise ErroPubler(f'o upload não devolveu id de mídia: {str(enviado)[:300]}')
    tipo = enviado.get('type')
    if tipo and tipo != 'video':
        raise ErroPubler(f'o Publer classificou o arquivo como "{tipo}", não como vídeo')
    t = validade_da_rede(enviado, rede)
    if rede == 'tiktok':
        if t is False or (isinstance(t, dict) and t.get('video') is False):
            raise ErroPubler(f'o Publer diz que este vídeo não serve pro TikTok (validity.tiktok = {t})')
    elif t is False or (isinstance(t, dict) and t.get('reel') is False):
        # doc: "if validity.instagram.reel is false, the uploaded media cannot be used for Instagram Reels"
        dica = ''
        if duracao and duracao > REDES['instagram']['dur_aviso']:
            dica = (f'; o vídeo tem {duracao:.0f} s e as páginas de Reels do Publer falam em 3–90 s: é o Publer '
                    'barrando Reel acima de 90 s (liberar com o suporte ou cortar versões de até 90 s)')
        raise ErroPubler(f'o Publer diz que este vídeo não serve pra Reel do Instagram '
                         f'(validity.instagram = {json.dumps(t, ensure_ascii=False)}){dica}')


def preparar_midia(cli, enviado, rede, duracao=None):
    """Monta o media[] do post. A doc pede thumbnails[] (vem de GET /media/{id}, depois do processamento).
    O GET /media/{id} também traz o `validity` calculado com o vídeo já processado ("derived from size,
    dimensions, format and duration"); a checagem da rede roda de novo com ele, porque o validity do upload sai
    antes do processamento. Recusa aqui = erro na etapa "midia": nada criado, dá pra repetir."""
    mid = enviado['id']
    item, avisou = None, False
    t0, intervalo = time.monotonic(), ESPERA['midia_ini']
    while True:
        try:
            item = desembrulhar(cli.json('GET', f'/media/{urllib.parse.quote(mid)}'))
        except ErroPubler as e:
            if e.status in (403, 404):
                print(f'  aviso: GET /media/{mid} devolveu {e.status}; uso a miniatura do upload')
                item = None
                break
            raise
        if isinstance(item, dict) and item.get('thumbnails'):
            break
        if time.monotonic() - t0 > ESPERA['midia_total']:
            break
        if not avisou:
            print('  Publer ainda processando o vídeo (sem miniaturas); aguardando...', flush=True)
            avisou = True
        time.sleep(intervalo)
        intervalo = min(intervalo * 1.5, ESPERA['midia_max'])
    item = item if isinstance(item, dict) else {}
    if isinstance(item.get('validity'), dict):
        processada = item['validity'].get(rede)
        if processada is not None:
            print(f'  vídeo processado: validity.{rede} = {json.dumps(processada, ensure_ascii=False)}', flush=True)
        checar_midia_enviada({**enviado, 'validity': item['validity']}, rede, duracao)
    thumbs = item.get('thumbnails') or []
    if not thumbs and enviado.get('thumbnail'):
        thumbs = [{'real': enviado['thumbnail'], 'small': enviado['thumbnail']}]
    if not thumbs:
        raise ErroPubler('o Publer não devolveu miniaturas do vídeo (a doc exige media[].thumbnails em vídeo)')
    # sem "path": é opcional na doc e, enquanto o vídeo processa, é um endereço provisório
    # (GET /media/{id}); o upload sem direct_upload também não devolve a URL final. O id basta.
    return {'id': mid, 'type': 'video', 'thumbnails': thumbs}


def contar_hashtags(texto):
    return len(re.findall(r'#\w+', texto or ''))


def corpo_post(rede, conta_id, midia, texto, quando, args):
    if rede == 'tiktok':
        rede_corpo = {
            'type': 'video',
            'text': texto,
            'media': [midia],
            'details': {'privacy': args.privacidade, 'comment': not args.sem_comentarios,
                        'duet': not args.sem_duet, 'stitch': not args.sem_stitch,
                        'promotional': False, 'paid': False, 'reminder': False},
        }
    else:
        # Trial Reel: sem "feed" (trial não vai pro feed); a 1ª miniatura (índice 0) é a capa
        rede_corpo = {
            'type': 'video',
            'text': texto,
            'media': [{**midia, 'default_thumbnail': 0}],
            'details': {'type': 'reel', 'trial_reel': args.trial},
        }
    return {'bulk': {'state': 'scheduled', 'posts': [{
        'networks': {rede: rede_corpo},
        'accounts': [{'id': conta_id, 'scheduled_at': quando.isoformat(timespec='seconds')}],
    }]}}


def exigir(cond, msg):
    if not cond:
        raise ErroPubler(f'payload do post malformado (NÃO enviado): {msg}')


def validar_corpo(c, rede):
    """Confere a estrutura antes de mandar pra API (regra da casa: validar payload antes de enviar)."""
    b = c.get('bulk') if isinstance(c, dict) else None
    exigir(isinstance(b, dict) and b.get('state') == 'scheduled', 'bulk.state != scheduled')
    exigir(isinstance(b.get('posts'), list) and len(b['posts']) == 1, 'bulk.posts precisa ter 1 post')
    p = b['posts'][0]
    redes = p.get('networks') or {}
    exigir(isinstance(redes, dict) and list(redes) == [rede], f'networks precisa ter só "{rede}" ({list(redes)})')
    t = redes.get(rede)
    exigir(isinstance(t, dict) and t.get('type') == 'video', f'networks.{rede}.type != video')
    exigir(isinstance(t.get('text'), str) and 0 < len(t['text']) <= LIMITE_TEXTO, 'text vazio ou > 2200')
    m = t.get('media')
    exigir(isinstance(m, list) and len(m) == 1 and m[0].get('id'), 'media precisa de 1 vídeo com id')
    exigir(m[0].get('type') == 'video', 'media[0].type != video')
    exigir(isinstance(m[0].get('thumbnails'), list) and m[0]['thumbnails'], 'media[0].thumbnails vazio')
    d = t.get('details') or {}
    if rede == 'tiktok':
        exigir(d.get('privacy') in PRIVACIDADES, f'privacy inválida: {d.get("privacy")}')
        exigir(all(isinstance(d.get(k), bool) for k in ('comment', 'duet', 'stitch')),
               'comment/duet/stitch não booleanos')
    else:
        exigir(d.get('type') == 'reel', f'details.type precisa ser "reel" ({d.get("type")})')
        exigir(d.get('trial_reel') in TRIAL_MODOS, f'details.trial_reel inválido: {d.get("trial_reel")}')
        exigir('feed' not in d, 'details.feed não vai em Trial Reel (trial não aparece no feed)')
        dt_idx = m[0].get('default_thumbnail')
        exigir(isinstance(dt_idx, int) and 0 <= dt_idx < len(m[0]['thumbnails']),
               f'media[0].default_thumbnail fora das miniaturas ({dt_idx})')
        n = contar_hashtags(t['text'])
        exigir(n <= REDES['instagram']['max_hashtags'], f'{n} hashtags (o Instagram aceita no máx. 30)')
    a = p.get('accounts')
    exigir(isinstance(a, list) and len(a) == 1 and a[0].get('id'), 'accounts precisa de 1 conta com id')
    try:
        q = dt.datetime.fromisoformat(a[0].get('scheduled_at') or '')
    except ValueError:
        q = None
    exigir(q is not None and q.tzinfo is not None, 'scheduled_at sem data ISO 8601 com fuso')


def paginas_posts(cli, consulta, max_paginas=50):
    """Percorre GET /posts página a página (doc: page começa em 0). Para no total_pages quando ele vem; sem ele,
    para na página vazia ou na que não traz post novo (servidor que ignora "page" não vira laço)."""
    vistos = set()
    for pagina in range(max_paginas):
        dado = cli.json('GET', '/posts', consulta={**consulta, 'page': pagina})
        posts = [p for p in lista_de(dado, 'posts') if isinstance(p, dict)]
        novos = [p for p in posts if (p.get('id'), p.get('scheduled_at')) not in vistos]
        vistos.update((p.get('id'), p.get('scheduled_at')) for p in novos)
        if novos:
            yield novos
        d = desembrulhar(dado)
        paginas = d.get('total_pages') if isinstance(d, dict) else None
        if not novos or (isinstance(paginas, int) and pagina + 1 >= paginas):
            break


def buscar_post(cli, conta_id, quando, legenda=None, estado='all'):
    """Procura na conta um post marcado pra `quando` (±1 min) via GET /posts.

    from/to vão como DATA (a doc aceita data; datetime aparece só na tabela) com 1 dia de folga, e o horário
    é conferido aqui. Com legenda, o começo do texto também precisa bater, pra não confundir com outro post
    no mesmo horário. Devolve (post, outro): `outro` = existe post nesse horário, mas com outro texto."""
    um = dt.timedelta(minutes=1)
    alvo = normalizar(legenda)[:40] if legenda else ''
    outro = None
    for posts in paginas_posts(cli, {
            'state': estado, 'account_ids[]': [conta_id],
            'from': (quando - dt.timedelta(days=1)).date().isoformat(),
            'to': (quando + dt.timedelta(days=1)).date().isoformat()}):
        for p in posts:
            if p.get('account_id') not in (None, conta_id) or not p.get('scheduled_at'):
                continue
            try:
                q = dt.datetime.fromisoformat(str(p['scheduled_at']).replace('Z', '+00:00'))
            except ValueError:
                continue
            if q.tzinfo is None or abs(q - quando) >= um:
                continue
            texto = normalizar(p.get('text'))
            n = min(len(alvo), len(texto))
            if n and texto[:n] != alvo[:n]:
                outro = p
                continue
            return p, None
    return None, outro


def problema_do_post(estado):
    """Estado de post (PostSummary.state) que não vai sair como está; None se está ok ou não dá pra saber.
    Doc (GET /posts, State Values): scheduled_locked, scheduled_reauth, scheduled_pending, scheduled_declined,
    failed; rascunho (draft*) também não sai."""
    s = str(estado or '').strip().lower()
    if not s:
        return None
    if s in FILTROS_TRAVA or s == 'failed' or s.startswith('draft'):
        return s
    return None


def verificar_post(cli, conta_id, quando, legenda, plano=None, post=None):
    """Depois do job concluído sem falhas: o post existe e vai mesmo sair? Devolve (post_id, motivo), com
    motivo = None se está tudo certo, ou o porquê de o post estar travado no Publer.

    1) plan.locked do job_status ("Whether the workspace is locked");
    2) o estado do post achado em GET /posts?state=all (conta + horário + começo da legenda);
    3) GET /posts com cada filtro de trava da doc (scheduled_locked/reauth/pending/declined), caso o estado
       resumido do post venha só "scheduled". Controle: se o post aparece nos QUATRO filtros ao mesmo tempo, o
       filtro foi ignorado pelo servidor (um post não está travado, pendente, recusado e sem autorização juntos)
       e o resultado não vale.
    Falha de consulta vira aviso: o job já disse que o post foi criado."""
    motivo = 'o workspace está travado no Publer (job_status: plan.locked = true)' if plano_travado(plano) else None
    post_id = post.get('id') if isinstance(post, dict) else None
    try:
        if post is None:
            post, _ = buscar_post(cli, conta_id, quando, legenda, 'all')
            post_id = post.get('id') if post else None
        if post and not motivo:
            p = problema_do_post(post.get('state'))
            if p:
                motivo = f'o post está "{p}" no Publer'
        if not motivo:
            achados = []
            for filtro in FILTROS_TRAVA:
                trav, _ = buscar_post(cli, conta_id, quando, legenda, filtro)
                if trav:
                    achados.append(filtro)
                    post_id = post_id or trav.get('id')
            if achados and len(achados) < len(FILTROS_TRAVA):
                motivo = f'o post aparece no filtro "{achados[0]}" do Publer'
            elif achados:
                print('  aviso: o Publer devolveu o post em todos os filtros de trava (filtro ignorado); '
                      'fico com o estado do post e o plan do job')
    except ErroPubler as e:
        print(f'  aviso: não consegui conferir o estado do post no Publer ({e})')
    return post_id, motivo


def conciliar(cli, est, legenda):
    """Descobre no Publer se o post de um item "agendando" (ou com erro depois do POST, ou agendado_travado)
    foi criado e se vai sair.

    Devolve (resultado, post_id, explicação), com resultado:
      'existe'       -> o post está no Publer: marcar agendado_publer, NUNCA postar de novo;
      'travado'      -> o post está no Publer, mas travado (workspace, reautorização, aprovação): agendado_travado;
      'nao_existe'   -> o job terminou com recusa explícita: dá pra repetir;
      'em_andamento' -> o job ainda está rodando e o post ainda não aparece: esperar (nem --forcar);
      'incerto'      -> não deu pra provar nada: fica de fora até alguém conferir (--forcar <id>)."""
    conta = (est or {}).get('conta_publer')
    try:
        quando = dt.datetime.fromisoformat((est or {}).get('scheduled_at') or '')
    except ValueError:
        quando = None
    if not conta or quando is None or quando.tzinfo is None:
        return 'incerto', None, 'o registro na fila não tem conta/horário pra conferir'
    nota, job_rodando = '', None
    try:
        job_id = est.get('job_id')
        if job_id:
            try:
                status, payload, falhas, plano = ler_job(cli.json('GET', f'/job_status/{urllib.parse.quote(job_id)}'))
            except ErroPubler as e:
                status, nota = '', f'; o job {job_id} não pôde ser consultado ({e})'
            else:
                erros = listar_falhas(falhas)
                if status == 'failed' or (status in FIM_JOB and erros):
                    return 'nao_existe', None, ('o job terminou com recusa do Publer: ' +
                                                ('; '.join(erros) or status))
                if status in FIM_JOB:
                    post_id, motivo = verificar_post(cli, conta, quando, legenda, plano)
                    if motivo:
                        return 'travado', post_id, motivo
                    return 'existe', post_id, f'job {job_id} concluído sem falhas'
                if status in JOB_RODANDO:              # status desconhecido/vazio não prova nada: fica "incerto"
                    job_rodando = job_id
                nota = f'; o job {job_id} ainda está "{status or "?"}"'
        post, outro = buscar_post(cli, conta, quando, legenda, 'all')
    except ErroPubler as e:
        return 'incerto', None, f'a consulta ao Publer falhou ({e})'
    if post:
        post_id, motivo = verificar_post(cli, conta, quando, legenda, None, post)
        if motivo:
            return 'travado', post_id, motivo
        return 'existe', post.get('id'), f'achei o post no Publer (estado "{post.get("state") or "?"}")'
    if job_rodando:
        return 'em_andamento', None, (f'o job {job_rodando} ainda está rodando no Publer e o post ainda não aparece '
                                      f'em {fmt_quando(quando.astimezone(FUSO))}')
    if outro:
        nota += f'; há outro post nesse horário (id {outro.get("id")}) com texto diferente'
    return 'incerto', None, f'não achei o post em {fmt_quando(quando.astimezone(FUSO))} na conta {conta}{nota}'


def agenda_no_publer(cli, conta_id, de, ate):
    """Horários de TUDO que está agendado no Publer pra esta conta entre `de` e `ate` (GET /posts?state=scheduled,
    filtrado por conta), inclusive posts criados fora das filas (app do Publer, outra pessoa, outra ferramenta).
    A doc exige 1 min entre posts da mesma conta ("A one minute gap is required between posts") e o teto diário
    do Publer é por conta: esses horários entram na grade e no teto de 24 h."""
    saida = []
    for posts in paginas_posts(cli, {
            'state': 'scheduled', 'account_ids[]': [conta_id],
            'from': de.astimezone(FUSO).date().isoformat(), 'to': ate.astimezone(FUSO).date().isoformat()}):
        for p in posts:
            if p.get('account_id') not in (None, conta_id) or not p.get('scheduled_at'):
                continue
            try:
                q = dt.datetime.fromisoformat(str(p['scheduled_at']).replace('Z', '+00:00'))
            except ValueError:
                continue
            if q.tzinfo is not None:
                saida.append(q)
    return saida


# ---------------------------------------------------------------- plano (seleção + horários)

def parse_horarios(texto):
    hs = []
    for parte in texto.split(','):
        parte = parte.strip()
        if parte:
            try:
                hs.append(dt.datetime.strptime(parte, '%H:%M').time())
            except ValueError:
                sys.exit(f'--horarios: "{parte}" não está no formato HH:MM')
    if not hs or len(set(hs)) != len(hs):
        sys.exit('--horarios: informe horários distintos, ex.: "09:00,13:00,19:00"')
    return sorted(hs)


def parse_inicio(texto):
    try:
        return dt.datetime.strptime(texto.strip(), '%Y-%m-%d %H:%M').replace(tzinfo=FUSO)
    except ValueError:
        sys.exit(f'--inicio: "{texto}" não está no formato "AAAA-MM-DD HH:MM" (horário de Brasília)')


def horarios_por_intervalo(inicio, minutos, por_dia):
    """--intervalo: `por_dia` horários a partir da hora do --inicio, de `minutos` em `minutos`, no mesmo dia.
    Ex.: 08:00, 20 min, 21 por dia -> 08:00, 08:20, ..., 14:40."""
    if minutos < 1:
        sys.exit('--intervalo: informe minutos >= 1')
    base = dt.datetime.combine(dt.date(2000, 1, 1), inicio.time())
    hs = [base + dt.timedelta(minutes=minutos * k) for k in range(por_dia)]
    if hs[-1].date() != base.date():
        sys.exit(f'--intervalo {minutos} com --por-dia {por_dia} a partir das {inicio:%H:%M} passa da meia-noite '
                 f'(o último cairia {hs[-1]:%H:%M} do dia seguinte); diminua o intervalo, o --por-dia ou adiante o início')
    return [h.time() for h in hs]


UM_MINUTO = dt.timedelta(minutes=1)


def colide(q, ocupados):
    """O Publer exige 1 min entre posts da mesma conta: horário a menos de 1 min de um ocupado está tomado."""
    return any(abs(q - o) < UM_MINUTO for o in ocupados)


def juntar_ocupados(*listas):
    """Junta horários ocupados de várias fontes (filas + Publer) sem contar duas vezes o mesmo post
    (o mesmo post aparece na fila e no Publer; dois posts da conta nunca ficam a menos de 1 min)."""
    saida = []
    for q in sorted(q for lista in listas for q in lista):
        if not colide(q, saida):
            saida.append(q)
    return saida


def gerar_horarios(inicio, horarios, n, piso, ocupados=()):
    """N horários a partir do --inicio, nos horários do dia (já cortados pelo --por-dia), nunca antes do piso.
    Horário a menos de 1 min de um post já agendado na mesma conta/rede (`ocupados`) é pulado."""
    ocupados = list(ocupados)
    saida, dia = [], inicio.date()
    for _ in range(3660):
        if len(saida) >= n:
            break
        for h in horarios:
            q = dt.datetime.combine(dia, h, tzinfo=FUSO)
            if q >= inicio and q >= piso and not colide(q, ocupados) and len(saida) < n:
                saida.append(q)
        dia += dt.timedelta(days=1)
    return saida


def estado_bruto(item, rede):
    """estado.<rede> exatamente como está na fila (base do compare-and-swap)."""
    return (item.get('estado') or {}).get(rede)


def status_rede(item, rede):
    """Status da rede; objeto sem "status" (só acontece em item que não passou pelo fila.carregar) é
    "malformado", que nunca sai (o fila.carregar já barra a fila inteira nesse caso)."""
    est = estado_bruto(item, rede)
    if est is None:
        return 'pendente'
    return est.get('status') if isinstance(est, dict) and est.get('status') else 'malformado'


def precisa_conciliar(item, rede):
    """"agendando", ou erro depois do POST de criação: o post PODE existir no Publer."""
    est = estado_bruto(item, rede) or {}
    st = status_rede(item, rede)
    return st == 'agendando' or (st == 'erro' and est.get('etapa') not in ETAPAS_REPETIVEIS)


def aceito(item, args):
    """Este item pode ser subido e agendado nesta rodada?"""
    st = status_rede(item, args.rede)
    if st == 'pendente':
        return True
    if item['id'] in args.forcar:                       # a pessoa conferiu o Publer e mandou repostar
        return st in ('agendando', 'erro', TRAVADO)
    return st == 'erro' and args.repetir_erros and not precisa_conciliar(item, args.rede)


def filas_reais():
    """Nomes das filas de verdade em filas/ (o JSON diz "semana" igual ao nome do arquivo; backups ficam de fora)."""
    nomes = []
    try:
        arquivos = sorted(os.listdir(filamod.FILAS))
    except OSError:
        return nomes
    for arq in arquivos:
        if not arq.endswith('.json'):
            continue
        nome = arq[:-5]
        try:
            with open(os.path.join(filamod.FILAS, arq), encoding='utf-8') as fh:
                if json.load(fh).get('semana') == nome:
                    nomes.append(nome)
        except (OSError, ValueError, AttributeError):
            print(f'aviso: não consegui ler filas/{arq}; ela fica fora da conta de horários ocupados')
    return nomes


def agenda_da_rede(rede, ignorar=()):
    """Horários (datetime) de tudo que já está, ou pode estar, agendado no Publer nesta rede, em todas as filas.
    `ignorar` = {(fila, id)} que não contam: o item que vai sair de novo com --forcar (a pessoa conferiu que o
    post antigo NÃO existe) não ocupa o horário antigo nem conta duas vezes no teto de 24 h."""
    saida = []
    for nome in filas_reais():
        for it in filamod.carregar(nome)['itens']:
            if (nome, it['id']) in ignorar:
                continue
            est = estado_bruto(it, rede) or {}
            if est.get('status') in OCUPADOS or precisa_conciliar(it, rede):
                try:
                    q = dt.datetime.fromisoformat(est.get('scheduled_at') or '')
                except ValueError:
                    continue
                if q.tzinfo is not None:
                    saida.append(q)
    return saida


def estouro_24h(rede, slots, ocupados):
    """Pior janela de 24 h corridas (o Publer conta em rolling 24 h) que contém algum horário do plano.
    Devolve (quantidade, início da janela) se passar do limite diário da rede; senão None."""
    limite = REDES[rede]['limite_dia']
    dia = dt.timedelta(hours=24)
    if not slots:
        return None
    ini, fim = min(slots) - dia, max(slots) + dia
    todos = sorted(list(slots) + [x for x in ocupados if ini < x < fim])
    pior = None
    for s in slots:
        # janelas (t-24h, t] que terminam em cada evento entre s e s+24h e portanto contêm s
        for t in todos:
            if s <= t < s + dia:
                n = sum(1 for x in todos if t - dia < x <= t)
                if n > limite and (pior is None or n > pior[0]):
                    pior = (n, t - dia)
    return pior


_DURACOES = {}


def _caixas_mp4(f, ini, fim):
    """Percorre as caixas (boxes) do MP4 entre ini e fim lendo só os cabeçalhos."""
    pos = ini
    while pos + 8 <= fim:
        f.seek(pos)
        cab = f.read(8)
        if len(cab) < 8:
            return
        tam, tipo = struct.unpack('>I4s', cab)
        cab_tam = 8
        if tam == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return
            tam, cab_tam = struct.unpack('>Q', ext)[0], 16
        elif tam == 0:
            tam = fim - pos
        if tam < cab_tam:
            return
        yield tipo, pos + cab_tam, min(pos + tam, fim)
        pos += tam


def duracao_video(caminho):
    """Duração em segundos lida da caixa moov/mvhd do MP4 (só cabeçalhos; o vídeo não é lido inteiro nem alterado).
    None se não der pra ler."""
    if caminho in _DURACOES:
        return _DURACOES[caminho]
    dur = None
    try:
        with open(caminho, 'rb') as f:
            tamanho = os.fstat(f.fileno()).st_size
            for tipo, ini, fim in _caixas_mp4(f, 0, tamanho):
                if tipo != b'moov':
                    continue
                for t2, i2, _ in _caixas_mp4(f, ini, fim):
                    if t2 != b'mvhd':
                        continue
                    f.seek(i2)
                    versao = f.read(4)[0]
                    if versao == 1:
                        f.seek(16, os.SEEK_CUR)
                        escala, bruto = struct.unpack('>IQ', f.read(12))
                    else:
                        f.seek(8, os.SEEK_CUR)
                        escala, bruto = struct.unpack('>II', f.read(8))
                    dur = bruto / escala if escala and bruto else None
                    break
                break
    except (OSError, struct.error, IndexError):
        dur = None
    _DURACOES[caminho] = dur
    return dur


def recorte(itens, args):
    ids = [i['id'] for i in itens]
    ini, fim = 0, len(itens)
    if args.de:
        if args.de not in ids:
            sys.exit(f'--de {args.de}: esse id não está na fila')
        ini = ids.index(args.de)
    if args.ate:
        if args.ate not in ids:
            sys.exit(f'--ate {args.ate}: esse id não está na fila')
        fim = ids.index(args.ate) + 1
    if fim <= ini:
        sys.exit('--ate vem antes do --de na ordem da fila')
    return itens[ini:fim]


def ler_forcar(valores):
    return {x.strip() for v in (valores or []) for x in str(v).split(',') if x.strip()}


def validar_forcar(itens, args):
    no_recorte = {i['id'] for i in recorte(itens, args)}
    por_id = {i['id']: i for i in itens}
    for rid in sorted(args.forcar):
        if rid not in por_id:
            sys.exit(f'--forcar {rid}: esse id não está na fila')
        if rid not in no_recorte:
            sys.exit(f'--forcar {rid}: esse id está fora do recorte --de/--ate desta rodada')
        st = status_rede(por_id[rid], args.rede)
        if st not in ('agendando', 'erro', 'pendente', TRAVADO):
            sys.exit(f'--forcar {rid}: o item está "{st}" em {args.rede}; --forcar só vale pra item em "agendando", '
                     f'"erro" ou "{TRAVADO}" (este último só depois de apagar o post travado no Publer)')


def selecionar(itens, args):
    sel, pulados, a_conferir = [], {}, []
    for it in recorte(itens, args):
        if it.get('fora_do_plano'):                 # saiu do plano (fila.py montar): não sai em rede nenhuma
            pulados['fora_do_plano'] = pulados.get('fora_do_plano', 0) + 1
            continue
        if aceito(it, args):
            sel.append(it)
            continue
        if precisa_conciliar(it, args.rede):
            a_conferir.append(it)
            chave = PULADO_CONFERIR
        else:
            chave = status_rede(it, args.rede)
        pulados[chave] = pulados.get(chave, 0) + 1
    if args.max is not None:
        sel = sel[:max(args.max, 0)]
    return sel, pulados, a_conferir


def problemas_do_item(item, rede):
    """O que impede o item de sair (bloqueia a rodada inteira antes de qualquer envio)."""
    p = []
    cfg = REDES[rede]
    video = item.get('video') or ''
    if not os.path.isfile(video):
        p.append('vídeo não encontrado (o disco está montado?)')
    elif os.path.getsize(video) > LIMITE_UPLOAD:
        p.append(f'vídeo com {os.path.getsize(video) / 1e6:.1f} MB passa de 200 MB')
    else:
        dur = duracao_video(video)
        if dur is not None and cfg['dur_min'] is not None and dur < cfg['dur_min']:
            p.append(f'vídeo com {dur:.1f} s; o {cfg["nome"]} pede no mínimo {cfg["dur_min"]} s')
        if dur is not None and cfg['dur_max'] is not None and dur > cfg['dur_max']:
            p.append(f'vídeo com {dur / 60:.1f} min; o {cfg["nome"]} aceita até {cfg["dur_max"] // 60} min')
    leg = (item.get('legenda') or '').strip()
    if not leg:
        p.append('legenda vazia')
    elif len(leg) > LIMITE_TEXTO:
        p.append(f'legenda com {len(leg)} caracteres (máx. {LIMITE_TEXTO})')
    if cfg['max_hashtags'] is not None and contar_hashtags(leg) > cfg['max_hashtags']:
        p.append(f'legenda com {contar_hashtags(leg)} hashtags (o {cfg["nome"]} aceita no máx. {cfg["max_hashtags"]})')
    return p


def videos_longos(plano, rede):
    """Itens acima da duração que a doc do Publer cita pra Reel (90 s): só aviso, não bloqueia."""
    lim = REDES[rede]['dur_aviso']
    if lim is None:
        return []
    saida = []
    for it, _ in plano:
        dur = duracao_video(it.get('video') or '') if os.path.isfile(it.get('video') or '') else None
        if dur is not None and dur > lim:
            saida.append((it['id'], dur))
    return saida


def imprimir_aviso_duracao(plano, rede):
    longos = videos_longos(plano, rede)
    if not longos:
        return
    durs = [d for _, d in longos]
    print(f'\naviso (não bloqueia): {len(longos)} de {len(plano)} vídeos passam de {REDES[rede]["dur_aviso"]} s '
          f'(de {min(durs):.0f} a {max(durs):.0f} s). As páginas de Reels e de redes do Publer citam Reel de '
          f'3–90 s; a página de vídeo do Publer e a Meta aceitam até 15 min.\n'
          '  O teste real dirá: se o Publer barrar, o upload volta com validity.instagram.reel false e o item para na\n'
          '  etapa "midia" sem criar post (dá pra repetir); se passar, o job conclui normalmente.')


def fmt_quando(q):
    return f'{DIAS[q.weekday()]} {q:%d/%m %H:%M}'


def fmt_duracao(item):
    video = item.get('video') or ''
    dur = duracao_video(video) if os.path.isfile(video) else None
    return f'{dur:5.0f}s' if dur is not None else '    ?'


def imprimir_tabela(plano, rede):
    print(f'{"id":9} {"arquivo":30} {"MB":>6} {"dur.":>6}  {"horário (Brasília)":18}  legenda')
    forcados = False
    for item, quando in plano:
        video = item.get('video') or ''
        tam = os.path.getsize(video) if os.path.isfile(video) else item.get('bytes') or 0
        arq = os.path.basename(video)
        arq = arq if len(arq) <= 30 else arq[:29] + '…'
        leg = ' '.join((item.get('legenda') or '').split())
        leg = leg if len(leg) <= 48 else leg[:47] + '…'
        rid = item['id']
        if status_rede(item, rede) != 'pendente' and (precisa_conciliar(item, rede)
                                                       or status_rede(item, rede) == TRAVADO):
            rid, forcados = rid + '*', True
        print(f'{rid:9} {arq:30} {tam / 1e6:6.1f} {fmt_duracao(item):>6}  {fmt_quando(quando):18}  {leg}')
    if forcados:
        print('* forçado com --forcar: o post anterior PODE existir no Publer (a rodada real confere antes)')


def imprimir_a_conferir(a_conferir, rede):
    if not a_conferir:
        return
    print(f'\nFORA DESTA RODADA ({PULADO_CONFERIR}): o post pode já existir no Publer.')
    for it in a_conferir:
        est = estado_bruto(it, rede) or {}
        try:
            q = fmt_quando(dt.datetime.fromisoformat(est.get('scheduled_at') or '').astimezone(FUSO))
        except (ValueError, TypeError):
            q = '?'
        print(f'  {it["id"]:9} {est.get("status")}' + (f' na etapa "{est["etapa"]}"' if est.get('etapa') else '') +
              f'; horário pedido {q}; conta {est.get("conta_publer") or "?"}' +
              (f'; job {est["job_id"]}' if est.get('job_id') else ''))
    print('  A rodada real confere no Publer antes de tudo e marca agendado_publer o que achar. O que não der pra\n'
          '  confirmar continua de fora: olhe os agendados no Publer e, se o post NÃO estiver lá, use --forcar <id>.')


# ---------------------------------------------------------------- estado na fila

def agora_iso():
    return dt.datetime.now(FUSO).isoformat(timespec='seconds')


def salvar_fila(fila):
    """Gravação atômica com .part de nome ÚNICO no mesmo diretório (duas gravações nunca dividem o mesmo .part)."""
    p = filamod.caminho_fila(fila['semana'])
    pasta = os.path.dirname(p)
    os.makedirs(pasta, exist_ok=True)
    try:
        modo = os.stat(p).st_mode & 0o777
    except OSError:
        modo = 0o644
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(p) + '.', suffix='.part', dir=pasta)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(fila, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, modo)               # mkstemp cria 0600; mantém a permissão da fila
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def item_da_fila(semana, rid):
    return next((it for it in filamod.carregar(semana)['itens'] if it['id'] == rid), None)


def gravar_estado(semana, rid, estado, esperado, rede):
    """Compare-and-swap: relê a fila e só grava se o estado.<rede> em disco ainda for o `esperado`.
    Se alguém mexeu no item no meio-tempo (ex.: marcou postado_manual), levanta ConflitoFila e não grava."""
    f = filamod.carregar(semana)
    for it in f['itens']:
        if it['id'] == rid:
            atual = estado_bruto(it, rede)
            if atual != esperado:
                raise ConflitoFila(f'{rid} mudou na fila durante a rodada (agora está '
                                   f'{json.dumps(atual, ensure_ascii=False)[:200]})')
            it.setdefault('estado', {})[rede] = estado
            break
    else:
        raise ConflitoFila(f'{rid} sumiu da fila {semana}')
    salvar_fila(f)


def travar_fila(semana, rede='?'):
    """Uma execução por fila, de qualquer rede: trava exclusiva em filas/<fila>.lock enquanto a rodada durar (o
    sistema solta sozinho se o processo morrer). TikTok e Instagram da mesma fila rodam um depois do outro: as
    duas gravariam o mesmo arquivo. O fila.py (montar/intercalar) pega a mesma trava. Devolve o descritor;
    fechar o descritor solta a trava."""
    try:
        return filamod.travar(semana, rede)
    except filamod.TravaOcupada as e:
        sys.exit(f'Já tem outra execução publicando a fila {semana}' + (f' ({e.dono})' if e.dono else '') +
                 f'.\nEspere ela terminar (ou feche-a) antes de rodar de novo. Trava: {e.caminho}')


def travar_rede(rede, semana):
    """Uma rodada por rede, de qualquer fila (trava em filas/.rede-<rede>.lock): duas rodadas do Instagram em dois
    Terminais (ex.: SEM41-terca e SEM41-quarta) planejariam com a mesma foto do disco e marcariam os mesmos
    horários, passando do teto de 24 h."""
    try:
        return filamod.travar(f'.rede-{rede}', f'{rede}, fila {semana}')
    except filamod.TravaOcupada as e:
        sys.exit(f'Já tem uma rodada do {REDES[rede]["nome"]} publicando' + (f' ({e.dono})' if e.dono else '') +
                 '.\nUma rodada por rede de cada vez (as duas marcariam os mesmos horários). Espere ela terminar. '
                 f'Trava: {e.caminho}')


def anotar_diario(semana, registro):
    """Diário só de acréscimo de todo POST de criação (filas/<fila>.posts.log, uma linha JSON por evento): se a
    fila for sobrescrita no meio da rodada, o rastro do post continua aqui."""
    try:
        caminho = os.path.join(filamod.FILAS, f'{semana}.posts.log')
        with open(caminho, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'em': agora_iso(), **registro}, ensure_ascii=False) + '\n')
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as e:
        print(f'  aviso: não consegui escrever no diário de posts ({e})')


def reparar_registro(semana, rid, rede, registro):
    """Depois do POST, a gravação falhou porque o item mudou na fila. Se ele voltou pra "pendente" (alguém gravou
    por cima uma cópia velha da fila), o post criado ficaria sem rastro e sairia de novo na próxima rodada: grava
    o registro do POST por cima. Outro status (ex.: postado_manual marcado à mão) é decisão de gente: fica."""
    try:
        item = item_da_fila(semana, rid)
        if item is None or status_rede(item, rede) != 'pendente':
            return False
        gravar_estado(semana, rid, registro, estado_bruto(item, rede), rede)
        return True
    except (ConflitoFila, OSError, ValueError):
        return False


def conciliar_pendencias(cli, semana, args):
    """Antes de postar: confere no Publer os itens do recorte que podem já ter post criado ("agendando", erro
    depois do POST, agendado_travado) e grava o que descobrir. Tira do --forcar quem não pode sair de novo (job
    ainda rodando, post travado ainda no Publer). Devolve {'incertos': [ids], 'travados': [(id, motivo)]}."""
    alvo = [it for it in recorte(filamod.carregar(semana)['itens'], args)
            if precisa_conciliar(it, args.rede) or status_rede(it, args.rede) == TRAVADO]
    saida = {'incertos': [], 'travados': []}
    if not alvo:
        return saida
    print(f'\nconferindo no Publer {len(alvo)} item(ns) que podem já ter post criado:')
    for it in alvo:
        rid, est = it['id'], estado_bruto(it, args.rede)
        res, post_id, expl = conciliar(cli, est, it.get('legenda'))
        forcado = rid in args.forcar
        if res == 'existe':
            novo = {k: v for k, v in est.items() if k not in ('mensagem', 'aviso', 'etapa', 'motivo')}
            novo.update(status='agendado_publer', conciliado=agora_iso(), obs=expl)
            if post_id:
                novo['post_id'] = post_id
            linha = f'  {rid}: o post EXISTE ({expl}) -> agendado_publer; não sai de novo'
        elif res == 'travado':
            novo = {k: v for k, v in est.items() if k not in ('mensagem', 'etapa')}
            novo.update(status=TRAVADO, motivo=expl, aviso=AVISO_TRAVADO, conciliado=agora_iso())
            if post_id:
                novo['post_id'] = post_id
            saida['travados'].append((rid, expl))
            linha = f'  {rid}: o post EXISTE, mas está TRAVADO no Publer ({expl}) -> {TRAVADO}'
            if forcado:
                args.forcar.discard(rid)
                linha += (f'\n         --forcar {rid} recusado: o post travado continua no Publer '
                          '(apague-o lá antes, senão sairiam dois)')
        elif res == 'nao_existe':
            novo = {**est, 'status': 'erro', 'etapa': 'recusado', 'mensagem': expl, 'conciliado': agora_iso(),
                    'aviso': 'conferido no Publer: nada foi agendado; dá pra repetir com --repetir-erros'}
            linha = f'  {rid}: o Publer NÃO criou o post ({expl}); dá pra repetir com --repetir-erros'
        elif res == 'em_andamento':
            saida['incertos'].append(rid)
            msg = f'  {rid}: {expl}. Fica de fora; rode de novo daqui a alguns minutos.'
            if forcado:
                args.forcar.discard(rid)
                msg += (f'\n         --forcar {rid} recusado: o job ainda está rodando e pode criar o post a '
                        'qualquer momento; espere ele terminar (repostar agora duplicaria)')
            print(msg)
            continue
        else:
            if forcado:
                print(f'  {rid}: não deu pra confirmar ({expl}); sai de novo por --forcar {rid} '
                      '(a tentativa anterior fica guardada em "anteriores")')
            else:
                saida['incertos'].append(rid)
                if 'não pôde ser consultado' in expl or 'falhou' in expl:
                    dica = ('Rode de novo daqui a alguns minutos; se continuar sem resposta, confira os agendados no '
                            f'Publer e, se o post NÃO estiver lá, use --forcar {rid}')
                else:
                    dica = f'Confira os agendados no Publer; se o post NÃO estiver lá, use --forcar {rid}'
                print(f'  {rid}: não deu pra confirmar ({expl}).\n         Fica de fora. {dica}')
            continue
        try:
            gravar_estado(semana, rid, novo, est, args.rede)
        except ConflitoFila as e:
            print(f'  {rid}: não gravei a conferência: {e}')
            saida['incertos'].append(rid)
            args.forcar.discard(rid)
            continue
        print(linha)
    return saida


def garantir_futuro(quando, etapa):
    if quando < dt.datetime.now(FUSO) + MARGEM_POST:
        raise HorarioPassou(f'{fmt_quando(quando)} já está a menos de {MARGEM_POST.seconds // 60} min '
                            f'({etapa}); rode de novo o MESMO comando: os horários que já passaram são pulados')


def anteriores_de(item, rede):
    """Ao repostar com --forcar um item que pode ter post antigo, guarda a tentativa anterior (o post dela pode
    aparecer depois e precisa de rastro); a corrente de tentativas antigas nunca se perde."""
    ultimo = estado_bruto(item, rede)
    if not isinstance(ultimo, dict):
        return []
    lista = list(ultimo.get('anteriores') or [])
    if (precisa_conciliar(item, rede) or status_rede(item, rede) == TRAVADO) and (
            ultimo.get('job_id') or ultimo.get('post_id') or ultimo.get('scheduled_at')):
        lista.append({k: ultimo[k] for k in ('status', 'etapa', 'job_id', 'post_id', 'media_id', 'scheduled_at',
                                             'conta_publer', 'motivo', 'quando') if k in ultimo})
    return lista


def processar_item(cli, semana, rid, quando, conta, args):
    rede = args.rede
    conta_id = str(conta['id'])
    # relê o item: a rodada é longa (20 vídeos de ~140 MB) e alguém pode ter mexido nele depois do planejamento
    item = item_da_fila(semana, rid)
    if item is None or not aceito(item, args):
        st = status_rede(item, rede) if item else 'sumiu da fila'
        print(f'\n[{rid}] PAREI sem postar: o item está "{st}" agora (mudou desde o início da rodada). '
              'Rode de novo pra replanejar.')
        return False
    ultimo = estado_bruto(item, rede)     # o que está em disco agora; toda gravação confere contra isto
    print(f'\n[{rid}] {os.path.basename(item["video"])} -> {fmt_quando(quando)}', flush=True)
    base = {'scheduled_at': quando.isoformat(timespec='seconds'), 'conta_publer': conta_id,
            'conta_nome': str(conta.get('name') or '')}
    if rede == 'instagram':
        base['trial_reel'] = args.trial
    anteriores = anteriores_de(item, rede)
    if anteriores:
        base['anteriores'] = anteriores
    etapa, extra, agendando = 'upload', {}, None
    try:
        garantir_futuro(quando, 'antes do upload')
        campos = {'in_library': 'true'} if args.biblioteca else {}
        enviado = desembrulhar(cli.upload(item['video'], campos))
        if isinstance(enviado, dict) and enviado.get('id'):
            extra['media_id'] = enviado['id']
        etapa = 'midia'
        duracao = duracao_video(item['video'])
        checar_midia_enviada(enviado, rede, duracao)
        validade = validade_da_rede(enviado, rede)
        print(f'  upload ok (mídia {enviado["id"]}' +
              (f'; validity.{rede} = {json.dumps(validade, ensure_ascii=False)}' if validade is not None else '') +
              ')', flush=True)
        midia = preparar_midia(cli, enviado, rede, duracao)
        etapa = 'montar'
        corpo = corpo_post(rede, conta_id, midia, item['legenda'].strip(), quando, args)
        validar_corpo(corpo, rede)
        garantir_futuro(quando, 'antes de agendar')
        # grava ANTES de criar o post: se o processo morrer daqui em diante (Terminal fechado, reboot),
        # a próxima rodada vê "agendando" e confere no Publer em vez de criar um segundo post
        agendando = {'status': 'agendando', **base, **extra, 'quando': agora_iso()}
        gravar_estado(semana, rid, agendando, ultimo, rede)
        ultimo = agendando
        anotar_diario(semana, {'evento': 'antes_do_post', 'id': rid, 'rede': rede, 'conta_publer': conta_id,
                               'scheduled_at': base['scheduled_at'], 'media_id': extra.get('media_id')})
        etapa = 'agendar'
        resp = desembrulhar(cli.json('POST', '/posts/schedule', corpo=corpo))
        job_id = resp.get('job_id') if isinstance(resp, dict) else None
        if not job_id:
            raise ErroPubler(f'o Publer não devolveu job_id: {str(resp)[:300]}')
        extra['job_id'] = job_id
        etapa = 'job'
        anotar_diario(semana, {'evento': 'job_recebido', 'id': rid, 'rede': rede, 'conta_publer': conta_id,
                               'scheduled_at': base['scheduled_at'], 'job_id': job_id})
        agendando = {**agendando, 'job_id': job_id}
        gravar_estado(semana, rid, agendando, ultimo, rede)
        ultimo = agendando
        plano = esperar_job(cli, job_id)
    except HorarioPassou as e:
        print(f'  PAREI sem mexer no {rid}: {e}')
        return False
    except ConflitoFila as e:
        if etapa in ('agendar', 'job'):
            if agendando and reparar_registro(semana, rid, rede, agendando):
                print(f'  ATENÇÃO: o post foi criado no Publer para {fmt_quando(quando)}'
                      + (f' (job {extra["job_id"]})' if extra.get('job_id') else '') +
                      f', mas {e}. O item tinha voltado pra "pendente" (uma cópia velha da fila foi gravada por '
                      'cima), então regravei o registro do POST ("agendando" + job): a próxima rodada confere no '
                      'Publer e não reposta. Parei aqui.')
            else:
                print(f'  ATENÇÃO: o post foi (ou pode ter sido) criado no Publer para {fmt_quando(quando)}'
                      + (f' (job {extra["job_id"]})' if extra.get('job_id') else '') +
                      f', mas {e}.\n  Confira no Publer e na fila: pode haver post duplicado (rastro do POST em '
                      f'filas/{semana}.posts.log). Parei aqui.')
        else:
            print(f'  PAREI sem postar: {e}.' + (f' (a mídia {extra["media_id"]} ficou no Publer sem uso)'
                                                 if extra.get('media_id') else ''))
        return False
    except (Exception, KeyboardInterrupt) as e:
        if isinstance(e, PostRecusado):
            etapa = 'recusado'                # o job terminou com falha explícita: o post não existe
        elif etapa == 'agendar' and isinstance(e, ErroPubler) and e.status and 400 <= e.status < 500:
            etapa = 'recusado'                # 4xx no POST: o Publer recusou o pedido, nada foi criado
        if isinstance(e, KeyboardInterrupt):
            msg = f'interrompido ({e})' if str(e) else 'interrompido (Ctrl+C)'
        else:
            msg = str(e)
        estado = {'status': 'erro', 'mensagem': msg, 'etapa': etapa, **base, **extra, 'quando': agora_iso()}
        if etapa in ('agendar', 'job'):
            estado['aviso'] = ('o post PODE ter sido criado: a próxima rodada confere no Publer antes de repetir '
                               '(não use --repetir-erros pra isso; só --forcar depois de conferir)')
        elif etapa == 'recusado':
            estado['aviso'] = 'o Publer recusou o post (nada foi agendado); corrija a causa e repita com --repetir-erros'
        else:
            estado['aviso'] = 'nada foi agendado; dá pra repetir com --repetir-erros'
        try:
            gravar_estado(semana, rid, estado, ultimo, rede)
            registro = 'a fila registrou o erro.'
        except ConflitoFila as c:
            if etapa in ('agendar', 'job') and reparar_registro(semana, rid, rede, estado):
                registro = f'o item tinha voltado pra "pendente" ({c}); regravei o erro junto com o registro do POST.'
            else:
                registro = f'NÃO gravei o erro na fila: {c}' + (
                    f' (rastro do POST em filas/{semana}.posts.log)' if etapa in ('agendar', 'job') else '')
        print(f'  ERRO na etapa "{etapa}": {msg}\n  {estado["aviso"]}\n  Parei aqui; {registro}')
        return False
    # o job concluiu sem falhas: antes de dar o item como agendado, confere se o post vai mesmo sair (workspace
    # travado, conta pedindo reautorização, aprovação). Uma interrupção aqui deixa "agendando" + job_id em disco:
    # a próxima rodada confere no Publer e não reposta.
    post_id, motivo = verificar_post(cli, conta_id, quando, item['legenda'], plano)
    final = {'status': TRAVADO if motivo else 'agendado_publer', **base, 'media_id': extra['media_id'],
             'job_id': extra['job_id'], 'quando': agora_iso()}
    if motivo:
        final.update(motivo=motivo, aviso=AVISO_TRAVADO)
    if post_id:
        final['post_id'] = post_id
    try:
        gravar_estado(semana, rid, final, ultimo, rede)
    except ConflitoFila as e:
        if reparar_registro(semana, rid, rede, final):
            print(f'  ATENÇÃO: {e}; o item tinha voltado pra "pendente" (cópia velha da fila gravada por cima), '
                  f'então regravei o registro do post ({final["status"]}). Parei aqui.')
        else:
            print(f'  ATENÇÃO: o post FOI agendado no Publer para {fmt_quando(quando)} (job {extra["job_id"]}), mas '
                  f'{e}.\n  Confira no Publer e na fila: pode haver post duplicado (rastro do POST em '
                  f'filas/{semana}.posts.log). Parei aqui.')
        return False
    if motivo:
        print(f'  ATENÇÃO: o post foi criado no Publer para {fmt_quando(quando)}, mas está TRAVADO: {motivo}.\n'
              f'  {AVISO_TRAVADO}\n  Parei o lote aqui pra não subir os outros vídeos pro mesmo travamento.')
        return False
    print(f'  agendado no Publer ({REDES[rede]["nome"]}'
          + (f', Trial Reel {args.trial}' if rede == 'instagram' else '') + f') para {fmt_quando(quando)}'
          + (f' (post {post_id})' if post_id else ''), flush=True)
    return True


# ---------------------------------------------------------------- comandos

def cmd_contas(args, base=BASE, chave=None):
    cli = Cliente(chave or obter_chave(), base=base)
    ws = listar_workspaces(cli)
    if args.workspace:
        ws = [w for w in ws if w.get('id') == args.workspace] or [{'id': args.workspace, 'name': '?'}]
    if not ws:
        print('nenhum workspace visível para esta chave')
        return 1
    for w in ws:
        print(f"workspace {w.get('id')}  {w.get('name') or ''}  (papel: {w.get('role') or '-'}, "
              f"plano: {w.get('plan') or '-'})")
        cli.workspace = w.get('id')
        try:
            contas = listar_contas(cli)
        except ErroPubler as e:
            print(f'   (não consegui listar as contas: {e})')
            continue
        for c in contas:
            print('   ' + descrever_conta(c))
        if not contas:
            print('   (sem contas sociais)')
    return 0


def planejar(fila, args, horarios, por_dia, inicio, externos=None):
    """Seleciona os itens e dá um horário a cada um. Devolve (plano, pulados, a_conferir, info), com info =
      'ocupados'   horários da grade pulados por já terem post da conta (nas filas ou no Publer);
      'passados'   horários da grade a partir do --inicio pulados por já terem passado (ou faltarem < 15 min);
      'deslocados' quantos vídeos caíram num dia depois do que cairiam sem esses horários passados;
      'estouro'    (n, início da janela) se alguma janela de 24 h passa do teto da rede, senão None;
      'publer'     True se `externos` (agendados no Publer pra conta, de agenda_no_publer) entraram na conta.
    O item que sai de novo com --forcar não ocupa o próprio horário antigo (a pessoa conferiu que o post não existe)."""
    selecionados, pulados, a_conferir = selecionar(fila['itens'], args)
    ignorar = {(fila['semana'], rid) for rid in args.forcar}
    ocupados = juntar_ocupados(agenda_da_rede(args.rede, ignorar), externos or [])
    grade = horarios[:por_dia]
    piso = dt.datetime.now(FUSO) + MARGEM_PLANO
    slots = gerar_horarios(inicio, grade, len(selecionados), piso, ocupados)
    plano = list(zip(selecionados, slots))
    pulados_ocup, passados = [], []
    if slots:
        usados = set(slots)
        d = inicio.date()
        while d <= slots[-1].date():
            for h in grade:
                q = dt.datetime.combine(d, h, tzinfo=FUSO)
                if inicio <= q <= slots[-1] and q not in usados:
                    (passados if q < piso else pulados_ocup).append(q)
            d += dt.timedelta(days=1)
    deslocados = 0
    if passados:
        ideal = gerar_horarios(inicio, grade, len(selecionados), inicio, ocupados)
        if ideal:
            deslocados = sum(1 for q in slots if q.date() > ideal[-1].date())
    info = {'ocupados': pulados_ocup, 'passados': passados, 'deslocados': deslocados,
            'estouro': estouro_24h(args.rede, slots, ocupados), 'publer': externos is not None}
    return plano, pulados, a_conferir, info


def planejar_com_publer(cli, conta_id, fila, args, horarios, por_dia, inicio):
    """planejar() somando o que já está agendado no Publer pra conta (inclusive fora das filas). A janela lida
    cobre do dia anterior ao --inicio até um dia depois do último horário do plano (o teto é de 24 h corridas);
    se o plano passar da janela lida, lê de novo mais longe."""
    n = len(selecionar(fila['itens'], args)[0])
    de = inicio - dt.timedelta(days=1)
    ate = inicio + dt.timedelta(days=-(-max(n, 1) // max(por_dia, 1)) + 2)
    for _ in range(6):
        externos = agenda_no_publer(cli, conta_id, de, ate)
        resultado = planejar(fila, args, horarios, por_dia, inicio, externos)
        plano = resultado[0]
        if not plano or plano[-1][1] + dt.timedelta(days=1) <= ate:
            return resultado
        ate = plano[-1][1] + dt.timedelta(days=2)
    return resultado


def problemas_do_plano(plano, args, info):
    """[(id, problema)] que barram a rodada: os de cada item + o teto de 24 h da rede."""
    problemas = [(it['id'], p) for it, _ in plano for p in problemas_do_item(it, args.rede)]
    if info.get('estouro'):
        n, ini = info['estouro']
        cfg = REDES[args.rede]
        problemas.append(('agenda', f'o plano põe {n} posts de {cfg["nome"]} numa janela de 24 h (a partir de '
                                    f'{fmt_quando(ini.astimezone(FUSO))}), contando o que já está agendado nas '
                                    f'filas; o limite é {cfg["limite_dia"]}/24 h corridas (Publer Business'
                                    + ('; a Meta permite 100' if args.rede == 'instagram' else '') +
                                    '). Adiante o --inicio ou diminua o --por-dia'))
    return problemas


def descrever_agenda(args, horarios, por_dia, inicio):
    grade = horarios[:por_dia]
    if args.intervalo:
        txt = (f'{por_dia} por dia, de {args.intervalo} em {args.intervalo} min, das {grade[0]:%H:%M} às '
               f'{grade[-1]:%H:%M}')
    else:
        txt = f'{por_dia} por dia em {", ".join(h.strftime("%H:%M") for h in grade)}'
    return f'{txt} (Brasília), a partir de {fmt_quando(inicio)}'


def descrever_opcoes(args):
    if args.rede == 'tiktok':
        return (f'privacidade {args.privacidade}; comentários {"não" if args.sem_comentarios else "sim"}, '
                f'duet {"não" if args.sem_duet else "sim"}, stitch {"não" if args.sem_stitch else "sim"}')
    if args.trial == 'MANUAL':
        return 'Trial Reel MANUAL: não vai pro feed nem pros seguidores; você libera a vencedora no app'
    return f'Trial Reel {args.trial}: não vai pro feed; o Instagram PODE liberar sozinho pros seguidores'


def imprimir_plano(fila, plano, pulados, a_conferir, args, horarios, por_dia, inicio, info):
    """Mostra o plano e devolve a lista de problemas [(id, problema)]."""
    nome = REDES[args.rede]['nome']
    resumo_pulados = ', '.join(f'{k}: {v}' for k, v in sorted(pulados.items()))
    print(f'fila {fila["semana"]}: {len(fila["itens"])} vídeos; {len(plano)} a agendar no {nome}'
          + (f'; pulados ({resumo_pulados})' if pulados else ''))
    print(f'{descrever_agenda(args, horarios, por_dia, inicio)}; {descrever_opcoes(args)}')
    if plano:
        print(f'plano: de {fmt_quando(plano[0][1])} a {fmt_quando(plano[-1][1])}')
    if info.get('passados'):
        ps = info['passados']
        print(f'AVISO: {len(ps)} horário(s) da grade a partir do --inicio ({fmt_quando(inicio)}) já passaram ou faltam '
              f'menos de {MARGEM_PLANO.seconds // 60} min, e foram pulados ('
              + ', '.join(fmt_quando(q) for q in ps[:3]) + (' …' if len(ps) > 3 else '') + ')'
              + (f'; o plano começa em {fmt_quando(plano[0][1])}' if plano else '')
              + (f' e {info["deslocados"]} vídeo(s) caem num dia depois do que cairiam' if info.get('deslocados') else '')
              + '. Confira se é isso mesmo (ou ajuste o --inicio).')
    if info.get('ocupados'):
        fonte = 'agendados nas filas ou no Publer' if info.get('publer') else 'agendados em alguma fila'
        print(f'horários já ocupados no {nome} ({fonte}) e pulados: '
              + ', '.join(fmt_quando(q) for q in info['ocupados'][:8]) + (' …' if len(info['ocupados']) > 8 else ''))
    print()
    imprimir_tabela(plano, args.rede)
    imprimir_a_conferir(a_conferir, args.rede)
    travados = [it for it in recorte(fila['itens'], args)
                if status_rede(it, args.rede) == TRAVADO and it['id'] not in args.forcar]
    if travados:
        print(f'\nTRAVADOS NO PUBLER ({TRAVADO}): o post existe, mas não vai sair assim.')
        for it in travados:
            est = estado_bruto(it, args.rede) or {}
            print(f'  {it["id"]:9} {est.get("motivo") or "?"}' + (f'; post {est["post_id"]}' if est.get('post_id') else ''))
        print(f'  {AVISO_TRAVADO}.\n  A rodada real confere esses itens antes de tudo e não sobe nada enquanto '
              'continuarem travados.')
    imprimir_aviso_duracao(plano, args.rede)
    problemas = problemas_do_plano(plano, args, info)
    if problemas:
        print('\nPROBLEMAS:')
        for rid, p in problemas:
            print(f'  {rid}: {p}')
    return problemas


def conferir_opcoes(args):
    """Opções que só valem numa rede; preenche os padrões da rede escolhida."""
    if args.rede == 'tiktok':
        if args.trial is not None:
            sys.exit('--trial vale só pro Instagram (--rede instagram)')
        args.privacidade = args.privacidade or 'PUBLIC_TO_EVERYONE'
        if args.privacidade not in PRIVACIDADES:
            sys.exit(f'--privacidade precisa ser uma de: {", ".join(PRIVACIDADES)}')
        return
    so_tiktok = [o for o, v in (('--privacidade', args.privacidade), ('--sem-comentarios', args.sem_comentarios),
                                ('--sem-duet', args.sem_duet), ('--sem-stitch', args.sem_stitch)) if v]
    if so_tiktok:
        sys.exit(f'{", ".join(so_tiktok)}: opção só do TikTok, não vale com --rede instagram')
    if args.trial is None:
        args.trial = TRIAL_PADRAO
    elif args.trial not in TRIAL_MODOS:
        sys.exit(f'--trial precisa ser um de: {", ".join(TRIAL_MODOS)}')
    if args.trial != TRIAL_PADRAO:
        print(f'ATENÇÃO: --trial {args.trial}. O Instagram pode liberar sozinho pros seguidores o Reel que for bem '
              '(a ajuda do Publer fala em até ~72 h), e com várias versões do mesmo Reel no dia mais de uma pode\n'
              f'  chegar aos seguidores. A decisão de 06/10/2026 é {TRIAL_PADRAO}.')


def resolver_agenda(args, inicio):
    """(horarios, por_dia) a partir de --horarios OU --intervalo/--por-dia, dentro do teto diário da rede."""
    cfg = REDES[args.rede]
    if args.intervalo is not None:
        if args.horarios is not None:
            sys.exit('use --horarios OU --intervalo, não os dois')
        if not args.por_dia or args.por_dia < 1:
            sys.exit('--intervalo precisa de --por-dia N (ex.: --intervalo 20 --por-dia 21)')
        por_dia = args.por_dia
        if por_dia > cfg['limite_dia']:
            sys.exit(f'--por-dia {por_dia} passa do limite diário do {cfg["nome"]} ({cfg["limite_dia"]} posts/24 h)')
        # revisão do Fable (06/10): horário dentro da margem de 15 min era tratado como passado e o vídeo ia pro
        # DIA SEGUINTE sem perguntar. No modo intervalo a grade inteira anda pra frente no MESMO dia, no mesmo
        # passo (rodar o mesmo comando depois de uma parada continua hoje, não amanhã)
        piso = dt.datetime.now(FUSO) + MARGEM_PLANO + dt.timedelta(minutes=1)
        if inicio < piso and inicio.date() == piso.date():
            passos = -(-int((piso - inicio).total_seconds()) // (args.intervalo * 60))
            novo = inicio + dt.timedelta(minutes=passos * args.intervalo)
            print(f'aviso: o --inicio {inicio:%H:%M} já está dentro da margem de 15 min; a grade começa às '
                  f'{novo:%H:%M} (mesmo dia, mesmo intervalo)')
            inicio = novo
        return horarios_por_intervalo(inicio, args.intervalo, por_dia), por_dia
    horarios = parse_horarios(args.horarios or HORARIOS_PADRAO)
    por_dia = args.por_dia or len(horarios)
    if not 1 <= por_dia <= len(horarios):
        sys.exit(f'--por-dia {por_dia}: precisa ficar entre 1 e a quantidade de --horarios ({len(horarios)}). '
                 f'Pra {por_dia} por dia de N em N minutos, use --intervalo N (ex.: --intervalo 20 --por-dia {por_dia})')
    if por_dia > cfg['limite_dia']:
        sys.exit(f'--por-dia {por_dia} passa do limite diário do {cfg["nome"]} ({cfg["limite_dia"]} posts/24 h)')
    return horarios, por_dia


def _interromper(signum, frame):
    # SIGHUP (fechar a janela do Terminal) e SIGTERM matariam o processo sem passar pelo except que grava o
    # erro; virando KeyboardInterrupt, caem no mesmo caminho do Ctrl+C
    raise KeyboardInterrupt(f'sinal {signal.Signals(signum).name}')


def escolher_conta(contas, args, alvo, rede):
    """A conta da rodada: --conta (conferida pela rede e pelo nome) ou a que bate com contas.<rede> da fila."""
    nome = REDES[rede]['nome']
    if args.conta:
        conta = next((c for c in contas if str(c.get('id')) == args.conta), None)
        if not conta:
            sys.exit(f'--conta {args.conta}: essa conta não existe neste workspace (rode "contas")')
        if not eh_da_rede(conta, rede):
            sys.exit(f'--conta {args.conta} é {conta.get("provider")}, não {nome}. Nada foi enviado.')
        conferir_conta_explicita(conta, alvo, args.conta_confirmada, rede)
        return conta
    return achar_conta(contas, alvo, rede)


def cmd_postar(args, base=BASE, chave=None, usar_keychain=True):
    rede = args.rede
    nome = REDES[rede]['nome']
    fila = filamod.carregar(args.semana)
    alvo = (fila.get('contas') or {}).get(rede) or {'instagram': config.CONTA_INSTAGRAM}.get(rede, config.CONTA_TIKTOK)
    conferir_opcoes(args)
    inicio = parse_inicio(args.inicio)
    horarios, por_dia = resolver_agenda(args, inicio)
    args.forcar = ler_forcar(args.forcar)
    validar_forcar(fila['itens'], args)

    if args.simular:
        tipo = None
        if args.conta:
            plano, pulados, a_conferir, info = planejar(fila, args, horarios, por_dia, inicio)
            nota = (f'\nconta {nome} no Publer: {args.conta} (informada; a simulação não consultou o Publer). Na rodada '
                    f'real o nome dela é conferido com {alvo}, e os horários já agendados no Publer pra ela (inclusive '
                    'fora das filas) entram na grade e no teto de 24 h.')
        else:
            # sem chave a simulação NÃO para: monta o plano só a partir da fila e avisa que a conta não foi conferida
            k = chave or (ler_keychain('api-key') if usar_keychain else None)
            if not k:
                plano, pulados, a_conferir, info = planejar(fila, args, horarios, por_dia, inicio)
                nota = (f'\nconta {nome} no Publer: NÃO conferida (não há chave do Publer no Keychain; o plano acima '
                        f'saiu só da fila). Na rodada real a conta é achada pelo nome ({alvo}).')
            else:
                # só leitura: GET /workspaces, /accounts e /posts (agenda da conta)
                cli = Cliente(k, base=base)
                cli.workspace = resolver_workspace(cli, args.workspace, usar_keychain)
                conta = achar_conta(listar_contas(cli), alvo, rede)
                plano, pulados, a_conferir, info = planejar_com_publer(cli, str(conta['id']), fila, args, horarios,
                                                                       por_dia, inicio)
                tipo = problema_tipo_conta(conta, rede)
                nota = (f'\nconta {nome} no Publer: {descrever_conta(conta)} (só leitura; os horários já agendados no '
                        'Publer pra ela entraram na conta)')
                if tipo:
                    nota += ('\nPROBLEMA: ' if tipo[0] else '\n') + tipo[1]
        problemas = imprimir_plano(fila, plano, pulados, a_conferir, args, horarios, por_dia, inicio, info)
        print(nota)
        print('simulação: nada foi enviado ao Publer e a fila não foi alterada'
              + ('; os PROBLEMAS acima barrariam a rodada real' if problemas or (tipo and tipo[0]) else ''))
        return 0

    plano, pulados, a_conferir, info = planejar(fila, args, horarios, por_dia, inicio)
    # checagem local antes de qualquer rede (disco montado, legenda, tamanho, duração, teto de 24 h)
    problemas = problemas_do_plano(plano, args, info)
    if problemas:
        imprimir_plano(fila, plano, pulados, a_conferir, args, horarios, por_dia, inicio, info)
        print('\nNada foi enviado: resolva os problemas acima primeiro.')
        return 1
    travados = [it for it in recorte(fila['itens'], args) if status_rede(it, rede) == TRAVADO]
    if not plano and not a_conferir and not travados:
        imprimir_plano(fila, plano, pulados, a_conferir, args, horarios, por_dia, inicio, info)
        print('\nnada pendente nesse recorte')
        return 0

    trava = travar_fila(args.semana, rede)
    trava_rede, antigos = None, {}
    try:
        trava_rede = travar_rede(rede, args.semana)
        for s in (signal.SIGHUP, signal.SIGTERM):
            try:
                antigos[s] = signal.signal(s, _interromper)
            except ValueError:                       # fora da thread principal não dá pra instalar
                pass
        cli = Cliente(chave or obter_chave(), base=base)
        cli.workspace = resolver_workspace(cli, args.workspace, usar_keychain)
        conta = escolher_conta(listar_contas(cli), args, alvo, rede)
        if conta.get('status') and conta.get('status') != 'active':
            print(f'aviso: a conta está com status "{conta.get("status")}" no Publer')
        tipo = problema_tipo_conta(conta, rede)
        if tipo and tipo[0]:
            print(f'conta {nome}: {descrever_conta(conta)}')
            print(tipo[1])
            return 1
        if tipo:
            print(tipo[1])
        print(f'conta {nome}: {descrever_conta(conta)}')

        # resolve primeiro o que pode já existir no Publer, depois replaneja com a fila atualizada e com a
        # agenda da conta no Publer (posts de fora das filas também ocupam horário e contam no teto)
        pend = conciliar_pendencias(cli, args.semana, args)
        if pend['travados']:
            rid0, motivo0 = pend['travados'][0]
            print(f'\nNada foi enviado: {len(pend["travados"])} post(s) desta fila estão travados no Publer '
                  f'({", ".join(r for r, _ in pend["travados"])}; {rid0}: {motivo0}).\n'
                  f'  {AVISO_TRAVADO}.\n  Subir mais vídeos agora só criaria mais posts travados.')
            return 1
        fila = filamod.carregar(args.semana)
        plano, pulados, a_conferir, info = planejar_com_publer(cli, str(conta['id']), fila, args, horarios,
                                                               por_dia, inicio)
        print()
        problemas = imprimir_plano(fila, plano, pulados, a_conferir, args, horarios, por_dia, inicio, info)
        if problemas:
            print('\nNada foi enviado: resolva os problemas acima primeiro.')
            return 1
        if not plano:
            print('\nnada a agendar nesse recorte')
            return 0
        feitos = 0
        for item, quando in plano:
            if not processar_item(cli, args.semana, item['id'], quando, conta, args):
                print(f'\n{feitos} de {len(plano)} agendados antes de parar.')
                return 1
            feitos += 1
        print(f'\npronto: {feitos} vídeo(s) agendado(s) no Publer ({nome}).')
        if a_conferir:
            print(f'atenção: {len(a_conferir)} item(ns) ficaram de fora por não dar pra confirmar no Publer '
                  f'({", ".join(i["id"] for i in a_conferir)}).')
        return 0
    finally:
        for s, h in antigos.items():
            signal.signal(s, h)
        if trava_rede is not None:
            os.close(trava_rede)                     # solta a trava da rede
        os.close(trava)                              # solta a trava da fila


# ---------------------------------------------------------------- autoteste offline

def cmd_autoteste(args):
    """Servidor falso local (thread): upload em streaming íntegro + fluxo completo do postar numa fila temporária,
    no TikTok (1–8, pela linha de comando do publer_tiktok.py), no Instagram Trial Reels (9–18) e nos achados da
    revisão de 06/10/2026 (19–30: post travado, agenda do Publer, tipo da conta, validity processado, montar sem
    perda, travas, --forcar com job rodando, estado malformado, --inicio no passado, rodada cheia de 21)."""
    import contextlib
    import http.server
    import io
    import tracemalloc

    CHAVE, WS, CONTA = 'chave-falsa-do-autoteste', 'ws-teste', 'conta-tiktok-teste'
    CONTA_IG = 'conta-ig'
    falhas, total = [], [0]

    def conferir(cond, desc):
        total[0] += 1
        print(('  ok      ' if cond else '  FALHOU  ') + desc)
        if not cond:
            falhas.append(desc)

    tmp = tempfile.TemporaryDirectory(prefix='publer-autoteste-')
    # posts = corpos recebidos em POST /posts/schedule; publer = o que GET /posts devolve (inclui posts "antigos")
    srv = {'uploads': [], 'posts': [], 'publer': [], 'jobs': {}, 'gets_midia': {}, 'reqs': 0, 'forcar_429': True,
           'estado_no_post': [], 'ao_upload': None, 'sinal_no_job': False, 'validade_ig': True,
           # cenários novos: workspace travado (plan.locked), estado do post criado, resumo de GET /posts que só
           # diz "scheduled", servidor que ignora o filtro de estado, validity do GET /media, tipo da conta IG,
           # gancho no POST (cópia velha da fila gravada por cima)
           'ws_travado': False, 'estado_novo': 'scheduled', 'resumo_generico': False, 'filtro_ignorado': False,
           'validade_ig_midia': True, 'tipo_ig': 'business', 'ao_post': None}

    def estado_em_disco(texto, rede):
        """Estado.<rede>, no disco, do item cuja legenda é `texto` (o servidor espia a fila no momento do POST)."""
        for nome in os.listdir(filamod.FILAS):
            if nome.endswith('.json'):
                with open(os.path.join(filamod.FILAS, nome), encoding='utf-8') as fh:
                    for it in json.load(fh)['itens']:
                        if it['legenda'] == texto:
                            return estado_bruto(it, rede)
        return None

    class Falso(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *a):
            pass

        def _resp(self, status, dado, cab=None):
            corpo = json.dumps(dado).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(corpo)))
            for k, v in (cab or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _autorizado(self, com_ws=True):
            if self.headers.get('Authorization') != f'Bearer-API {CHAVE}':
                self._resp(401, {'errors': ['chave inválida']})
                return False
            if com_ws and self.headers.get('Publer-Workspace-Id') != WS:
                self._resp(403, {'errors': ['Publer-Workspace-Id ausente']})
                return False
            return True

        def do_GET(self):
            srv['reqs'] += 1
            u = urllib.parse.urlsplit(self.path)
            if u.path == '/api/v1/workspaces':
                if self._autorizado(com_ws=False):
                    self._resp(200, [{'id': WS, 'name': 'Workspace de teste', 'role': 'owner'}])
            elif not self._autorizado():
                return
            elif u.path == '/api/v1/accounts':
                self._resp(200, {'accounts': [
                    {'id': CONTA_IG, 'provider': 'instagram', 'name': 'anadareconecta', 'type': srv['tipo_ig'],
                     'status': 'active'},
                    {'id': CONTA, 'provider': 'tiktok', 'name': 'Ana da Reconecta', 'status': 'active'},
                    {'id': 'conta-outra', 'provider': 'tiktok', 'name': 'reconectaoficial', 'status': 'active'},
                    {'id': 'conta-ig-outra', 'provider': 'instagram', 'name': 'reconectaoficial', 'type': 'business',
                     'status': 'active'}]})
            elif u.path.startswith('/api/v1/media/'):
                mid = u.path.rsplit('/', 1)[1]
                n = srv['gets_midia'][mid] = srv['gets_midia'].get(mid, 0) + 1
                thumbs = [] if n == 1 else [{'id': f't{i}', 'small': f'https://cdn.teste/{mid}_{i}s.jpg',
                                             'real': f'https://cdn.teste/{mid}_{i}.jpg'} for i in range(3)]
                self._resp(200, {'id': mid, 'type': 'video', 'path': f'https://cdn.teste/{mid}.mp4', 'thumbnails': thumbs,
                                 'validity': {'tiktok': {'video': True},
                                              'instagram': {'reel': srv['validade_ig_midia'], 'post': True}}})
            elif u.path.startswith('/api/v1/job_status/'):
                jid = u.path.rsplit('/', 1)[1]
                job = srv['jobs'][jid]
                job['polls'] += 1
                if job.get('lento'):                     # job que nunca termina (o Publer ainda processando)
                    self._resp(200, {'status': 'working', 'payload': {}})
                elif job['polls'] == 1:
                    self._resp(200, {'status': 'working', 'payload': {}})
                    if srv['sinal_no_job']:              # simula o Terminal sendo fechado no meio do polling
                        srv['sinal_no_job'] = False
                        os.kill(os.getpid(), signal.SIGTERM)
                elif job['falha']:
                    self._resp(200, {'status': 'complete', 'payload': {'failures': [
                        {'account_id': job['conta'], 'provider': job['rede'], 'message': 'falha simulada pelo autoteste'}]}})
                else:
                    self._resp(200, {'success': True, 'data': {'status': 'complete', 'result': {
                        'status': 'complete', 'payload': {'failures': {}},
                        'plan': {'rate': 'business', 'locked': srv['ws_travado']}}}})
            elif u.path == '/api/v1/posts':
                consulta = urllib.parse.parse_qs(u.query)
                filtro = (consulta.get('state') or ['all'])[0]
                contas_f = consulta.get('account_ids[]')
                posts = []
                for p in srv['publer']:
                    st = p.get('state', 'scheduled')
                    if contas_f and p['account_id'] not in contas_f:
                        continue
                    if not srv['filtro_ignorado'] and filtro != 'all' and not (
                            st == filtro or (filtro == 'scheduled' and st.startswith('scheduled'))):
                        continue
                    mostrado = 'scheduled' if srv['resumo_generico'] and st.startswith('scheduled') else st
                    q = dt.datetime.fromisoformat(p['scheduled_at'])
                    posts.append({**p, 'state': mostrado,
                                  'scheduled_at': q.strftime('%Y-%m-%dT%H:%M:%S.000%z')[:-2] + ':' + q.strftime('%z')[-2:]})
                self._resp(200, {'posts': posts, 'total': len(posts), 'page': 0, 'total_pages': 1})
            else:
                self._resp(404, {'errors': ['rota desconhecida']})

        def do_POST(self):
            srv['reqs'] += 1
            u = urllib.parse.urlsplit(self.path)
            if u.path == '/api/v1/media':
                cl = self.headers.get('Content-Length')
                reg = {'auth': self.headers.get('Authorization'), 'ws': self.headers.get('Publer-Workspace-Id'),
                       'content_type': self.headers.get('Content-Type') or '', 'content_length': cl,
                       'transfer_encoding': self.headers.get('Transfer-Encoding'), 'recebidos': 0,
                       'arquivo': os.path.join(tmp.name, f'corpo-{len(srv["uploads"])}.bin')}
                falta = int(cl or 0)
                with open(reg['arquivo'], 'wb') as out:      # o servidor também recebe em pedaços pequenos
                    while falta > 0:
                        b = self.rfile.read(min(65536, falta))
                        if not b:
                            break
                        out.write(b)
                        falta -= len(b)
                        reg['recebidos'] += len(b)
                srv['uploads'].append(reg)
                if not self._autorizado():
                    return
                if srv['ao_upload']:
                    srv['ao_upload']()
                if srv['forcar_429']:                        # 1º upload: simula o limite pra testar a espera
                    srv['forcar_429'] = False
                    self._resp(429, {'error': 'Rate limit exceeded. Retry later.'}, {'Retry-After': '1'})
                    return
                mid = f'midia-{len(srv["uploads"])}'
                self._resp(200, {'id': mid, 'type': 'video', 'path': f'/media/{mid}', 'thumbnail': f'/media/{mid}.jpg',
                                 'validity': {'tiktok': {'video': True},
                                              'instagram': {'reel': srv['validade_ig'], 'post': True, 'story': False}},
                                 'name': 'x.mp4'})
            elif u.path == '/api/v1/posts/schedule':
                n = int(self.headers.get('Content-Length') or 0)
                corpo = json.loads(self.rfile.read(n) or b'{}')
                if not self._autorizado():
                    return
                srv['posts'].append(corpo)
                jid = f'job-{len(srv["posts"])}'
                redes = corpo['bulk']['posts'][0]['networks']
                rede = next(iter(redes))
                texto = redes[rede]['text']
                srv['estado_no_post'].append(estado_em_disco(texto, rede))
                falha = 'FORCAR_FALHA' in texto
                a = corpo['bulk']['posts'][0]['accounts'][0]
                srv['jobs'][jid] = {'polls': 0, 'falha': falha, 'rede': rede, 'conta': a['id']}
                if not falha:
                    srv['publer'].append({'id': f'post-{len(srv["publer"]) + 1}', 'account_id': a['id'],
                                          'scheduled_at': a['scheduled_at'], 'text': texto, 'network': rede,
                                          'state': srv['estado_novo']})
                if srv['ao_post']:
                    srv['ao_post'](texto, rede)
                # alterna os dois envelopes que a doc mostra
                self._resp(200, {'job_id': jid} if len(srv['posts']) % 2 else {'success': True, 'data': {'job_id': jid}})
            else:
                self._resp(404, {'errors': ['rota desconhecida']})

    def partes_multipart(caminho, content_type):
        """Parser independente do cliente: separa o corpo pela fronteira declarada no Content-Type."""
        fronteira = content_type.split('boundary=', 1)[1].strip().strip('"').encode()
        with open(caminho, 'rb') as f:
            corpo = f.read()
        delim = b'\r\n--' + fronteira
        pedacos = (b'\r\n' + corpo).split(delim)
        partes = {}
        for p in pedacos[1:]:
            if p.startswith(b'--'):
                break
            cab, _, dados = p[2:].partition(b'\r\n\r\n')
            cabs = dict(linha.split(': ', 1) for linha in cab.decode().split('\r\n'))
            nome = cabs['Content-Disposition'].split('name="', 1)[1].split('"', 1)[0]
            partes[nome] = (cabs, dados)
        return partes, pedacos[-1]

    class Servidor(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            # no teste 8 o SIGTERM interrompe o cliente no meio da leitura e a conexão fecha com RST: é esperado
            if isinstance(sys.exc_info()[1], ConnectionResetError):
                return
            super().handle_error(request, client_address)

    servidor = Servidor(('127.0.0.1', 0), Falso)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{servidor.server_address[1]}/api/v1'
    espera_original = dict(ESPERA)
    fila_original = filamod.FILAS
    chave_original = globals()['obter_chave']
    try:
        ESPERA.update({'job_ini': 0.05, 'job_max': 0.1, 'midia_ini': 0.05, 'midia_max': 0.1})

        # 1) upload em streaming de ~5 MB: corpo íntegro, headers certos, 429 respeitado, memória baixa
        print('1) upload multipart em streaming (~5 MB) contra servidor local')
        arq = os.path.join(tmp.name, 'teste [26] ação.mp4')
        tamanho = 5 * 1024 * 1024 + 12345                     # não múltiplo de 1 MiB: testa o último bloco
        h = hashlib.sha256()
        with open(arq, 'wb') as f:
            falta = tamanho
            while falta:
                b = os.urandom(min(BLOCO, falta))
                f.write(b)
                h.update(b)
                falta -= len(b)
        hash_origem = h.hexdigest()
        cli = Cliente(CHAVE, WS, base=base)
        t0 = time.monotonic()
        tracemalloc.start()
        resp = cli.upload(arq, {'in_library': 'true'}, progresso=False)
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        dur = time.monotonic() - t0
        conferir(isinstance(resp, dict) and resp.get('id') == 'midia-2', f'upload devolveu o id da mídia ({resp.get("id")})')
        conferir(len(srv['uploads']) == 2, 'o 429 com Retry-After foi respeitado e o arquivo reenviado (2 envios)')
        conferir(dur >= 1.0, f'esperou o Retry-After de 1 s antes de reenviar ({dur:.1f} s no total)')
        conferir(pico < 3 * 1024 * 1024, f'pico de memória Python no upload {pico / 1e6:.2f} MB (< 3 MB; arquivo tem {tamanho / 1e6:.1f} MB)')
        reg = srv['uploads'][-1]
        conferir(reg['auth'] == f'Bearer-API {CHAVE}', 'header Authorization = "Bearer-API <chave>"')
        conferir(reg['ws'] == WS, 'header Publer-Workspace-Id presente')
        conferir(reg['content_type'].startswith('multipart/form-data; boundary='), 'Content-Type multipart/form-data com boundary')
        conferir(reg['transfer_encoding'] is None and reg['content_length'] is not None, 'Content-Length fixo (sem chunked)')
        conferir(reg['recebidos'] == int(reg['content_length']), f'servidor recebeu exatamente o Content-Length ({reg["recebidos"]} bytes)')
        partes, fim = partes_multipart(reg['arquivo'], reg['content_type'])
        cab_arq, dados = partes.get('file', ({}, b''))
        conferir(len(dados) == tamanho, f'parte "file" com o mesmo tamanho ({len(dados)} = {tamanho})')
        conferir(hashlib.sha256(dados).hexdigest() == hash_origem, 'parte "file" com o mesmo SHA-256 do arquivo de origem')
        conferir(cab_arq.get('Content-Type') == 'video/mp4', 'parte "file" com Content-Type video/mp4 (octet-stream a API recusa)')
        conferir('filename="teste [26] acao.mp4"' in cab_arq.get('Content-Disposition', ''), 'filename ASCII seguro no Content-Disposition')
        conferir(partes.get('in_library', ({}, b''))[1] == b'true', 'campo in_library enviado junto')
        conferir(fim.startswith(b'--'), 'corpo termina com a fronteira de fechamento')
        del dados, partes

        # 2) fluxo completo do "postar" numa fila temporária (a fila real não é tocada)
        print('2) fluxo completo do postar (fila temporária, servidor local)')
        filamod.FILAS = os.path.join(tmp.name, 'filas')
        os.makedirs(filamod.FILAS)

        def video(nome, kb):
            p = os.path.join(tmp.name, nome)
            with open(p, 'wb') as f:
                f.write(os.urandom(kb * 1024))
            return p

        def item(rid, st, legenda):
            return {'id': rid, 'nome': rid, 'video': video(rid + '.mp4', 300), 'titulo': 't', 'legenda': legenda,
                    'bytes': 300 * 1024, 'estado': {'tiktok': {'status': st}, 'youtube': {'status': 'postado_manual'}}}
        filamod.salvar({'semana': 'SEMTESTE', 'contas': {'tiktok': '@anadareconecta'}, 'itens': [
            item('T1', 'pendente', 'Legenda um. Me conta'), item('T2', 'postado_manual', 'pulado'),
            item('T3', 'pendente', 'FORCAR_FALHA legenda três'), item('T4', 'pendente', 'nunca deve sair')]})
        amanha = (dt.datetime.now(FUSO) + dt.timedelta(days=1)).strftime('%Y-%m-%d')
        ap = montar_parser('tiktok')         # a linha de comando do publer_tiktok.py (invólucro)
        a = ap.parse_args(['postar', 'SEMTESTE', '--inicio', f'{amanha} 09:00', '--por-dia', '2',
                           '--horarios', '09:00,13:00,19:00'])
        srv['forcar_429'] = False
        rc = cmd_postar(a, base=base, chave=CHAVE, usar_keychain=False)
        f = {i['id']: i['estado']['tiktok'] for i in filamod.carregar('SEMTESTE')['itens']}
        conferir(all(i['estado'].get('instagram') == {'status': 'pendente'} for i in filamod.carregar('SEMTESTE')['itens']),
                 'rodada do TikTok não tocou no estado do Instagram (só a migração: pendente)')
        conferir(rc == 1, 'postar parou com código 1 no item que falhou')
        conferir(f['T1'].get('status') == 'agendado_publer', f'T1 -> agendado_publer ({f["T1"].get("status")})')
        conferir(f['T1'].get('post_id') == 'post-1' and f['T1'].get('job_id') == 'job-1', 'T1 guardou post_id e job_id')
        conferir(f['T1'].get('scheduled_at') == f'{amanha}T09:00:00-03:00', f'T1 agendado às 09:00 de Brasília ({f["T1"].get("scheduled_at")})')
        conferir(f['T2'] == {'status': 'postado_manual'}, 'T2 (postado_manual) pulado e intocado')
        conferir(f['T3'].get('status') == 'erro' and 'falha simulada' in f['T3'].get('mensagem', ''), 'T3 -> erro com a mensagem do Publer')
        conferir(f['T3'].get('etapa') == 'recusado', f'T3: recusa explícita do job vira etapa "recusado" ({f["T3"].get("etapa")})')
        conferir(f['T3'].get('scheduled_at') == f'{amanha}T13:00:00-03:00', 'T3 caiu no 2º horário do dia (13:00)')
        conferir(f['T4'] == {'status': 'pendente'}, 'T4 continua pendente (parou no erro, não seguiu)')
        e1 = srv['estado_no_post'][0] or {}
        conferir(e1.get('status') == 'agendando' and e1.get('media_id') == f['T1'].get('media_id')
                 and e1.get('scheduled_at') == f['T1'].get('scheduled_at') and e1.get('conta_publer') == CONTA,
                 'T1 já estava "agendando" (mídia, horário, conta) no disco quando o POST /posts/schedule chegou')
        conferir(f['T1'].get('conta_nome') == 'Ana da Reconecta', 'T1 guardou o nome da conta usada')
        p1 = srv['posts'][0]['bulk']
        t1 = p1['posts'][0]['networks']['tiktok']
        conferir(p1['state'] == 'scheduled' and t1['type'] == 'video', 'payload: bulk.state scheduled + tiktok.type video')
        conferir(t1['text'] == 'Legenda um. Me conta', 'payload: text = legenda da fila')
        conferir(t1['details'] == {'privacy': 'PUBLIC_TO_EVERYONE', 'comment': True, 'duet': True, 'stitch': True,
                                   'promotional': False, 'paid': False, 'reminder': False}, 'payload: details com tudo liberado e público')
        conferir(t1['media'][0]['id'] == f['T1'].get('media_id') and len(t1['media'][0]['thumbnails']) == 3,
                 'payload: media com o id do upload e as thumbnails do GET /media/{id}')
        conferir(set(t1['media'][0]) == {'id', 'type', 'thumbnails'},
                 f'payload: media sem "path" provisório, só id/type/thumbnails ({sorted(t1["media"][0])})')
        conferir(p1['posts'][0]['accounts'][0]['id'] == CONTA, 'conta TikTok achada pelo nome ("Ana da Reconecta" ~ @anadareconecta)')

        # 3) --simular com --conta: nenhuma chamada de rede, nenhuma chave, fila intocada
        print('3) --simular com --conta explícita')
        globals()['obter_chave'] = lambda: (_ for _ in ()).throw(AssertionError('pediu a chave'))
        antes_reqs = srv['reqs']
        with open(filamod.caminho_fila('SEMTESTE'), 'rb') as fh:
            antes = hashlib.sha256(fh.read()).hexdigest()
        a = ap.parse_args(['postar', 'SEMTESTE', '--repetir-erros', '--simular', '--conta', 'TESTE',
                           '--inicio', f'{amanha} 09:00'])
        rc = cmd_postar(a, base='http://127.0.0.1:9/api/v1', chave=None, usar_keychain=False)
        with open(filamod.caminho_fila('SEMTESTE'), 'rb') as fh:
            depois = hashlib.sha256(fh.read()).hexdigest()
        conferir(rc == 0 and srv['reqs'] == antes_reqs, 'simulação não fez requisição nem pediu a chave')
        conferir(antes == depois, 'simulação não alterou a fila')

        def fila_com(semana, *itens):
            filamod.salvar({'semana': semana, 'contas': {'tiktok': '@anadareconecta'}, 'itens': list(itens)})

        def item_est(rid, est, legenda):
            it = item(rid, 'pendente', legenda)
            it['estado']['tiktok'] = est
            return it

        def estados(semana, rede='tiktok'):
            return {i['id']: i['estado'][rede] for i in filamod.carregar(semana)['itens']}

        def postar(*extra):
            return cmd_postar(ap.parse_args(['postar', *extra]), base=base, chave=CHAVE, usar_keychain=False)

        # 4) post que pode já existir: confere no Publer em vez de repostar; --repetir-erros não passa por cima
        print('4) conferência no Publer antes de repetir (agendando / erro depois do POST)')
        depois_amanha = dt.datetime.now(FUSO).date() + dt.timedelta(days=2)
        s1 = dt.datetime.combine(depois_amanha, dt.time(10, 0), tzinfo=FUSO).isoformat(timespec='seconds')
        s2 = dt.datetime.combine(depois_amanha, dt.time(11, 0), tzinfo=FUSO).isoformat(timespec='seconds')
        srv['publer'].append({'id': 'post-antigo', 'account_id': CONTA, 'scheduled_at': s1, 'text': 'Legenda D1'})
        srv['jobs']['job-velho'] = {'polls': 9, 'falha': True, 'rede': 'tiktok', 'conta': CONTA}
        fila_com('SEMDUP',
                 item_est('D1', {'status': 'agendando', 'scheduled_at': s1, 'conta_publer': CONTA, 'media_id': 'mx'},
                          'Legenda D1'),
                 item_est('D2', {'status': 'erro', 'etapa': 'agendar', 'scheduled_at': s2, 'conta_publer': CONTA,
                                 'mensagem': 'timed out'}, 'Legenda D2'),
                 item_est('D3', {'status': 'erro', 'etapa': 'job', 'scheduled_at': s2, 'conta_publer': CONTA,
                                 'job_id': 'job-velho'}, 'Legenda D3'),
                 item_est('D4', {'status': 'erro', 'etapa': 'upload', 'mensagem': 'upload caiu'}, 'Legenda D4'))
        n0 = len(srv['posts'])
        rc = postar('SEMDUP', '--repetir-erros', '--inicio', f'{amanha} 09:00')
        f = estados('SEMDUP')
        conferir(rc == 0 and len(srv['posts']) == n0 + 2, f'só D3 e D4 viraram post novo ({len(srv["posts"]) - n0} POSTs)')
        conferir(f['D1'].get('status') == 'agendado_publer' and f['D1'].get('post_id') == 'post-antigo',
                 'D1 "agendando" achado no Publer -> agendado_publer, sem repostar')
        conferir(f['D2'].get('status') == 'erro' and f['D2'].get('etapa') == 'agendar',
                 'D2 (erro no POST, post não confirmado) ficou de fora mesmo com --repetir-erros')
        conferir(f['D3'].get('status') == 'agendado_publer', 'D3 (job recusado, conferido no Publer) repostado')
        conferir(f['D4'].get('status') == 'agendado_publer', 'D4 (erro no upload) repostado com --repetir-erros')
        n0 = len(srv['posts'])
        rc = postar('SEMDUP', '--forcar', 'D2', '--inicio', f'{amanha} 09:00')
        conferir(rc == 0 and len(srv['posts']) == n0 + 1 and estados('SEMDUP')['D2'].get('status') == 'agendado_publer',
                 'D2 só saiu com --forcar D2')

        # 5) compare-and-swap: item marcado à mão durante o upload não é postado nem sobrescrito
        print('5) item mudado na fila durante a rodada')
        fila_com('SEMCAS', item('C1', 'pendente', 'Legenda C1'))
        manual = {'status': 'postado_manual', 'obs': 'à mão no TikTok Studio'}

        def marcar_manual():
            fc = filamod.carregar('SEMCAS')
            fc['itens'][0]['estado']['tiktok'] = manual
            filamod.salvar(fc)
        srv['ao_upload'] = marcar_manual
        n0 = len(srv['posts'])
        rc = postar('SEMCAS', '--inicio', f'{amanha} 09:00')
        srv['ao_upload'] = None
        conferir(rc == 1 and len(srv['posts']) == n0 and estados('SEMCAS')['C1'] == manual,
                 'parou sem criar post e o postado_manual continua lá')

        # 6) --conta explícita com nome que não bate com a fila
        print('6) --conta explícita conferida pelo nome')
        fila_com('SEMCONTA', item('K1', 'pendente', 'Legenda K1'))
        n0 = len(srv['uploads'])
        try:
            postar('SEMCONTA', '--conta', 'conta-outra', '--inicio', f'{amanha} 09:00')
            abortou = False
        except SystemExit:
            abortou = True
        conferir(abortou and len(srv['uploads']) == n0, '--conta de outro nome abortou antes de subir vídeo')
        rc = postar('SEMCONTA', '--conta', 'conta-outra', '--conta-confirmada', 'reconectaoficial',
                    '--inicio', f'{amanha} 09:00')
        k1 = estados('SEMCONTA')['K1']
        conferir(rc == 0 and k1.get('conta_publer') == 'conta-outra' and k1.get('conta_nome') == 'reconectaoficial',
                 'com --conta-confirmada "<nome exato>" seguiu e gravou conta e nome')

        # 7) trava: duas execuções na mesma fila
        print('7) trava de uma execução por fila')
        fila_com('SEMTRAVA', item('L1', 'pendente', 'Legenda L1'))
        outra = travar_fila('SEMTRAVA')
        n0 = len(srv['uploads'])
        try:
            postar('SEMTRAVA', '--inicio', f'{amanha} 09:00')
            barrou = False
        except SystemExit:
            barrou = True
        finally:
            os.close(outra)
        conferir(barrou and len(srv['uploads']) == n0, 'segunda execução barrada pela trava, sem upload')
        sobras = [n for n in os.listdir(filamod.FILAS) if n.endswith('.part')]
        conferir(not sobras, f'nenhum .part esquecido na pasta das filas ({sobras})')

        # 8) SIGTERM (ou SIGHUP do Terminal fechado) no meio do polling do job
        print('8) sinal no meio do polling do job')
        fila_com('SEMSINAL', item('S1', 'pendente', 'Legenda S1'))
        sigterm_antes = signal.getsignal(signal.SIGTERM)
        srv['sinal_no_job'] = True
        n0 = len(srv['posts'])
        rc = postar('SEMSINAL', '--inicio', f'{amanha} 09:00')
        s = estados('SEMSINAL')['S1']
        conferir(rc == 1 and s.get('status') == 'erro' and s.get('etapa') == 'job' and s.get('job_id'),
                 f'SIGTERM virou erro gravado na etapa "job" com o job_id ({s.get("etapa")}, {s.get("mensagem")})')
        conferir(signal.getsignal(signal.SIGTERM) == sigterm_antes, 'tratador de SIGTERM devolvido ao fim da rodada')
        rc = postar('SEMSINAL', '--inicio', f'{amanha} 09:00')
        conferir(rc == 0 and len(srv['posts']) == n0 + 1 and estados('SEMSINAL')['S1'].get('status') == 'agendado_publer',
                 'rodada seguinte achou o job concluído e NÃO criou segundo post')

        # ======================= Instagram (Trial Reels) =======================
        ap_ig = montar_parser()              # a linha de comando do publer_postar.py (--rede obrigatório)
        hoje = dt.datetime.now(FUSO).date()

        def dia(n):
            return (hoje + dt.timedelta(days=n)).isoformat()

        def postar_ig(*extra, chave_=CHAVE, saida=None):
            a_ = ap_ig.parse_args(['postar', *extra])
            if saida is None:
                return cmd_postar(a_, base=base, chave=chave_, usar_keychain=False)
            with contextlib.redirect_stdout(saida):
                return cmd_postar(a_, base=base, chave=chave_, usar_keychain=False)

        def item_ig(rid, legenda, est_ig=None, video_=None):
            it = item(rid, 'agendado_publer', legenda)          # TikTok já agendado: o Instagram não pode mexer
            if video_:
                it['video'] = video_
            it['estado']['instagram'] = est_ig or {'status': 'pendente'}
            return it

        def fila_ig(semana, *itens):
            filamod.salvar({'semana': semana, 'contas': {'tiktok': '@anadareconecta', 'instagram': '@anadareconecta'},
                            'ordem': 'intercalada', 'itens': list(itens)})

        def mp4_falso(nome, segundos, versao=0):
            """MP4 mínimo (ftyp + moov/mvhd + mdat) com a duração pedida, pra testar a leitura da duração."""
            escala = 1000
            if versao == 1:
                corpo = bytes([1, 0, 0, 0]) + struct.pack('>QQIQ', 0, 0, escala, int(segundos * escala))
            else:
                corpo = bytes([0, 0, 0, 0]) + struct.pack('>IIII', 0, 0, escala, int(segundos * escala))
            corpo += b'\0' * 80
            mvhd = struct.pack('>I4s', 8 + len(corpo), b'mvhd') + corpo
            moov = struct.pack('>I4s', 8 + len(mvhd), b'moov') + mvhd
            ftyp = struct.pack('>I4s4sI', 16, b'ftyp', b'isom', 512)
            dados = os.urandom(200 * 1024)
            mdat = struct.pack('>I4s', 8 + len(dados), b'mdat') + dados
            p_ = os.path.join(tmp.name, nome)
            with open(p_, 'wb') as fh:
                fh.write(ftyp + mdat + moov)                      # moov no fim, como sai de muito exportador
            return p_

        # 9) fluxo completo no Instagram com --intervalo
        print('9) Instagram: Trial Reel MANUAL, conta pelo nome, agenda por intervalo')
        fila_ig('SEMIG', item_ig('I1', 'Legenda I1 #harmonizacaofacial'), item_ig('I2', 'Legenda I2'),
                item_ig('I3', 'Legenda I3'))
        n0, u0 = len(srv['posts']), len(srv['uploads'])
        rc = postar_ig('SEMIG', '--rede', 'instagram', '--inicio', f'{dia(1)} 08:00', '--intervalo', '20',
                       '--por-dia', '21')
        g = estados('SEMIG', 'instagram')
        conferir(rc == 0 and len(srv['posts']) == n0 + 3 and len(srv['uploads']) == u0 + 3,
                 f'3 Trial Reels agendados (rc {rc}, {len(srv["posts"]) - n0} POSTs)')
        conferir([g[k].get('scheduled_at') for k in ('I1', 'I2', 'I3')] ==
                 [f'{dia(1)}T08:00:00-03:00', f'{dia(1)}T08:20:00-03:00', f'{dia(1)}T08:40:00-03:00'],
                 'horários 08:00, 08:20, 08:40 (de 20 em 20 min)')
        conferir(all(g[k].get('status') == 'agendado_publer' and g[k].get('conta_publer') == CONTA_IG
                     and g[k].get('trial_reel') == 'MANUAL' and g[k].get('post_id') for k in g),
                 'estado.instagram -> agendado_publer, conta Instagram, trial MANUAL e post_id gravados')
        conferir(all(v == {'status': 'agendado_publer'} for v in estados('SEMIG', 'tiktok').values()),
                 'rodada do Instagram não tocou no estado do TikTok')
        pi = srv['posts'][n0]['bulk']
        ig = pi['posts'][0]['networks'].get('instagram') or {}
        conferir(list(pi['posts'][0]['networks']) == ['instagram'] and pi['state'] == 'scheduled'
                 and ig.get('type') == 'video', 'payload: só networks.instagram, type video, bulk.state scheduled')
        conferir(ig.get('details') == {'type': 'reel', 'trial_reel': 'MANUAL'},
                 f'payload: details = {{type reel, trial_reel MANUAL}}, sem feed ({ig.get("details")})')
        m0 = (ig.get('media') or [{}])[0]
        conferir(set(m0) == {'id', 'type', 'thumbnails', 'default_thumbnail'} and m0.get('default_thumbnail') == 0
                 and len(m0.get('thumbnails') or []) == 3 and m0.get('id') == g['I1'].get('media_id'),
                 'payload: media com id do upload, thumbnails e default_thumbnail 0 (sem path)')
        conferir(ig.get('text') == 'Legenda I1 #harmonizacaofacial', 'payload: text = legenda da fila (com hashtags)')
        conferir(pi['posts'][0]['accounts'][0] == {'id': CONTA_IG, 'scheduled_at': f'{dia(1)}T08:00:00-03:00'},
                 'payload: conta Instagram achada pelo nome ("anadareconecta") e horário com fuso')
        e_ig = srv['estado_no_post'][n0] or {}
        conferir(e_ig.get('status') == 'agendando' and e_ig.get('conta_publer') == CONTA_IG,
                 'Instagram: item já estava "agendando" no disco quando o POST chegou')

        # 10) --intervalo: 21 por dia de 20 em 20 min; o resto vai pro dia seguinte no mesmo horário
        print('10) agenda por intervalo')
        hs = horarios_por_intervalo(parse_inicio(f'{dia(5)} 08:00'), 20, 21)
        conferir([h.strftime('%H:%M') for h in hs] == [f'{8 + k * 20 // 60:02d}:{k * 20 % 60:02d}' for k in range(21)]
                 and hs[-1].strftime('%H:%M') == '14:40', f'08:00, 08:20, …, 14:40 ({len(hs)} horários)')
        sl = gerar_horarios(parse_inicio(f'{dia(5)} 08:00'), hs, 23, dt.datetime.now(FUSO))
        conferir(sl[20].strftime('%d %H:%M') == parse_inicio(f'{dia(5)} 14:40').strftime('%d %H:%M')
                 and sl[21] == parse_inicio(f'{dia(6)} 08:00') and sl[22] == parse_inicio(f'{dia(6)} 08:20'),
                 'o 22º e o 23º vão pro dia seguinte às 08:00 e 08:20')
        try:
            horarios_por_intervalo(parse_inicio(f'{dia(5)} 20:00'), 20, 21)
            meia_noite = False
        except SystemExit:
            meia_noite = True
        conferir(meia_noite, '--intervalo que passaria da meia-noite é recusado')
        fila_ig('SEMIG2', item_ig('J1', 'Legenda J1'), item_ig('J2', 'Legenda J2'))
        a_ = ap_ig.parse_args(['postar', 'SEMIG2', '--rede', 'instagram', '--inicio', f'{dia(1)} 08:00',
                               '--intervalo', '20', '--por-dia', '21', '--simular'])
        conferir_opcoes(a_)
        a_.forcar = set()
        ini_ = parse_inicio(a_.inicio)
        hs_, pd_ = resolver_agenda(a_, ini_)
        pl_, _, _, info_ = planejar(filamod.carregar('SEMIG2'), a_, hs_, pd_, ini_)
        conferir([q.strftime('%H:%M') for _, q in pl_] == ['09:00', '09:20'] and len(info_['ocupados']) == 3,
                 'horários já agendados (08:00–08:40 da SEMIG) são pulados: a fila nova começa às 09:00')

        # 11) conta errada recusa
        print('11) Instagram: conta conferida')
        fila_ig('SEMIGCONTA', item_ig('K1', 'Legenda IG K1'))
        n0 = len(srv['uploads'])
        recusas = 0
        for conta_ in ('conta-ig-outra', CONTA):
            try:
                postar_ig('SEMIGCONTA', '--rede', 'instagram', '--conta', conta_, '--inicio', f'{dia(1)} 10:00')
            except SystemExit:
                recusas += 1
        conferir(recusas == 2 and len(srv['uploads']) == n0,
                 '--conta de outro nome (Instagram) e --conta de TikTok recusadas antes de subir vídeo')
        conferir(estados('SEMIGCONTA', 'instagram')['K1'] == {'status': 'pendente'}, 'K1 continua pendente')

        # 12) idempotência / duplicado igual ao TikTok
        print('12) Instagram: conferência no Publer antes de repetir')
        s1i = dt.datetime.combine(hoje + dt.timedelta(days=2), dt.time(15, 0), tzinfo=FUSO).isoformat(timespec='seconds')
        s2i = dt.datetime.combine(hoje + dt.timedelta(days=2), dt.time(16, 0), tzinfo=FUSO).isoformat(timespec='seconds')
        srv['publer'].append({'id': 'post-ig-antigo', 'account_id': CONTA_IG, 'scheduled_at': s1i,
                              'text': 'Legenda G1', 'network': 'instagram'})
        srv['jobs']['job-ig-velho'] = {'polls': 9, 'falha': True, 'rede': 'instagram', 'conta': CONTA_IG}
        fila_ig('SEMIGDUP',
                item_ig('G1', 'Legenda G1', {'status': 'agendando', 'scheduled_at': s1i, 'conta_publer': CONTA_IG}),
                item_ig('G2', 'Legenda G2', {'status': 'erro', 'etapa': 'agendar', 'scheduled_at': s2i,
                                             'conta_publer': CONTA_IG, 'mensagem': 'timed out'}),
                item_ig('G3', 'Legenda G3', {'status': 'erro', 'etapa': 'job', 'scheduled_at': s2i,
                                             'conta_publer': CONTA_IG, 'job_id': 'job-ig-velho'}))
        n0 = len(srv['posts'])
        rc = postar_ig('SEMIGDUP', '--rede', 'instagram', '--repetir-erros', '--inicio', f'{dia(1)} 08:00',
                       '--intervalo', '20', '--por-dia', '21')
        g = estados('SEMIGDUP', 'instagram')
        conferir(rc == 0 and len(srv['posts']) == n0 + 1, f'só G3 virou post novo ({len(srv["posts"]) - n0} POST)')
        conferir(g['G1'].get('status') == 'agendado_publer' and g['G1'].get('post_id') == 'post-ig-antigo',
                 'G1 "agendando" achado no Publer -> agendado_publer, sem repostar')
        conferir(g['G2'].get('status') == 'erro' and g['G2'].get('etapa') == 'agendar',
                 'G2 (erro no POST, não confirmado) ficou de fora mesmo com --repetir-erros')
        conferir(g['G3'].get('status') == 'agendado_publer', 'G3 (job recusado, conferido no Publer) repostado')
        n0 = len(srv['posts'])
        rc = postar_ig('SEMIGDUP', '--rede', 'instagram', '--forcar', 'G2', '--inicio', f'{dia(1)} 08:00',
                       '--intervalo', '20', '--por-dia', '21')
        conferir(rc == 0 and len(srv['posts']) == n0 + 1
                 and estados('SEMIGDUP', 'instagram')['G2'].get('status') == 'agendado_publer',
                 'G2 só saiu com --forcar G2')

        # 13) duração: > 90 s só avisa; validity.instagram.reel false para na etapa "midia"; < 3 s bloqueia
        print('13) Instagram: duração do vídeo')
        v152 = mp4_falso('longo152.mp4', 152)
        v152b = mp4_falso('longo152b.mp4', 152)
        v2 = mp4_falso('curto2.mp4', 2, versao=1)
        conferir(abs((duracao_video(v152) or 0) - 152) < 0.01 and abs((duracao_video(v2) or 0) - 2) < 0.01,
                 f'duração lida do mvhd v0 e v1 com moov no fim ({duracao_video(v152)} s, {duracao_video(v2)} s)')
        fila_ig('SEMIGDUR', item_ig('V1', 'Legenda V1', video_=v152))
        buf = io.StringIO()
        n0 = len(srv['posts'])
        rc = postar_ig('SEMIGDUR', '--rede', 'instagram', '--inicio', f'{dia(3)} 08:00', '--intervalo', '20',
                       '--por-dia', '21', saida=buf)
        txt = buf.getvalue()
        conferir(rc == 0 and len(srv['posts']) == n0 + 1 and 'aviso (não bloqueia)' in txt and '152 s' in txt
                 and estados('SEMIGDUR', 'instagram')['V1'].get('status') == 'agendado_publer',
                 'vídeo de 152 s: avisou (doc do Publer x Meta) e agendou mesmo assim')
        fila_ig('SEMIGVAL', item_ig('W1', 'Legenda W1', video_=v152b))
        srv['validade_ig'] = False
        n0 = len(srv['posts'])
        rc = postar_ig('SEMIGVAL', '--rede', 'instagram', '--inicio', f'{dia(3)} 09:00', '--intervalo', '20',
                       '--por-dia', '21')
        srv['validade_ig'] = True
        w1 = estados('SEMIGVAL', 'instagram')['W1']
        conferir(rc == 1 and len(srv['posts']) == n0 and w1.get('status') == 'erro' and w1.get('etapa') == 'midia'
                 and 'validity.instagram' in w1.get('mensagem', '') and '90 s' in w1.get('mensagem', ''),
                 f'validity.instagram.reel false: erro na etapa "midia", sem POST ({w1.get("etapa")})')
        rc = postar_ig('SEMIGVAL', '--rede', 'instagram', '--repetir-erros', '--inicio', f'{dia(3)} 09:00',
                       '--intervalo', '20', '--por-dia', '21')
        conferir(rc == 0 and estados('SEMIGVAL', 'instagram')['W1'].get('status') == 'agendado_publer',
                 'o mesmo item sai com --repetir-erros quando o Publer aceita')
        fila_ig('SEMIGCURTO', item_ig('X1', 'Legenda X1', video_=v2))
        n0 = len(srv['uploads'])
        rc = postar_ig('SEMIGCURTO', '--rede', 'instagram', '--inicio', f'{dia(3)} 10:00', '--intervalo', '20',
                       '--por-dia', '21', saida=io.StringIO())
        conferir(rc == 1 and len(srv['uploads']) == n0, 'vídeo de 2 s (abaixo dos 3 s da Meta) barrado antes do upload')

        # 14) segunda postada pelo mLabs nunca entra no plano
        print('14) Instagram: postado_manual (segunda pelo mLabs) nunca sai')
        manual_ig = {'status': 'postado_manual', 'obs': 'postado pelo mLabs em 05/10'}
        fila_ig('SEMSEG', *[item_ig(f'M{k}', f'Legenda M{k}', dict(manual_ig)) for k in range(1, 4)])
        n0, u0 = len(srv['posts']), len(srv['uploads'])
        rc = postar_ig('SEMSEG', '--rede', 'instagram', '--repetir-erros', '--inicio', f'{dia(1)} 08:00',
                       '--intervalo', '20', '--por-dia', '21', saida=io.StringIO())
        conferir(rc == 0 and len(srv['posts']) == n0 and len(srv['uploads']) == u0
                 and all(v == manual_ig for v in estados('SEMSEG', 'instagram').values()),
                 'nenhum upload/POST e o postado_manual ficou intocado')
        try:
            postar_ig('SEMSEG', '--rede', 'instagram', '--forcar', 'M1', '--inicio', f'{dia(1)} 08:00')
            forcou = True
        except SystemExit:
            forcou = False
        conferir(not forcou and len(srv['uploads']) == u0, '--forcar em item postado_manual é recusado')

        # 15) --trial explícito e opções de outra rede
        print('15) opções por rede')
        fila_ig('SEMIGSS', item_ig('Y1', 'Legenda Y1'))
        buf = io.StringIO()
        n0 = len(srv['posts'])
        rc = postar_ig('SEMIGSS', '--rede', 'instagram', '--trial', 'SS_PERFORMANCE', '--inicio', f'{dia(4)} 08:00',
                       saida=buf)
        d_ = ((srv['posts'][n0]['bulk']['posts'][0]['networks'].get('instagram') or {}).get('details')
              if len(srv['posts']) > n0 else None)
        conferir(rc == 0 and d_ == {'type': 'reel', 'trial_reel': 'SS_PERFORMANCE'} and 'ATENÇÃO' in buf.getvalue(),
                 '--trial SS_PERFORMANCE só quando passado, e com aviso')
        recusas = 0
        for extra_ in (['--rede', 'tiktok', '--trial', 'MANUAL'], ['--rede', 'instagram', '--sem-duet'],
                       ['--rede', 'instagram', '--privacidade', 'SELF_ONLY']):
            try:
                postar_ig('SEMIGSS', *extra_, '--inicio', f'{dia(4)} 08:00', '--simular')
            except SystemExit:
                recusas += 1
        conferir(recusas == 3, '--trial no TikTok e opções do TikTok no Instagram são recusadas')

        # 16) teto de 24 h corridas (Publer Business: 25 Instagram Posts & Reels)
        print('16) teto de 24 h')
        d10 = hoje + dt.timedelta(days=10)
        cheios = [item_ig(f'Z{k:02d}', f'Legenda Z{k}', {
            'status': 'agendado_publer', 'conta_publer': CONTA_IG,
            'scheduled_at': (dt.datetime.combine(d10, dt.time(8, 0), tzinfo=FUSO)
                             + dt.timedelta(minutes=20 * k)).isoformat(timespec='seconds')}) for k in range(21)]
        fila_ig('SEMTETO1', *cheios)
        fila_ig('SEMTETO2', *[item_ig(f'N{k}', f'Legenda N{k}') for k in range(5)])
        n0 = len(srv['uploads'])
        buf = io.StringIO()
        rc = postar_ig('SEMTETO2', '--rede', 'instagram', '--inicio', f'{(d10 + dt.timedelta(days=1)).isoformat()} 06:00',
                       '--intervalo', '20', '--por-dia', '21', saida=buf)
        conferir(rc == 1 and len(srv['uploads']) == n0 and 'janela de 24 h' in buf.getvalue(),
                 'dia seguinte começando 06:00 passaria de 25 em 24 h: barrado antes do upload')
        a_ = ap_ig.parse_args(['postar', 'SEMTETO2', '--rede', 'instagram', '--inicio',
                               f'{(d10 + dt.timedelta(days=1)).isoformat()} 08:00', '--intervalo', '20', '--por-dia', '21'])
        conferir_opcoes(a_)
        a_.forcar = set()
        ini_ = parse_inicio(a_.inicio)
        hs_, pd_ = resolver_agenda(a_, ini_)
        _, _, _, info_ = planejar(filamod.carregar('SEMTETO2'), a_, hs_, pd_, ini_)
        conferir(info_['estouro'] is None, 'dia seguinte no mesmo horário (08:00) cabe: 21 por janela de 24 h')
        try:
            postar_ig('SEMTETO2', '--rede', 'instagram', '--inicio', f'{dia(12)} 08:00', '--intervalo', '20',
                      '--por-dia', '26', '--simular')
            passou = True
        except SystemExit:
            passou = False
        conferir(not passou, '--por-dia 26 recusado (limite 25/24 h do Instagram no Publer Business)')

        # 17) simulação sem chave: monta o plano só da fila
        print('17) simulação sem chave no Keychain')
        fila_ig('SEMIGSIM', *[item_ig(f'Q{k}', f'Legenda Q{k}') for k in range(3)])
        antes_reqs = srv['reqs']
        with open(filamod.caminho_fila('SEMIGSIM'), 'rb') as fh:
            antes = hashlib.sha256(fh.read()).hexdigest()
        buf = io.StringIO()
        rc = postar_ig('SEMIGSIM', '--rede', 'instagram', '--inicio', f'{dia(7)} 08:00', '--intervalo', '20',
                       '--por-dia', '21', '--simular', chave_=None, saida=buf)
        with open(filamod.caminho_fila('SEMIGSIM'), 'rb') as fh:
            depois = hashlib.sha256(fh.read()).hexdigest()
        conferir(rc == 0 and srv['reqs'] == antes_reqs and antes == depois and 'NÃO conferida' in buf.getvalue()
                 and '08:40' in buf.getvalue(), 'sem chave: mostrou o plano, sem requisição e sem mexer na fila')

        # 18) fila.py: migração sem perda (rede que falta entra como pendente; montar preserva o resto)
        print('18) fila.py: migração pro Instagram')
        destino = os.path.join(tmp.name, 'destino')
        for letra in ('A', 'B'):
            pasta_ = os.path.join(destino, 'orgânico', f'[26] [41] [ORG] VD001_{letra}')
            os.makedirs(pasta_)
            for nome_, conteudo in ((f'[26] [41] [ORG] VD001_{letra}.mp4', 'x'), ('título.txt', f'T {letra}'),
                                    ('legenda.txt', f'L {letra}')):
                with open(os.path.join(pasta_, nome_), 'w', encoding='utf-8') as fh:
                    fh.write(conteudo)
        plano_ = os.path.join(tmp.name, 'plano_mig.json')
        with open(plano_, 'w', encoding='utf-8') as fh:
            json.dump({'fila': 'SEMMIG', 'destino': destino, 'videos': [{'vd': 'VD001', 'hooks': ['A', 'B'],
                                                                         'shortcode': 'X'}],
                       'variantes': [{'id': 'ORG', 'subpasta': 'orgânico', 'prefixo': '[26] [41] [ORG] '}]}, fh)
        velho = {'status': 'agendado_publer', 'post_id': 'p9', 'scheduled_at': '2026-10-06T09:00:00-03:00'}
        with open(filamod.caminho_fila('SEMMIG'), 'w', encoding='utf-8') as fh:   # fila antiga, sem "instagram"
            json.dump({'semana': 'SEMMIG', 'contas': {'tiktok': '@anadareconecta'}, 'ordem': 'intercalada',
                       'itens': [{'id': 'VD001_A', 'legenda': 'L A', 'estado': {
                           'tiktok': velho, 'youtube': {'status': 'postado_manual'}}}]}, fh)
        carregada = filamod.carregar('SEMMIG')['itens'][0]['estado']
        conferir(carregada == {'tiktok': velho, 'youtube': {'status': 'postado_manual'},
                               'instagram': {'status': 'pendente'}}, 'carregar: instagram ausente entra como pendente')
        with contextlib.redirect_stdout(io.StringIO()):
            filamod.montar(plano_)
        fm = filamod.carregar('SEMMIG')
        e_ = {i['id']: i['estado'] for i in fm['itens']}
        conferir(e_['VD001_A'] == {'tiktok': velho, 'youtube': {'status': 'postado_manual'},
                                   'instagram': {'status': 'pendente'}}
                 and e_['VD001_B'] == {r: {'status': 'pendente'} for r in filamod.REDES}
                 and fm.get('contas') == {'tiktok': '@anadareconecta'} and fm.get('ordem') == 'intercalada',
                 'montar: preserva estados e metadados, acrescenta instagram pendente')

        # ======================= revisão (achados dos 3 revisores) =======================
        def saida_de(fn, *a, **k):
            """Roda fn com stdout/stderr capturados; devolve (retorno ou 'exit:<código>', texto)."""
            buf_ = io.StringIO()
            with contextlib.redirect_stdout(buf_), contextlib.redirect_stderr(buf_):
                try:
                    r_ = fn(*a, **k)
                except SystemExit as e_:
                    r_ = f'exit:{e_.code}'
            return r_, buf_.getvalue()

        def ig(semana, *extra, chave_=CHAVE):
            return saida_de(postar_ig, semana, '--rede', 'instagram', *extra, chave_=chave_)

        def iso(d, hhmm):
            h_, m_ = map(int, hhmm.split(':'))
            return dt.datetime.combine(hoje + dt.timedelta(days=d), dt.time(h_, m_), tzinfo=FUSO).isoformat(timespec='seconds')

        # 19) workspace/conta travados: o lote para no 1º e nada vira agendado_publer em silêncio
        print('19) post travado no Publer (plan.locked, scheduled_reauth, filtro de estado)')
        conferir(plano_travado(ler_job({'status': 'complete', 'payload': {'failures': {}}, 'plan': {'locked': True}})[3])
                 and plano_travado(ler_job({'success': True, 'data': {'status': 'complete', 'result': {
                     'status': 'complete', 'payload': {}, 'plan': {'locked': True}}}})[3])
                 and not plano_travado(ler_job({'status': 'complete', 'payload': {}, 'plan': {}})[3]),
                 'ler_job lê plan.locked nos dois envelopes da doc')
        fila_ig('SEMTRAVADO', *[item_ig(f'B{k}', f'Legenda B{k}') for k in range(1, 4)])
        srv.update(ws_travado=True, estado_novo='scheduled_locked')
        n0, u0 = len(srv['posts']), len(srv['uploads'])
        rc, txt = ig('SEMTRAVADO', '--inicio', f'{dia(14)} 08:00', '--intervalo', '20', '--por-dia', '21')
        g = estados('SEMTRAVADO', 'instagram')
        conferir(rc == 1 and len(srv['posts']) == n0 + 1 and g['B1'].get('status') == TRAVADO
                 and 'plan.locked' in g['B1'].get('motivo', '') and g['B1'].get('post_id')
                 and g['B2'] == {'status': 'pendente'} and 'TRAVADO' in txt,
                 f'workspace travado: B1 -> {TRAVADO} (com post_id e motivo), lote parou no 1º ({g["B1"].get("status")})')
        u1 = len(srv['uploads'])
        rc, txt = ig('SEMTRAVADO', '--inicio', f'{dia(14)} 08:00', '--intervalo', '20', '--por-dia', '21')
        conferir(rc == 1 and len(srv['uploads']) == u1 and len(srv['posts']) == n0 + 1 and 'Nada foi enviado' in txt
                 and estados('SEMTRAVADO', 'instagram')['B1'].get('status') == TRAVADO,
                 'ainda travado: a rodada seguinte confere antes e não sobe nada')
        srv.update(ws_travado=False, estado_novo='scheduled')
        for p_ in srv['publer']:
            if p_.get('state') == 'scheduled_locked':
                p_['state'] = 'scheduled'                       # destravou no Publer
        rc, txt = ig('SEMTRAVADO', '--inicio', f'{dia(14)} 08:00', '--intervalo', '20', '--por-dia', '21')
        g = estados('SEMTRAVADO', 'instagram')
        conferir(rc == 0 and len(srv['posts']) == n0 + 3 and all(v.get('status') == 'agendado_publer' for v in g.values())
                 and 'motivo' not in g['B1'] and g['B2'].get('scheduled_at') == iso(14, '08:20'),
                 'destravado: B1 conciliado -> agendado_publer, B2 e B3 saem (08:20, 08:40), sem repostar B1')
        fila_ig('SEMREAUTH', item_ig('E1', 'Legenda E1'), item_ig('E2', 'Legenda E2'))
        srv.update(estado_novo='scheduled_reauth', filtro_ignorado=True)   # só o estado do post acusa
        n0 = len(srv['posts'])
        rc, txt = ig('SEMREAUTH', '--inicio', f'{dia(15)} 08:00', '--intervalo', '20', '--por-dia', '21')
        srv['filtro_ignorado'] = False
        g = estados('SEMREAUTH', 'instagram')
        conferir(rc == 1 and len(srv['posts']) == n0 + 1 and g['E1'].get('status') == TRAVADO
                 and 'scheduled_reauth' in g['E1'].get('motivo', '') and g['E2'] == {'status': 'pendente'},
                 'post em scheduled_reauth (conta pedindo reautorização): travado e o lote para')
        fila_ig('SEMPEND', item_ig('H1', 'Legenda H1'))
        srv.update(estado_novo='scheduled_pending', resumo_generico=True)
        rc, txt = ig('SEMPEND', '--inicio', f'{dia(15)} 10:00', '--intervalo', '20', '--por-dia', '21')
        h1 = estados('SEMPEND', 'instagram')['H1']
        conferir(rc == 1 and h1.get('status') == TRAVADO and 'scheduled_pending' in h1.get('motivo', ''),
                 'resumo do post diz só "scheduled", mas o filtro scheduled_pending acha: travado')
        fila_ig('SEMFILTRO', item_ig('H2', 'Legenda H2'))
        srv.update(estado_novo='scheduled', resumo_generico=False, filtro_ignorado=True)
        rc, txt = ig('SEMFILTRO', '--inicio', f'{dia(15)} 12:00', '--intervalo', '20', '--por-dia', '21')
        srv['filtro_ignorado'] = False
        conferir(rc == 0 and estados('SEMFILTRO', 'instagram')['H2'].get('status') == 'agendado_publer'
                 and 'filtro ignorado' in txt,
                 'controle: servidor que ignora o filtro de estado não vira falso "travado"')

        # 20) agenda do Publer fora das filas ocupa horário e conta no teto
        print('20) posts agendados no Publer por fora das filas')
        srv['publer'].append({'id': 'post-do-app', 'account_id': CONTA_IG, 'scheduled_at': iso(20, '08:00'),
                              'text': 'post feito no app do Publer', 'network': 'instagram'})
        srv['publer'].append({'id': 'post-outra-conta', 'account_id': 'conta-ig-outra', 'scheduled_at': iso(20, '08:20'),
                              'text': 'outra conta', 'network': 'instagram'})
        fila_ig('SEMEXT', item_ig('O1', 'Legenda O1'), item_ig('O2', 'Legenda O2'))
        rc, txt = ig('SEMEXT', '--inicio', f'{dia(20)} 08:00', '--intervalo', '20', '--por-dia', '21')
        g = estados('SEMEXT', 'instagram')
        conferir(rc == 0 and [g['O1'].get('scheduled_at'), g['O2'].get('scheduled_at')] == [iso(20, '08:20'), iso(20, '08:40')]
                 and 'nas filas ou no Publer' in txt,
                 '08:00 (post do app, fora das filas) pulado; post de outra conta não ocupa: 08:20 e 08:40')
        fila_ig('SEMEXT2', item_ig('O3', 'Legenda O3'))
        r0 = srv['reqs']
        rc, txt = ig('SEMEXT2', '--inicio', f'{dia(20)} 08:00', '--intervalo', '20', '--por-dia', '21', '--simular')
        conferir(rc == 0 and 'plano: de' in txt and 'O3' in txt and dia(20)[8:] + '/' in txt,
                 'simulação com chave mostra o plano')
        conferir('nas filas ou no Publer' in txt and '[tipo: business]' in txt and srv['reqs'] > r0
                 and estados('SEMEXT2', 'instagram')['O3'] == {'status': 'pendente'},
                 'simulação com chave lê a agenda da conta no Publer (só GET) e mostra o tipo da conta')
        class PaginasFalsas:                                      # GET /posts sem total_pages
            def __init__(self, ignora_page):
                self.ignora_page, self.chamadas = ignora_page, 0

            def json(self, metodo, caminho, consulta=None, **_):
                self.chamadas += 1
                pg = 0 if self.ignora_page else consulta['page']
                return {'posts': [{'id': f'p{pg}-{i}', 'scheduled_at': iso(40, '08:00')} for i in range(2)] if pg < 3 else []}
        c1_, c2_ = PaginasFalsas(False), PaginasFalsas(True)
        n1_ = sum(len(x) for x in paginas_posts(c1_, {}))
        n2_ = sum(len(x) for x in paginas_posts(c2_, {}))
        conferir(n1_ == 6 and c1_.chamadas == 4 and n2_ == 2 and c2_.chamadas == 2,
                 f'GET /posts sem total_pages: lê até a página vazia ({n1_} posts) e não entra em laço se o '
                 f'servidor ignora "page" ({c2_.chamadas} chamadas)')
        for k in range(5):
            srv['publer'].append({'id': f'post-app-{k}', 'account_id': CONTA_IG, 'network': 'instagram',
                                  'scheduled_at': iso(22, f'07:{k * 10:02d}'), 'text': f'app {k}'})
        fila_ig('SEMEXT3', *[item_ig(f'P{k:02d}', f'Legenda P{k}') for k in range(21)])
        u0 = len(srv['uploads'])
        rc, txt = ig('SEMEXT3', '--inicio', f'{dia(22)} 08:00', '--intervalo', '20', '--por-dia', '21')
        conferir(rc == 1 and len(srv['uploads']) == u0 and 'janela de 24 h' in txt and '26 posts' in txt,
                 '5 posts do app + 21 da fila = 26 em 24 h: barrado antes do upload')

        # 21) tipo da conta (doc: Instagram só "business" na API)
        print('21) tipo da conta Instagram')
        fila_ig('SEMTIPO', item_ig('A1', 'Legenda A1'))
        srv['tipo_ig'] = 'profile'
        u0 = len(srv['uploads'])
        rc, txt = ig('SEMTIPO', '--inicio', f'{dia(23)} 08:00', '--intervalo', '20', '--por-dia', '21')
        srv['tipo_ig'] = 'business'
        conferir(rc == 1 and len(srv['uploads']) == u0 and 'tipo "profile"' in txt
                 and estados('SEMTIPO', 'instagram')['A1'] == {'status': 'pendente'},
                 'conta Instagram do tipo "profile" recusada antes de subir vídeo')
        rc, txt = saida_de(cmd_contas, ap_ig.parse_args(['contas']), base=base, chave=CHAVE)
        conferir(rc == 0 and '[tipo: business]' in txt, 'comando "contas" mostra o tipo da conta')

        # 22) validity do GET /media (vídeo já processado) também barra
        print('22) validity do vídeo processado (GET /media/{id})')
        fila_ig('SEMVALMID', item_ig('U1', 'Legenda U1'))
        srv['validade_ig_midia'] = False
        n0 = len(srv['posts'])
        rc, txt = ig('SEMVALMID', '--inicio', f'{dia(23)} 10:00', '--intervalo', '20', '--por-dia', '21')
        srv['validade_ig_midia'] = True
        u1_ = estados('SEMVALMID', 'instagram')['U1']
        conferir(rc == 1 and len(srv['posts']) == n0 and u1_.get('status') == 'erro' and u1_.get('etapa') == 'midia'
                 and 'validity.instagram' in u1_.get('mensagem', ''),
                 'upload dizia reel true, o GET /media processado diz false: erro na etapa "midia", sem POST')

        # 23) fila.py montar com disco fora / vídeo sumido / plano mudado: nada some
        print('23) fila.py montar sem perder estado')
        destino2 = os.path.join(tmp.name, 'destino2')

        def criar_pasta(vd, letra):
            pasta_ = os.path.join(destino2, 'orgânico', f'[26] [41] [ORG] {vd}_{letra}')
            os.makedirs(pasta_, exist_ok=True)
            for nome_, conteudo in ((f'[26] [41] [ORG] {vd}_{letra}.mp4', 'x'), ('título.txt', 'T'),
                                    ('legenda.txt', f'L {vd} {letra}')):
                with open(os.path.join(pasta_, nome_), 'w', encoding='utf-8') as fh:
                    fh.write(conteudo)
            return pasta_

        def plano_falta(videos):
            p_ = os.path.join(tmp.name, 'plano_falta.json')
            with open(p_, 'w', encoding='utf-8') as fh:
                json.dump({'fila': 'SEMFALTA', 'destino': destino2,
                           'videos': [{'vd': vd, 'hooks': hk, 'shortcode': 'X'} for vd, hk in videos],
                           'variantes': [{'id': 'ORG', 'subpasta': 'orgânico', 'prefixo': '[26] [41] [ORG] '}]}, fh)
            return p_

        pa = criar_pasta('VD001', 'A')
        criar_pasta('VD001', 'B')
        criar_pasta('VD002', 'A')
        pl_ = plano_falta([('VD001', ['A', 'B']), ('VD002', ['A'])])
        saida_de(filamod.montar, pl_)
        ff = filamod.carregar('SEMFALTA')
        ff['contas'] = {'instagram': '@anadareconecta'}
        for it_ in ff['itens']:
            if it_['id'] == 'VD001_A':
                it_['estado']['instagram'] = {'status': 'postado_manual', 'obs': 'mLabs'}
                it_['estado']['tiktok'] = {'status': 'agendado_publer', 'post_id': 'pX'}
            if it_['id'] == 'VD002_A':
                it_['estado']['tiktok'] = {'status': 'agendado_publer', 'post_id': 'pY'}
        filamod.salvar(ff)
        os.rename(pa, pa + '.fora')                               # vídeo sumiu (pasta renomeada)
        r_, txt = saida_de(filamod.montar, pl_)
        e_ = {i['id']: i for i in filamod.carregar('SEMFALTA')['itens']}
        conferir(set(e_) == {'VD001_A', 'VD001_B', 'VD002_A'} and e_['VD001_A'].get('faltando') is True
                 and e_['VD001_A']['estado']['instagram'] == {'status': 'postado_manual', 'obs': 'mLabs'}
                 and e_['VD001_A']['estado']['tiktok'].get('status') == 'agendado_publer' and 'faltando' in txt,
                 'vídeo sumido: o item fica na fila com o estado antigo, marcado "faltando"')
        org = os.path.join(destino2, 'orgânico')
        os.rename(org, org + '.fora')                             # disco inteiro "desmontado"
        with open(filamod.caminho_fila('SEMFALTA'), 'rb') as fh:
            antes = hashlib.sha256(fh.read()).hexdigest()
        r_, txt = saida_de(filamod.montar, pl_)
        with open(filamod.caminho_fila('SEMFALTA'), 'rb') as fh:
            depois = hashlib.sha256(fh.read()).hexdigest()
        conferir(str(r_).startswith('exit:') and 'disco está montado' in str(r_) and antes == depois,
                 'nenhum vídeo achado: montar para sem gravar (a fila fica igual)')
        os.rename(org + '.fora', org)
        os.rename(pa + '.fora', pa)
        saida_de(filamod.montar, pl_)
        e_ = {i['id']: i for i in filamod.carregar('SEMFALTA')['itens']}
        conferir('faltando' not in e_['VD001_A'] and e_['VD001_A']['estado']['instagram'].get('status') == 'postado_manual',
                 'disco de volta: o item volta normal, com o estado preservado')
        pl2_ = plano_falta([('VD001', ['A'])])                    # o plano novo tirou VD001_B e VD002_A
        r_, txt = saida_de(filamod.montar, pl2_)
        e_ = {i['id']: i for i in filamod.carregar('SEMFALTA')['itens']}
        conferir(set(e_) == {'VD001_A', 'VD002_A'} and e_['VD002_A'].get('fora_do_plano') is True
                 and e_['VD002_A']['estado']['tiktok'].get('status') == 'agendado_publer',
                 'plano mudou: item que já saiu fica (fora_do_plano); o que só estava pendente sai')
        a_ = ap_ig.parse_args(['postar', 'SEMFALTA', '--rede', 'instagram', '--inicio', f'{dia(23)} 12:00'])
        a_.forcar = set()
        sel_, pul_, _ = selecionar(filamod.carregar('SEMFALTA')['itens'], a_)
        conferir([i['id'] for i in sel_] == [] and pul_ == {'fora_do_plano': 1, 'postado_manual': 1},
                 f'item fora_do_plano não é selecionado pro Instagram ({pul_})')

        # 24) trava também no fila.py; registro do POST nunca se perde
        print('24) trava no fila.py e registro do POST')
        tv_ = travar_fila('SEMFALTA')
        with open(filamod.caminho_fila('SEMFALTA'), 'rb') as fh:
            antes = hashlib.sha256(fh.read()).hexdigest()
        r1_, _ = saida_de(filamod.montar, pl2_)
        r2_, _ = saida_de(filamod.intercalar, 'SEMFALTA')
        os.close(tv_)
        with open(filamod.caminho_fila('SEMFALTA'), 'rb') as fh:
            depois = hashlib.sha256(fh.read()).hexdigest()
        conferir(str(r1_).startswith('exit:') and str(r2_).startswith('exit:') and 'rodada publicando' in str(r1_)
                 and antes == depois, 'montar e intercalar recusam com a fila travada por uma rodada, sem gravar')
        fila_ig('SEMVELHA', item_ig('R1', 'Legenda R1'))

        def copia_velha(texto, rede):                             # alguém grava uma cópia velha da fila por cima
            if texto == 'Legenda R1':
                fv = filamod.carregar('SEMVELHA')
                fv['itens'][0]['estado'][rede] = {'status': 'pendente'}
                filamod.salvar(fv)
        srv['ao_post'] = copia_velha
        n0 = len(srv['posts'])
        rc, txt = ig('SEMVELHA', '--inicio', f'{dia(24)} 08:00', '--intervalo', '20', '--por-dia', '21')
        srv['ao_post'] = None
        r1e = estados('SEMVELHA', 'instagram')['R1']
        with open(os.path.join(filamod.FILAS, 'SEMVELHA.posts.log'), encoding='utf-8') as fh:
            diario = [json.loads(l_) for l_ in fh if l_.strip()]
        conferir(rc == 1 and len(srv['posts']) == n0 + 1 and r1e.get('status') == 'agendando' and r1e.get('job_id')
                 and [d_['evento'] for d_ in diario] == ['antes_do_post', 'job_recebido'],
                 'fila voltou pra "pendente" depois do POST: registro regravado ("agendando" + job) e diário com o POST')
        rc, txt = ig('SEMVELHA', '--inicio', f'{dia(24)} 08:00', '--intervalo', '20', '--por-dia', '21')
        conferir(rc == 0 and len(srv['posts']) == n0 + 1
                 and estados('SEMVELHA', 'instagram')['R1'].get('status') == 'agendado_publer',
                 'rodada seguinte conciliou R1 sem criar segundo post')

        # 25) --forcar não passa por cima de job ainda rodando; tentativa anterior fica guardada
        print('25) --forcar com job em andamento')
        srv['jobs']['job-lento'] = {'polls': 0, 'falha': False, 'rede': 'instagram', 'conta': CONTA_IG, 'lento': True}
        lento = {'status': 'erro', 'etapa': 'job', 'job_id': 'job-lento', 'scheduled_at': iso(25, '08:00'),
                 'conta_publer': CONTA_IG, 'mensagem': 'o job não terminou em 10 min'}
        velho_f2 = {'status': 'erro', 'etapa': 'agendar', 'scheduled_at': iso(25, '09:00'), 'conta_publer': CONTA_IG,
                    'mensagem': 'timed out', 'media_id': 'm-velha'}
        fila_ig('SEMLENTO', item_ig('F1', 'Legenda F1', dict(lento)), item_ig('F2', 'Legenda F2', dict(velho_f2)))
        n0 = len(srv['posts'])
        rc, txt = ig('SEMLENTO', '--forcar', 'F1,F2', '--inicio', f'{dia(25)} 08:00', '--intervalo', '20',
                     '--por-dia', '21')
        g = estados('SEMLENTO', 'instagram')
        conferir(len(srv['posts']) == n0 + 1 and g['F1'] == lento and '--forcar F1 recusado' in txt,
                 'job ainda rodando: --forcar F1 recusado, sem POST e sem mexer no registro')
        ant = (g['F2'].get('anteriores') or [{}])[-1]
        conferir(rc == 0 and g['F2'].get('status') == 'agendado_publer' and ant.get('scheduled_at') == velho_f2['scheduled_at']
                 and ant.get('media_id') == 'm-velha' and ant.get('etapa') == 'agendar',
                 'F2 repostado com --forcar e a tentativa anterior guardada em "anteriores"')

        # 26) estado malformado não vira pendente
        print('26) estado malformado na fila')
        malformados = 0
        for est_ in ('"postado_manual"', '{"obs": "postado pelo mLabs"}', None):
            with open(filamod.caminho_fila('SEMMAL'), 'w', encoding='utf-8') as fh:
                estado_txt = ('null' if est_ is None else
                              '{"tiktok": {"status": "pendente"}, "youtube": {"status": "pendente"}, "instagram": ' + est_ + '}')
                fh.write('{"semana": "SEMMAL", "contas": {"instagram": "@anadareconecta"}, "itens": [{"id": "M1", '
                         '"video": "x", "legenda": "L", "estado": ' + estado_txt + '}]}')
            r_, _ = saida_de(filamod.carregar, 'SEMMAL')
            malformados += str(r_).startswith('exit:') and 'malformado' in str(r_)
        u0 = len(srv['uploads'])
        r_, _ = ig('SEMMAL', '--inicio', f'{dia(26)} 08:00', '--intervalo', '20', '--por-dia', '21')
        conferir(malformados == 3 and str(r_).startswith('exit:') and len(srv['uploads']) == u0,
                 'string, objeto sem "status" e "estado": null barram a fila (nada vira pendente, nada sobe)')
        os.unlink(filamod.caminho_fila('SEMMAL'))

        # 27) --forcar volta pro próprio horário
        print('27) --forcar volta pro horário original')
        fila_ig('SEMVOLTA',
                item_ig('X1', 'Legenda X1', {'status': 'agendado_publer', 'scheduled_at': iso(27, '08:00'), 'conta_publer': CONTA_IG}),
                item_ig('X2', 'Legenda X2', {'status': 'erro', 'etapa': 'agendar', 'scheduled_at': iso(27, '08:20'),
                                              'conta_publer': CONTA_IG, 'mensagem': 'timed out'}),
                item_ig('X3', 'Legenda X3', {'status': 'agendado_publer', 'scheduled_at': iso(27, '08:40'), 'conta_publer': CONTA_IG}))
        rc, txt = ig('SEMVOLTA', '--forcar', 'X2', '--inicio', f'{dia(27)} 08:00', '--intervalo', '20', '--por-dia', '21')
        conferir(rc == 0 and estados('SEMVOLTA', 'instagram')['X2'].get('scheduled_at') == iso(27, '08:20'),
                 'X2 forçado volta pras 08:20 (o horário antigo dele não conta como ocupado)')

        # 28) uma rodada por rede
        print('28) trava por rede')
        fila_ig('SEMREDE', item_ig('Q9', 'Legenda Q9'))
        outra = travar_rede('instagram', 'SEMOUTRA')
        u0 = len(srv['uploads'])
        r_, txt = ig('SEMREDE', '--inicio', f'{dia(28)} 08:00', '--intervalo', '20', '--por-dia', '21')
        os.close(outra)
        conferir(str(r_).startswith('exit:') and 'rodada do Instagram' in str(r_) and len(srv['uploads']) == u0,
                 'segunda rodada do Instagram (outra fila) barrada pela trava da rede, sem upload')
        r_, txt = saida_de(postar, 'SEMSINAL', '--inicio', f'{amanha} 09:00', '--simular', '--conta', 'X')
        conferir(r_ == 0, 'a trava do Instagram não bloqueia simulação do TikTok')

        # 29) --inicio que já passou: o plano avisa; mensagens que ensinam o uso certo
        print('29) --inicio no passado e mensagens')
        fila_ig('SEMPASSADO', *[item_ig(f'S{k}', f'Legenda S{k}') for k in range(3)])
        # desde a revisão do Fable (06/10): no modo intervalo a grade anda pra frente no MESMO dia (nada vai pra amanhã)
        r_, txt = ig('SEMPASSADO', '--inicio', f'{hoje.isoformat()} 00:00', '--intervalo', '2', '--por-dia', '21',
                     '--simular', chave_=None)
        tarde = dt.datetime.now(FUSO).hour == 23 and dt.datetime.now(FUSO).minute >= 20   # a grade passaria da meia-noite
        conferir(tarde or (r_ == 0 and 'mesmo dia, mesmo intervalo' in txt and 'plano: de' in txt
                           and 'caem num dia depois' not in txt),
                 '--inicio no passado com --intervalo: a grade anda pra frente no mesmo dia e avisa onde começa')
        try:
            garantir_futuro(dt.datetime.now(FUSO) - dt.timedelta(hours=1), 'teste')
            msg_ = ''
        except HorarioPassou as e_:
            msg_ = str(e_)
        conferir('MESMO comando' in msg_, 'HorarioPassou manda rodar o mesmo comando (não mudar o --inicio)')
        a_ = ap_ig.parse_args(['postar', 'SEMPASSADO', '--rede', 'instagram', '--inicio', f'{dia(29)} 08:00',
                               '--por-dia', '21'])
        conferir_opcoes(a_)
        r_, _ = saida_de(resolver_agenda, a_, parse_inicio(a_.inicio))
        conferir('--intervalo 20 --por-dia 21' in str(r_), '--por-dia 21 sem --intervalo sugere "--intervalo 20 --por-dia 21"')

        # 30) cobertura: margem, rodada cheia de 21, --de/--ate/--max, linha de comando
        print('30) margem, rodada de 21, recorte e linha de comando')
        fila_ig('SEMMARGEM', item_ig('G7', 'Legenda G7'))
        u0, n0 = len(srv['uploads']), len(srv['posts'])
        margem_original = MARGEM_POST
        try:
            globals()['MARGEM_POST'] = dt.timedelta(days=400)
            rc, txt = ig('SEMMARGEM', '--inicio', f'{dia(30)} 08:00', '--intervalo', '20', '--por-dia', '21')
        finally:
            globals()['MARGEM_POST'] = margem_original
        conferir(rc == 1 and len(srv['uploads']) == u0 and len(srv['posts']) == n0
                 and estados('SEMMARGEM', 'instagram')['G7'] == {'status': 'pendente'} and 'MESMO comando' in txt,
                 'horário a menos da margem antes do upload: para sem upload e o item continua pendente')

        def margem_estoura():
            globals()['MARGEM_POST'] = dt.timedelta(days=400)
        srv['ao_upload'] = margem_estoura
        try:
            rc, txt = ig('SEMMARGEM', '--inicio', f'{dia(30)} 08:00', '--intervalo', '20', '--por-dia', '21')
        finally:
            srv['ao_upload'] = None
            globals()['MARGEM_POST'] = margem_original
        conferir(rc == 1 and len(srv['uploads']) == u0 + 1 and len(srv['posts']) == n0
                 and estados('SEMMARGEM', 'instagram')['G7'] == {'status': 'pendente'},
                 'margem estourou durante o upload: nenhum POST e o item continua pendente')
        fila_ig('SEMCHEIA', *[item_ig(f'C{k:02d}', f'Legenda C{k}') for k in range(21)])
        rc1, _ = ig('SEMCHEIA', '--inicio', f'{dia(31)} 08:00', '--intervalo', '20', '--por-dia', '21', '--max', '1')
        rc2, _ = ig('SEMCHEIA', '--inicio', f'{dia(31)} 08:00', '--intervalo', '20', '--por-dia', '21')
        g = estados('SEMCHEIA', 'instagram')
        horas = [dt.datetime.fromisoformat(g[f'C{k:02d}']['scheduled_at']).strftime('%d %H:%M') for k in range(21)]
        esperado_ = [(parse_inicio(f'{dia(31)} 08:00') + dt.timedelta(minutes=20 * k)).strftime('%d %H:%M')
                     for k in range(21)]
        conferir(rc1 == 0 and rc2 == 0 and horas == esperado_ and all(v.get('status') == 'agendado_publer' for v in g.values()),
                 f'1 de teste (--max 1) às 08:00 e depois o lote: 21 de 08:00 a 14:40 no mesmo dia ({horas[0]}–{horas[-1]})')
        fila_ig('SEMRECORTE', *[item_ig(f'R{k:02d}', f'Legenda R{k}',
                                        {'status': 'postado_manual'} if k == 3 else None) for k in range(1, 9)])
        rc, _ = ig('SEMRECORTE', '--de', 'R02', '--ate', 'R07', '--max', '3', '--inicio', f'{dia(32)} 08:00',
                   '--intervalo', '20', '--por-dia', '21')
        g = estados('SEMRECORTE', 'instagram')
        saiu = {k: dt.datetime.fromisoformat(v['scheduled_at']).strftime('%H:%M') for k, v in g.items()
                if v.get('status') == 'agendado_publer'}
        conferir(rc == 0 and saiu == {'R02': '08:00', 'R04': '08:20', 'R05': '08:40'},
                 f'--de R02 --ate R07 --max 3 pula o postado_manual: R02, R04, R05 ({saiu})')
        recusas = 0
        for extra_ in (['--horarios', '09:00,13:00', '--intervalo', '20', '--por-dia', '2'],
                       ['--intervalo', '20'], ['--intervalo', '0', '--por-dia', '3']):
            r_, _ = ig('SEMRECORTE', '--inicio', f'{dia(33)} 08:00', '--simular', *extra_, chave_=None)
            recusas += str(r_).startswith('exit:')
        conferir(recusas == 3, '--horarios com --intervalo, --intervalo sem --por-dia e --intervalo 0 são recusados')
        recusas = 0
        for extra_ in (['--rede', 'instagram'], ['--trial', 'MANUAL']):
            r_, _ = saida_de(main, rede_fixa='tiktok', argv=['postar', 'SEMRECORTE', '--inicio', f'{dia(33)} 08:00',
                                                            '--simular', *extra_])
            recusas += str(r_).startswith('exit:')
        conferir(recusas == 2, 'o invólucro publer_tiktok.py recusa --rede instagram e --trial')
    except Exception as e:
        import traceback
        traceback.print_exc()
        falhas.append(f'exceção: {e!r}')
    finally:
        ESPERA.clear()
        ESPERA.update(espera_original)
        filamod.FILAS = fila_original
        globals()['obter_chave'] = chave_original
        servidor.shutdown()
        servidor.server_close()
        tmp.cleanup()
    if falhas:
        print(f'\nAUTOTESTE FALHOU: {len(falhas)} de {total[0]} verificações')
        return 1
    print(f'\nAUTOTESTE PASSOU: {total[0]} verificações, sem rede externa')
    return 0


# ---------------------------------------------------------------- CLI

def montar_parser(rede_fixa=None):
    """rede_fixa='tiktok' é o publer_tiktok.py (mesma linha de comando de antes); sem ela, --rede é obrigatório."""
    prog = 'publer_tiktok.py' if rede_fixa == 'tiktok' else None
    ap = argparse.ArgumentParser(prog=prog, description='Agenda vídeos da fila do orgânico no TikTok ou no Instagram '
                                                        '(Trial Reels) via API do Publer.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('contas', help='lista workspaces e contas sociais do Publer')
    c.add_argument('--workspace', help='id do workspace (padrão: todos)')
    p = sub.add_parser('postar', help='sobe e agenda na rede escolhida os vídeos pendentes da fila')
    p.add_argument('semana', help='nome da fila, ex.: SEM41-terca (lê filas/SEM41-terca.json)')
    if rede_fixa:
        p.add_argument('--rede', default=rede_fixa, choices=(rede_fixa,), help=f'fixa em {rede_fixa} neste invólucro')
    else:
        p.add_argument('--rede', required=True, choices=tuple(REDES), help='tiktok ou instagram (Trial Reels)')
    p.add_argument('--de', help='começa nesse id, na ordem da fila (ex.: VD001_B)')
    p.add_argument('--ate', help='termina nesse id (inclusive)')
    p.add_argument('--max', type=int, help='no máximo N vídeos nesta rodada')
    p.add_argument('--inicio', required=True, help='"AAAA-MM-DD HH:MM", horário de Brasília')
    p.add_argument('--horarios', help=f'horários do dia, ex.: "{HORARIOS_PADRAO}" (padrão)')
    p.add_argument('--intervalo', type=int, metavar='MIN',
                   help='em vez de --horarios: N horários (--por-dia) a partir da hora do --inicio, de MIN em MIN; '
                        'o resto vai pro dia seguinte no mesmo horário de início')
    p.add_argument('--por-dia', type=int, help='vídeos por dia (padrão: um por horário; obrigatório com --intervalo)')
    p.add_argument('--conta', help='id da conta no Publer (padrão: a que bate com contas.<rede> da fila)')
    p.add_argument('--conta-confirmada', metavar='NOME',
                   help='nome exato da conta do --conta, quando ele não bate com contas.<rede> da fila')
    p.add_argument('--workspace', help='id do workspace (padrão: Keychain ou o único da conta)')
    p.add_argument('--privacidade', choices=PRIVACIDADES, help='só TikTok (padrão: PUBLIC_TO_EVERYONE)')
    p.add_argument('--sem-comentarios', action='store_true', help='só TikTok: desliga comentários (padrão: liberados)')
    p.add_argument('--sem-duet', action='store_true', help='só TikTok: desliga duet (padrão: liberado)')
    p.add_argument('--sem-stitch', action='store_true', help='só TikTok: desliga stitch (padrão: liberado)')
    if rede_fixa != 'tiktok':
        p.add_argument('--trial', choices=TRIAL_MODOS,
                       help=f'só Instagram: modo do Trial Reel (padrão: {TRIAL_PADRAO}; SS_PERFORMANCE deixa o '
                            'Instagram liberar sozinho pros seguidores)')
    p.add_argument('--biblioteca', action='store_true', help='guarda o vídeo na biblioteca de mídia do Publer')
    p.add_argument('--repetir-erros', action='store_true',
                   help='inclui itens com erro em que NADA foi criado no Publer (upload, mídia, montagem, recusa)')
    p.add_argument('--forcar', action='append', metavar='ID',
                   help='reposta um item "agendando"/com erro depois do POST (só depois de conferir no Publer que o '
                        'post NÃO existe); aceita vários: --forcar VD002_C --forcar VD003_C ou VD002_C,VD003_C')
    p.add_argument('--simular', action='store_true',
                   help='só mostra o plano; nenhuma chamada de escrita (sem chave no Keychain, monta o plano só da fila)')
    if rede_fixa == 'tiktok':
        p.set_defaults(trial=None)
    sub.add_parser('autoteste', help='testa upload e fluxo contra um servidor local, sem rede externa')
    return ap


def main(rede_fixa=None, argv=None):
    a = montar_parser(rede_fixa).parse_args(argv)
    try:
        if a.cmd == 'contas':
            return cmd_contas(a)
        if a.cmd == 'postar':
            return cmd_postar(a)
        return cmd_autoteste(a)
    except ErroPubler as e:
        print(f'erro: {e}', file=sys.stderr)
        return 1
    except KeyboardInterrupt as e:
        print(f'\ninterrompido{f" ({e})" if str(e) else ""}', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())

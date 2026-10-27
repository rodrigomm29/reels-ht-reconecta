#!/usr/bin/env python3
"""Roteiro de gravação em PDF, no padrão aprovado pelo Rodrigo (modelo: Roteiros-Gravacao-01-08, agosto/2026).

Entrada: um JSON com o dia de gravação e os vídeos (formato abaixo). Saída: o .pdf (e o .html) ao lado do JSON.
O PDF sai pelo Chrome headless (/Applications/Google Chrome.app).

uso: python3 ferramentas/roteiro_pdf.py saida/roteiros/caso_hannah.json

{
 "cabecalho": "@drafernanda.porto · Planejamento de conteúdo — Outubro 2026",
 "titulo": "GRAVAÇÃO — CASO HANNAH", "subtitulo": "Guias de falas e direção de cena · ...",
 "visao_geral": [["1", "Vídeo", "Locação", "Publicação prevista"]],
 "checklist": [["Câmera:", "texto"]], "regras": ["texto"],
 "videos": [{
   "chips": ["VÍDEO 1 · CLÍNICA", "REEL"], "titulo": "...", "subtitulo": "...", "ideia": "...",
   "alertas": ["..."],
   "cenas": [{"nome": "CENA 1 — Abertura", "tempo": "0–5s", "opcional": false,
              "texto_tela": "...", "tela": "...", "fala": ["parágrafo", "..."], "direcao": "...", "nota": "...",
              "frases": {"A": "...", "B": "..."}, "cta": "..."}],
   "take_extra": {"titulo": "TAKE EXTRA — VERSÃO ANÚNCIO (não esquecer!)", "fala": "...", "direcao": "..."},
   "legenda": "..."}]
}
Em qualquer texto, **assim** vira negrito.
"""
import html, json, os, re, subprocess, sys

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

CSS = """
@page { size: A4; margin: 14mm 15mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; font-size: 9.4pt; line-height: 1.38; margin: 0; }
.topo { color: #555; font-size: 8.4pt; margin-bottom: 14pt; }
h1 { font-size: 19pt; margin: 0 0 3pt; letter-spacing: .2pt; }
.sub { color: #555; font-size: 8.6pt; margin-bottom: 16pt; }
h2 { font-size: 11pt; margin: 16pt 0 6pt; padding-bottom: 3pt; border-bottom: 1.6pt solid #1a1a1a; }
table { width: 100%; border-collapse: collapse; font-size: 8.6pt; }
th { background: #eee; text-align: left; font-weight: 700; }
th, td { border: .6pt solid #c8c8c8; padding: 4pt 6pt; vertical-align: top; }
ul { margin: 4pt 0; padding-left: 14pt; } li { margin: 2pt 0; }
.video { page-break-before: always; }
.chips span { display: inline-block; border: .7pt solid #777; border-radius: 3pt; color: #555; font-size: 7.4pt;
              padding: 1pt 5pt; margin-right: 4pt; letter-spacing: .3pt; }
.vt { font-size: 13.5pt; font-weight: 800; margin: 5pt 0 2pt; text-transform: uppercase; }
.vs { color: #555; font-size: 8.6pt; margin-bottom: 6pt; }
.ideia { margin: 0 0 8pt; }
.alerta { border: .8pt solid #c0392b; color: #8e2a1f; padding: 4pt 7pt; margin: 6pt 0; font-size: 8.6pt; }
.cena { margin-top: 9pt; page-break-inside: avoid; }
.rot { display: inline-block; background: #1a1a1a; color: #fff; font-weight: 700; padding: 2.5pt 7pt; border-radius: 2pt; font-size: 9pt; }
.tt { border: 1pt dashed #777; text-align: center; font-weight: 700; padding: 4pt; margin: 5pt 0; font-size: 8.8pt; }
.tela { background: #eef3fb; border-left: 3pt solid #3b6fb6; padding: 4pt 8pt; margin: 5pt 0; font-size: 8.6pt; }
.fala { background: #f1f1f1; border-left: 3.5pt solid #1a1a1a; padding: 5pt 9pt; margin: 5pt 0; }
.fala p { margin: 0 0 3pt; } .fala p:last-child { margin: 0; }
.dir { border-left: 3pt solid #bbb; padding: 2pt 8pt; color: #333; font-size: 8.7pt; margin: 4pt 0; }
.nota { color: #555; font-style: italic; font-size: 8pt; margin: 3pt 0; }
.frases b { display: block; margin: 5pt 0 2pt; }
.extra { border: 1.2pt solid #c0392b; padding: 0 8pt 8pt; margin-top: 12pt; page-break-inside: avoid; }
.extra .rot { background: #c0392b; margin-top: -7pt; }
.leg h3 { font-size: 9.6pt; margin: 14pt 0 3pt; letter-spacing: .3pt; }
"""


def t(s):
    """escapa e converte **negrito**."""
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html.escape(s or '', quote=False)).replace('\n', '<br>')


def cena(c):
    h = [f'<div class="cena"><span class="rot">{t(c["nome"])}'
         + (f' ({t(c["tempo"])})' if c.get('tempo') else '') + (' · opcional' if c.get('opcional') else '') + '</span>']
    if c.get('texto_tela'):
        h.append(f'<div class="tt">TEXTO NA TELA: {t(c["texto_tela"])}</div>')
    if c.get('tela'):
        h.append(f'<div class="tela"><b>Tela:</b> {t(c["tela"])}</div>')
    if c.get('fala'):
        h.append('<div class="fala">' + ''.join(f'<p>{t(p)}</p>' for p in c['fala']) + '</div>')
    if c.get('frases'):
        h.append('<div class="frases"><b>Frase de efeito — escolher na hora da gravação:</b><ul>'
                 + ''.join(f'<li><b style="display:inline">{k}:</b> {t(v)}</li>' for k, v in c['frases'].items()) + '</ul></div>')
    if c.get('cta'):
        h.append(f'<div class="fala"><p><b>CTA:</b> {t(c["cta"])}</p></div>')
    if c.get('direcao'):
        h.append(f'<div class="dir"><b>Direção:</b> {t(c["direcao"])}</div>')
    if c.get('nota'):
        h.append(f'<div class="nota">{t(c["nota"])}</div>')
    return ''.join(h) + '</div>'


def video(v):
    h = ['<div class="video"><div class="chips">' + ''.join(f'<span>{t(c)}</span>' for c in v.get('chips', [])) + '</div>',
         f'<div class="vt">{t(v["titulo"])}</div>']
    if v.get('subtitulo'):
        h.append(f'<div class="vs">{t(v["subtitulo"])}</div>')
    if v.get('ideia'):
        h.append(f'<p class="ideia"><b>Ideia:</b> {t(v["ideia"])}</p>')
    h += [f'<div class="alerta">⚠ {t(a)}</div>' for a in v.get('alertas', [])]
    h += [cena(c) for c in v.get('cenas', [])]
    if v.get('take_extra'):
        e = v['take_extra']
        h.append(f'<div class="extra"><span class="rot">{t(e.get("titulo", "TAKE EXTRA — VERSÃO ANÚNCIO (não esquecer!)"))}</span>'
                 f'<div class="fala"><p>{t(e["fala"])}</p></div>'
                 + (f'<div class="dir"><b>Direção:</b> {t(e["direcao"])}</div>' if e.get('direcao') else '') + '</div>')
    if v.get('legenda'):
        h.append(f'<div class="leg"><h3>LEGENDA</h3><div>{t(v["legenda"])}</div></div>')
    return ''.join(h) + '</div>'


def montar(d):
    h = [f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{t(d["titulo"])}</title>'
         f'<style>{CSS}</style></head><body>',
         f'<div class="topo">{t(d.get("cabecalho", ""))}</div><h1>{t(d["titulo"])}</h1>',
         f'<div class="sub">{t(d.get("subtitulo", ""))}</div>']
    if d.get('visao_geral'):
        h.append('<h2>Visão geral do dia</h2><table><tr><th>#</th><th>Vídeo</th><th>Locação</th><th>Publicação prevista</th></tr>'
                 + ''.join('<tr>' + ''.join(f'<td>{t(x)}</td>' for x in r) + '</tr>' for r in d['visao_geral']) + '</table>')
    if d.get('checklist'):
        h.append('<h2>Checklist de produção</h2><ul>'
                 + ''.join(f'<li><b>{t(k)}</b> {t(v)}</li>' for k, v in d['checklist']) + '</ul>')
    if d.get('regras'):
        h.append('<h2>Regras de publicação</h2><ul>' + ''.join(f'<li>{t(r)}</li>' for r in d['regras']) + '</ul>')
    h += [video(v) for v in d.get('videos', [])]
    return ''.join(h) + '</body></html>'


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    js = os.path.abspath(sys.argv[1])
    base = js[:-5]
    open(base + '.html', 'w', encoding='utf-8').write(montar(json.load(open(js, encoding='utf-8'))))
    r = subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                        f'--print-to-pdf={base}.pdf', 'file://' + base + '.html'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if not os.path.exists(base + '.pdf'):
        sys.exit(r.stderr[-800:])
    print(base + '.pdf')


if __name__ == '__main__':
    main()

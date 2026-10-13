# Instruções pros agentes de gancho (HT diário, estilo clean, 12/10/2026)

Você escolhe ganchos de vídeo a partir de um Reel da Ana (@anadareconecta, mentora de donos de clínica de harmonização facial; troque pelo perfil de vocês se for outro). Trabalho editorial em PT-BR. Não renderize vídeo; não altere nenhum arquivo além do JSON de saída.

Seu item (no `planos/_semXX_reels.json` do dia, gerado pelo `ferramentas/novo_lote.py`) traz: `vd`, `sc` (shortcode), `video` e `transcr` (nomes de arquivo), `dur`, `legenda` original, `evitar` (ganchos já usados em semanas anteriores: NÃO repita nem sobreponha esses trechos) e, às vezes, `cortes_antigos`.
- Vídeo: `{REELS_BASE}/videos/<video>` (REELS_BASE está no `config.env` da raiz do projeto)
- Transcrição Scribe (campo words: text/start/end/type): `{REELS_BASE}/transcricoes/<transcr>`
- Pasta do projeto: a raiz deste repositório (rode os comandos de dentro dela)

Quantos ganchos: 3 (A, B, C) — viram 3 vídeos que precisam parecer DIFERENTES entre si.

## Passos
1. Rode `python3 frases.py "<transcrição>"` (frases cronometradas + janelas candidatas). Leia a fala inteira.
2. Escolha 3 ganchos. Critérios, em ordem:
   a) Raciocínio completo: começa e termina em fronteira de frase/oração; se sustenta sozinho pra quem nunca viu o vídeo. Alvo 4–6 s; até ~7,5 s aceitável; piso 3,8 s.
   b) Três ÂNGULOS diferentes (frase controversa/reframe; número/história/cena concreta; pergunta/objeção que a doutora já se faz) e de TRÊS PARTES diferentes do vídeo, sem sobreposição.
   c) NUNCA os primeiros ~8 s do Reel (o corpo começa por eles).
   d) Não abrir com conectivo solto ou referência pra trás ("e aí", "então", "como eu falei") a menos que o bloco da legenda obrigue.
   e) Nada que mencione Desafio SUPERCASO, live, lançamento, evento com data, datas, "link na bio", nem política/eleição/regulação de conselho. ("desafio" como palavra comum, tipo "meu maior desafio", pode.)
3. CONFIRA A LEGENDA QUEIMADA de cada gancho (obrigatório):
   `python3 blocos_legenda.py "<vídeo>" "<transcrição>" --de <inicio-1.5> --ate <fim+1.5>`
   O primeiro bloco visível deve começar com a 1ª palavra do gancho; o último não pode trazer palavras de depois. Ajuste ou troque. Se só a ponta tiver 1–3 quadros do bloco errado, informe `fim_video` (último instante de vídeo limpo) ou `ini_corte_min`. Se o Reel não tiver legenda queimada, corte pelo silêncio do áudio (meça).
4. `inicio` = start da 1ª palavra e `fim` = end da última (2 casas), do JSON.
5. Título por gancho (vai numa caixa de texto estilo Instagram no meio da tela durante o gancho e no YouTube Shorts): eco curto do gancho, até 45 caracteres (máx. 55), assunto cedo, uma ideia só, números em algarismo, sem hashtag, travessão, dois-pontos ou "HOF" ("harmonização facial" por extenso); frase como a Ana falaria; os 3 diferentes entre si.
6. Se `dur` > 175 s: liste também `cortes_versao_curta` (frases inteiras de desvio que podem sair sem quebrar o argumento, bordas no silêncio e entre blocos de legenda, conferidas no blocos_legenda.py), em ordem do mais dispensável, somando pelo menos `dur + 8 − 193` s. Cada um com `inicio_corte`, `fim_corte`, `texto`. Se houver `cortes_antigos`, confira e reaproveite. Os ganchos não podem ficar dentro de um corte.
7. Escreva também 3 legendas do post (A, B, C): troca leve de palavras sobre a `legenda` original, mesma tese, mesma forma e emojis, palavra de comentário literal (ex.: "comenta ZAP" continua ZAP). Sem hashtags (elas entram depois).

## Saída
Grave no caminho indicado no seu pedido, exatamente:
```json
{"vd":"VD00X","shortcode":"...","duracao":0.0,
 "hooks":{"A":{"inicio":0.0,"fim":0.0,"texto":"literal","angulo":"...","titulo":"...","fim_video":null,"ini_corte_min":null,"obs":""},"B":{},"C":{}},
 "momentos":[], "cortes_versao_curta":[], "legendas":{"A":"...","B":"...","C":"..."}, "obs":"..."}
```
e devolva o mesmo JSON como resposta final (só o JSON).

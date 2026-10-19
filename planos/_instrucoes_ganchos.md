# Instruções pros agentes de gancho (Dra. Fernanda Porto, 18/10/2026)

Você escolhe ganchos de vídeo a partir de um Reel da Dra. Fernanda Porto (@drafernanda.porto). Ela faz rejuvenescimento facial em João Pessoa: Método AURA®, Ultherapy® (lifting sem cirurgia), qualidade de pele e sustentação. O trabalho é editorial, em PT-BR. Não renderize vídeo e não altere nenhum arquivo além do JSON de saída.

## Para quem é o vídeo
- **Público:** mulheres de 35 a 65 anos, PACIENTES em potencial. Não são profissionais nem alunas.
- **Objetivo:** quem assiste se reconhece, confia na Fernanda e chama no WhatsApp para uma avaliação. Os mesmos ganchos viram Trial Reels orgânicos e anúncios de captação.
- **O que a paciente sente e vê no espelho:** "derretimento facial", rosto quadrado, perda de contorno, papada, pescoço flácido, ar de cansada, mudança no rosto depois de emagrecer ou na menopausa.
- **O que a paciente teme:** ficar artificial ou com outro rosto, exagero, cirurgia, "será que tem jeito?".
- **O tom da Fernanda:** "você", de mulher para mulher, naturalidade acima de tudo, "não é para identificar o que foi feito", rejuvenescer sem perder a essência.
- **O que já provou que funciona** (anúncios e Reels de jul–out/2026):
  - "O lifting sem cirurgia realmente existe": Reel de 53 mil views e o anúncio com mais conversas;
  - "Menopausa batendo na porta… derretimento facial": o menor custo por lead;
  - "Derretimento facial? Sei que incomoda você aí também" e a história da Evelyn;
  - "Seu rosto muda aos poucos. E, muitas vezes, você nem percebe": 11 mil views.

## REGRA DE ANÚNCIO: foto de antes, de depois ou de antes/depois
Em vídeo que vai para ANÚNCIO (Meta Ads), nenhuma foto de antes, de depois ou de antes/depois pode ficar MAIS DE 2,5 s na tela, em tela cheia, em janela ou em tela dividida (o Meta barra acima de 3 s). No ORGÂNICO (Trial Reels e posts) não há esse limite: a foto fica o tempo que a edição pedir.

## Formato dos Reels dela
São Reels editados: a Fernanda fala para a câmera, intercalada com cenas da clínica e do procedimento, com pacientes e depoimentos. A legenda queimada costuma ser pequena e ficar no meio da tela. Alguns Reels quase não têm fala; esses não servem de base.

## O seu item
O seu item está no `planos/_semXX_reels.json` do dia, gerado pelo `ferramentas/novo_lote.py`. Ele traz:
- `vd` e `sc` (shortcode);
- `video` e `transcr` (nomes de arquivo);
- `dur`;
- a `legenda` original;
- `evitar`: ganchos já usados em semanas anteriores. NÃO repita nem sobreponha esses trechos;
- às vezes, `cortes_antigos`.

Onde ficam os arquivos:
- Vídeo: `{REELS_BASE}/videos/<video>` (o `REELS_BASE` está no `config.env` da raiz do projeto).
- Transcrição Scribe (campo `words`: text/start/end/type): `{REELS_BASE}/transcricoes/<transcr>`.
- Projeto: a raiz deste repositório. Rode os comandos de dentro dela.

Quantos ganchos: 3 (A, B, C). Eles viram 3 vídeos que precisam parecer DIFERENTES entre si.

## Passos
1. Rode `python3 frases.py "<transcrição>"`, que mostra as frases cronometradas e as janelas candidatas. Leia a fala inteira.
2. Escolha 3 ganchos. Critérios, em ordem:
   a) **Raciocínio completo.** O gancho começa e termina em fronteira de frase ou oração e se sustenta sozinho para quem nunca viu o vídeo. Alvo de 4 a 6 s; até ~7,5 s é aceitável; piso de 3,8 s.
   b) **Três ÂNGULOS diferentes, um em cada letra**, tirados de TRÊS PARTES diferentes do vídeo, sem sobreposição:
      - **A, dor e identificação.** A paciente se vê no espelho: "rosto quadrado", "ar de cansada", "derretimento", "você nem percebe". Este é o que vai primeiro para anúncio, então escolha o mais forte aqui.
      - **B, prova.** Uma paciente real, idade, cena ou resultado concreto: "ela tem 51 anos e…", "a primeira mensagem que ela me mandou…", "ninguém notou o procedimento".
      - **C, objeção, medo ou mito.** "Tem jeito?", "medo de ficar artificial", "lifting sem cirurgia existe", "não adianta fazer de tudo", "o que não fazer".
      Se o Reel não tiver um dos ângulos, use outro trecho forte e explique em `obs`.
   c) NUNCA use os primeiros ~8 s do Reel, porque o corpo do vídeo começa por eles.
   d) Não abra com conectivo solto ou referência para trás ("e aí", "então", "como eu falei"), a menos que o bloco da legenda obrigue.
   e) **Fala de saúde e estética: regras.**
      - Nada que prometa ou garanta resultado ("vai rejuvenescer 10 anos", "resultado garantido", "sem nenhum risco").
      - Nada de preço, desconto, promoção, condição especial, sorteio ou "últimas vagas".
      - Nada de comparação com outra profissional ou clínica, nem "a melhor".
      - Nada que exponha a paciente de forma negativa ("ela estava horrível").
      - Nada de live, evento com data, datas, "link na bio", política ou regras de conselho.
   f) **Foto de antes/depois (só importa para anúncio):** rode `python3 ferramentas/checar_fotos.py "<vídeo>"` (lista os trechos de imagem parada). Se o Reel tiver foto parada acima de 2,5 s, avise no começo do `obs` com "FOTO > 2,5 s: não serve para anúncio sem limpar". Para o orgânico, isso não muda a escolha dos ganchos.
   g) De preferência, um momento com prova visual: o resultado aparece, a paciente reage, o aparelho está em uso. Para conferir, tire um quadro com
      `ffmpeg -ss <t> -i "<vídeo>" -frames:v 1 -y /tmp/q.jpg` e olhe.
3. **Confira a legenda queimada de cada gancho** (obrigatório):
   `python3 blocos_legenda.py "<vídeo>" "<transcrição>" --de <inicio-1.5> --ate <fim+1.5>`
   - O primeiro bloco visível deve começar com a 1ª palavra do gancho, e o último não pode trazer palavras de depois. Ajuste ou troque.
   - Se só a ponta tiver 1 a 3 quadros do bloco errado, informe `fim_video` (o último instante de vídeo limpo) ou `ini_corte_min`.
   - Se o Reel não tiver legenda queimada, corte pelo silêncio do áudio (meça).
4. `inicio` = start da 1ª palavra e `fim` = end da última, com 2 casas, tirados do JSON.
5. **Título por gancho.** Ele vai numa caixa de texto no meio da tela durante o gancho, e no YouTube Shorts.
   - Eco curto do gancho, falando com a paciente: até 45 caracteres (máximo 55), assunto cedo, uma ideia só.
   - Números em algarismo.
   - Sem hashtag, travessão ou dois-pontos.
   - Termo técnico só se ela mesma usar ("Ultherapy", "colágeno").
   - Sem promessa de resultado.
   - Uma frase como a Fernanda falaria, por exemplo "Seu rosto não está cansado, está sem sustentação".
   - Os 3 títulos diferentes entre si.
   - **Posição:** a caixa de título fica, por padrão, abaixo da legenda (y≈1470). Se no gancho aparecer foto, antes/depois ou imagem importante na metade de baixo da tela (confira os quadros), ponha `"titulo_cy": 330` no gancho: o título sobe para o alto e não cobre a imagem.
6. **Se `dur` > 175 s,** liste também `cortes_versao_curta`: frases inteiras de desvio que podem sair sem quebrar o argumento.
   - As bordas ficam no silêncio e entre blocos de legenda, conferidas no `blocos_legenda.py`.
   - Ordene do mais dispensável para o menos, somando pelo menos `dur + 8 − 193` s.
   - Cada um tem `inicio_corte`, `fim_corte` e `texto`.
   - Se houver `cortes_antigos`, confira e reaproveite.
   - Os ganchos não podem ficar dentro de um corte.
7. **Escreva também 3 legendas do post (A, B e C).**
   - Troca leve de palavras sobre a `legenda` original, com a mesma tese, a mesma forma e os mesmos emojis.
   - Se a original pede comentário ou mensagem ("me conta", "comenta EU QUERO"), mantenha a palavra literal.
   - Sem hashtags, porque elas entram depois.
   - Sem preço ou promessa.

## Saída
Grave no caminho indicado no seu pedido, exatamente:
```json
{"vd":"VD00X","shortcode":"...","duracao":0.0,
 "hooks":{"A":{"inicio":0.0,"fim":0.0,"texto":"literal","angulo":"dor","titulo":"...","titulo_cy":null,"fim_video":null,"ini_corte_min":null,"obs":""},"B":{},"C":{}},
 "momentos":[], "cortes_versao_curta":[], "legendas":{"A":"...","B":"...","C":"..."}, "obs":"..."}
```
Devolva o mesmo JSON como resposta final (só o JSON).

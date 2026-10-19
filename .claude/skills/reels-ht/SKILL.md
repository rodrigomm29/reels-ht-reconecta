---
name: reels-ht
description: Conduz a rotina diária de variações de Reels deste projeto (baixar → transcrever → escolher Reels base → ganchos por agente → janela → plano → render → conferir → organizar → agendar no Publer). Acionar quando pedirem "variações de hoje", "21 de hoje", "lote do dia", "tela dividida", "programar no Publer", "posts de antes e depois", "carrossel", ou para retomar um dia pela metade.
---

# reels-ht — rotina do dia

O passo a passo com os comandos está no `README.md` (seção 5). Esta skill guarda as REGRAS que o README não pode esquecer.

## Antes de começar
- `zsh instalar.sh` tem que terminar em "tudo certo.". Se faltar chave, peça à pessoa que grave no Keychain; nunca peça a chave no chat e nunca a imprima.
- Confirme com a pessoa o plano do dia antes de rodar o lote:
  - quantos Reels base (mínimo 5, ideal 7);
  - quais Reels;
  - o estilo;
  - o horário de início.

## Perfil atual: Dra. Fernanda Porto
- O público são pacientes (mulheres de 35 a 65 anos), não profissionais.
- Estilo padrão: `clean`. Os Reels dela já são editados.
- Render: `--versao ORG AD`. O AD vai para o Gerenciador de Anúncios à mão.
- Nada de preço, promoção ou promessa de resultado em gancho, título ou legenda.

## Escolha dos Reels base
- Fora:
  - lançamento pago (Desafio SUPERCASO etc.);
  - live;
  - Reel sem fala;
  - Reel abaixo da data de corte que a equipe combinou;
  - os nossos próprios Trial Reels que voltaram pelo download (confira a legenda).
- Rode `checar_lancamento.py` nos candidatos.
- Reel já usado pode voltar, mas com ganchos NOVOS: o `ferramentas/novo_lote.py` põe os antigos em `evitar`.

## Ganchos (um agente por Reel)
- Cada agente segue `planos/_instrucoes_ganchos.md` e grava `planos/_rascunho_<semana>_<dia>/<VD>.json`.
- Lance os agentes em paralelo, um por Reel.
- Leia o resultado. Gancho fraco ou repetido = peça outro; Reel fraco = troque o Reel.
- A headline (campo `titulo`):
  - até 45 caracteres;
  - uma ideia;
  - como a pessoa falaria;
  - 3 diferentes por Reel.

## Render
- **UM vídeo por vez** (`lote_peles.py`, sempre com `caffeinate -m`). Nunca dois lotes juntos.
- Piloto de 1 vídeo antes do lote quando o estilo ou o acervo de B-roll mudou. Mostre as tiras à pessoa antes de seguir.
- Nunca baixar a qualidade para acelerar (CRF 18 / HEVC CRF 20 é o piso).
- Se o ffmpeg ficar parado sem CPU fora do lote: o B-roll e a legenda entram pelo filtro `movie` justamente para evitar isso. Não volte a passá-los como `-i`.

## Antes de agendar
- Olhe TODAS as tiras em `_conferencia/`. Confira:
  - legenda;
  - headline;
  - rosto dentro da janela;
  - B-roll proibido (criança, sensual, outra doutora, texto grande).
- Rode o `publer_postar.py ... --simular` e confira horários, conta e legendas.
- A fila de vídeos termina em `-ht`. Antes do `fila.py montar`, veja se `publicar/filas/<nome>.json` já existe e de quem é: carrossel de outra pessoa NÃO se mistura.
- Limite: 25 posts no Instagram por 24 h por conta, contando carrossel.
- Trial Reel sempre MANUAL (o padrão do script).

## Posts de foto (antes e depois)
- Comandos no README, seção 5.10. Entrada: pasta "Posts Fernanda" do iCloud; lote `FOTOS-SEMnn`.
- Depois do `importar_fotos.py`, olhe a `_conferencia.jpg` (Read) e mostre à pessoa. Foto torta, cortada ou de outra paciente = pare e pergunte.
- Legenda vazia: escreva você, no tom da Fernanda, para pacientes:
  - abre com o resultado visível (o que mudou);
  - explica em 1–2 frases o que foi feito, sem jargão;
  - fecha com "cada pele responde de um jeito" ou parecido, e o convite para a avaliação (link da bio);
  - até 5 hashtags do `HASHTAGS` do config;
  - nunca preço, promoção, "garantido" ou prazo prometido (regra do CFM).
- Mostre as legendas à pessoa antes do `fila.py montar-fotos`.
- Carrossel vai pro FEED (não é Trial Reel). Escolha um horário sem Reel e rode `--simular` antes.
- O 1º carrossel real roda com `--max 1`: a doc do Publer diverge no `type` ("photo" × "carousel"). Se o Publer recusar, o item fica "recusado" (nada criado): troque `TIPO_CARROSSEL` no `publer_postar.py` e repita com `--repetir-erros`.

## No fim
- Diga quantos foram agendados, os horários, o que ficou de fora e por quê.
- Vídeo publicado nunca é sobrescrito: versão nova = nome novo.

# Instruções pro agente de takes (vídeos brutos da Dra. Fernanda, 18/10/2026)

Você monta a edição de um vídeo BRUTO, ainda não postado: escolhe o que fica e o que sai, e onde entra a imagem de apoio. Trabalho editorial em PT-BR. Não renderize vídeo e não altere nenhum arquivo além do JSON de saída.

O público e o tom são os mesmos dos ganchos: leia a seção "Para quem é o vídeo" de `planos/_instrucoes_ganchos.md`.

## REGRA DE ANÚNCIO: foto de antes, de depois ou de antes/depois
Em vídeo que vai para ANÚNCIO (Meta Ads), nenhuma foto de antes, de depois ou de antes/depois pode ficar MAIS DE 2,5 s na tela, em tela cheia, em janela ou em tela dividida (o Meta barra acima de 3 s). No ORGÂNICO (Trial Reels e posts) não há esse limite: a foto fica o tempo que a edição pedir.

## O seu item
O `ferramentas/importar_brutos.py` já juntou os takes e transcreveu. Você recebe o id (ex.: `BR001`):
- `dados/brutos/<ID>.json`: o vídeo juntado (`video`), o início de cada take no vídeo juntado (`takes`), as imagens de apoio (`imagens`) e as cenas de atendimento (`cenas`, já normalizadas, sem áudio, com a duração de cada uma).
- Vídeo: `dados/videos/<video>`.
- Transcrição Scribe: `dados/transcricoes/<mesmo nome>.json` (campo `words`: text/start/end/type).

O bruto vem de duas formas:
- **vários takes curtos**, um por frase, com conversa com quem filma entre eles ("ficou bom?", "é isso?", "peraí");
- **um take longo** com erros, frases repetidas e recomeços.

## Passos
1. Rode `python3 frases.py "<transcrição>"` e leia a fala inteira. Confira também os inícios de take em `takes`: a emenda costuma cair entre eles.
2. Monte o roteiro final. Ele é a fala da Fernanda, em ordem, sem nada que não seja para o público.
   - **Sai:** conversa com quem filma, perguntas de "ficou bom?", contagem, "peraí", "vou de novo", tosse, risada de erro, frase interrompida no meio.
   - **Frase repetida** (ela errou e falou de novo): fica a versão MAIS COMPLETA e fluida, em geral a última. Nunca deixe duas versões da mesma ideia.
   - **Ordem:** a do roteiro. Normalmente é a ordem gravada; só mude se for claro que o take saiu fora de ordem.
   - **Mais de um roteiro no mesmo bruto** (ela gravou 2 vídeos de uma vez): avise em `obs` e faça só o primeiro.
3. Cada trecho mantido vai de `start` da 1ª palavra a `end` da última (2 casas), em frases inteiras. NÃO acrescente folga: o `editar_bruto.py` põe a respiração (0,10 s antes e 0,20 s depois: a emenda fica com 0,30 s, a pausa natural dela entre frases) e alterna o enquadramento a cada trecho.
   - **Palavra esticada:** o Scribe às vezes estica a 1ª palavra de um take para trás (start muito antes do resto, duração de 2 s ou mais). Ache o início real pelo silêncio:
     `ffmpeg -nostdin -ss <t-1> -t 6 -i "<vídeo>" -af silencedetect=noise=-35dB:d=0.25 -f null - 2>&1 | grep silence_`
     (os tempos saem relativos a `t-1`).
   - **Duas frases do mesmo take com pausa curta (< 0,8 s):** podem ficar num trecho só.
4. **Imagem de apoio** (antes e depois etc.), se houver em `imagens`:
   - Ponha onde a fala aponta para ela ("olha esse resultado", "aqui", "essa paciente").
   - `em` = um pouco depois da palavra que aponta, no tempo do BRUTO e dentro de um trecho mantido.
   - `dur`: no orgânico, o tempo que a fala pede (em geral 2 a 4 s). Se o vídeo também vai virar anúncio, ponha `"para_anuncio": true` no JSON: aí cada foto fica no máximo 2,5 s (o script trava).
   - Pode aparecer mais de uma vez, mas com pelo menos 10 s entre as aparições e no máximo 2 vezes por vídeo.
   - `modo`: `"dividida"` (preferido pela Fernanda: a tela divide SÓ enquanto a foto aparece, foto em cima e ela embaixo, depois volta para ela em tela cheia) ou `"tela_cheia"`. Na dividida, meça a janela do rosto com `python3 ferramentas/medir_janela.py <ID>` (folha com régua) e grave `"dividida_y"` no JSON: o topo da cabeça logo abaixo da borda de cima, rosto e peito dentro dos 964 px.
   - Só use foto do CASO de que ela está falando (a imagem que veio na pasta). Nunca foto ou cena aleatória.
   - Sem lugar natural na fala: use uma vez, no trecho de prova/resultado, e explique em `obs`.
5. **Cenas de atendimento**, se houver em `cenas`: elas entram em tela cheia, por cima da fala (a voz dela continua e a legenda também).
   - Antes de escolher, olhe cada cena: tire 2 ou 3 quadros com `ffmpeg -ss <t> -i "<cena>" -frames:v 1 -y /tmp/c.jpg`.
   - Ponha cada cena onde a fala combina com ela: procedimento quando ela fala de tratamento ou técnica, aparelho quando cita a tecnologia, consulta ou avaliação quando fala de planejamento.
   - `em` no tempo do BRUTO, dentro de um trecho mantido; `dur` entre 1,5 e 4 s (o script trava nisso); `ini` = de onde o clipe começa (0 se for do início).
   - **Ritmo:** no máximo uma cena a cada ~6 s de vídeo, e nunca duas seguidas sem a Fernanda aparecer entre elas.
   - **Não cubra:** os primeiros 3 s do vídeo (ela precisa aparecer); frase de identificação forte dita olhando para a câmera ("você", "eu sei que…"); o momento da imagem de antes e depois.
   - Cada cena no máximo uma vez. Cena que não combina com nada da fala fica de fora: liste em `obs`.
   - Cena com rosto de paciente reconhecível: só use se veio na pasta (a Fernanda já tem a autorização).
6. Confira a duração final (soma dos trechos + ~0,6 s por trecho). Alvo: até 90 s. Se passar, aponte em `obs` o que poderia sair.
7. Último trecho com CTA de anúncio ("clique e agende"): mantenha e marque `"cta_final": true`. Os ganchos não usam esse trecho.

## Saída
Grave em `dados/brutos/<ID>_edicao.json`, exatamente:
```json
{"id":"BR00X",
 "manter":[[0.0,0.0,"texto literal do trecho"]],
 "dividida_y":400,
 "imagens":[{"arquivo":"brutos/entrada/<pasta>/<imagem>","em":0.0,"dur":2.5,"modo":"dividida","_porque":"palavra que aponta"}],
 "cenas":[{"arquivo":"dados/brutos/<ID>_cenas/<cena>.mp4","em":0.0,"dur":3.0,"ini":0.0,"_porque":"fala que combina"}],
 "cta_final":false,
 "sai":[[0.0,0.0,"o que saiu e por quê"]],
 "obs":"..."}
```
Devolva o mesmo JSON como resposta final (só o JSON).

Depois, quem pediu roda `python3 ferramentas/editar_bruto.py <ID>` (gera a versão sem gancho) e segue o fluxo normal dos ganchos com o id `<ID>E`.

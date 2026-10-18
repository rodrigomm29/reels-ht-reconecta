# Instruções pro agente de takes (vídeos brutos da Dra. Fernanda, 18/10/2026)

Você monta a edição de um vídeo BRUTO, ainda não postado: escolhe o que fica e o que sai, e onde entra a imagem de apoio. Trabalho editorial em PT-BR. Não renderize vídeo e não altere nenhum arquivo além do JSON de saída.

O público e o tom são os mesmos dos ganchos: leia a seção "Para quem é o vídeo" de `planos/_instrucoes_ganchos.md`.

## O seu item
O `ferramentas/importar_brutos.py` já juntou os takes e transcreveu. Você recebe o id (ex.: `BR001`):
- `dados/brutos/<ID>.json`: o vídeo juntado (`video`), o início de cada take no vídeo juntado (`takes`) e as imagens de apoio (`imagens`).
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
   - `dur` no máximo 2,5 s (regra do Meta: antes e depois não pode passar de 3 s na tela; o script também trava em 2,5).
   - Pode aparecer mais de uma vez, mas com pelo menos 10 s entre as aparições e no máximo 2 vezes por vídeo.
   - Sem lugar natural na fala: use uma vez, no trecho de prova/resultado, e explique em `obs`.
5. Confira a duração final (soma dos trechos + ~0,6 s por trecho). Alvo: até 90 s. Se passar, aponte em `obs` o que poderia sair.
6. Último trecho com CTA de anúncio ("clique e agende"): mantenha e marque `"cta_final": true`. Os ganchos não usam esse trecho.

## Saída
Grave em `dados/brutos/<ID>_edicao.json`, exatamente:
```json
{"id":"BR00X",
 "manter":[[0.0,0.0,"texto literal do trecho"]],
 "imagens":[{"arquivo":"brutos/entrada/<pasta>/<imagem>","em":0.0,"dur":2.5,"_porque":"palavra que aponta"}],
 "cta_final":false,
 "sai":[[0.0,0.0,"o que saiu e por quê"]],
 "obs":"..."}
```
Devolva o mesmo JSON como resposta final (só o JSON).

Depois, quem pediu roda `python3 ferramentas/editar_bruto.py <ID>` (gera a versão sem gancho) e segue o fluxo normal dos ganchos com o id `<ID>E`.

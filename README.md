# Reels HT — variações diárias de Reels

Este projeto pega os Reels já publicados no Instagram e transforma cada um em várias versões novas.
Cada versão começa com um **gancho**: um trecho forte do meio do vídeo colocado no começo. Depois o vídeo
volta para o início e segue normal. As versões são programadas no **Publer** como Trial Reels do Instagram.

O estilo atual é a **tela dividida**:
- B-roll trocando a cada ~3 s na metade de cima, e a pessoa falando na metade de baixo;
- legenda nova logo acima da emenda, com uma palavra entrando por vez;
- headline em caixa branca no alto, nos 4 primeiros segundos.

Os estilos antigos (**clean** e **peles**) continuam disponíveis.

> **Adaptado para a Dra. Fernanda Porto** (@drafernanda.porto, rejuvenescimento facial, João Pessoa) em 18/10/2026.
> - **Ganchos:** as instruções dos agentes em `planos/_instrucoes_ganchos.md` falam com pacientes, não com donos de clínica. A = dor e identificação, B = prova, C = objeção ou mito.
> - **Estilo:** os Reels dela já são editados, com fala intercalada com cenas da clínica. Por isso, comece com `--estilo clean`. A `dividida` pede acervo de B-roll próprio e uma janela fixa do rosto, que não acompanha as trocas de cena.
> - **Anúncio:** o plano gera também a versão `AD`, com o Reel inteiro, na subpasta `anúncio/`. Se `TELA_FINAL` estiver preenchido, ela termina na tela de CTA. Os anúncios sobem à mão no Gerenciador de Anúncios; o Publer só agenda o orgânico.

Rotina típica: 7 Reels base × 3 ganchos = **21 vídeos por dia**, postados a partir das 19:00 com 2 minutos de intervalo.

```
baixar Reels → transcrever → escolher Reels base → ganchos (Claude Code) → medir janela → plano do dia
   → conferir legenda → render (1 por vez) → conferir tiras → organizar → fila → agendar no Publer
```

---

## 1. Do que você precisa

| O quê | Para quê | Observação |
|---|---|---|
| **Mac** (Apple Silicon ou Intel) | tudo | O projeto usa o Keychain e o OCR do Vision, que só existem no macOS. |
| **Homebrew** | instalar os programas | https://brew.sh |
| **ffmpeg, uv, python3** | render e download | `brew install ffmpeg uv python` |
| **Ferramentas de linha de comando da Apple** | compilar o OCR | `xcode-select --install` |
| **Instagram logado no navegador** | baixar os Reels | Usa a sessão do navegador, então não há senha no código. |
| **Chave da ElevenLabs** | transcrever as falas (Scribe v2) | Paga por uso; cada Reel custa poucos centavos. |
| **Publer, plano Business** | agendar os posts | Precisa de uma chave de API com os escopos workspaces, accounts, posts e media. A conta do Instagram precisa estar conectada e ter mais de 1.000 seguidores para usar Trial Reels. |
| **Claude Code** | escolher os ganchos | O passo editorial é feito por agentes que seguem `planos/_instrucoes_ganchos.md`. |
| **HD com espaço** | Reels e vídeos prontos | Uns 3 GB para os Reels e uns 4 GB por dia de saída (21 × ~180 MB). |

---

## 2. Instalação (uma vez)

1. **Baixe o projeto e entre na pasta.**
   ```bash
   git clone <url-do-repositório> reels-ht
   cd reels-ht
   ```

2. **Rode o instalador.** Ele confere os programas, instala o Pillow e o numpy, compila o OCR e cria o `config.env`.
   ```bash
   zsh instalar.sh
   ```

3. **Abra o `config.env` e ajuste os caminhos da sua máquina.** O arquivo explica cada campo. Os principais são:
   - `REELS_BASE`: onde ficam os Reels baixados e as transcrições. Pode ser um HD externo.
   - `SAIDA_DIR`: onde os vídeos prontos são gravados.
   - `BROLL_DIR`: o seu acervo de B-roll. Veja a seção 4.
   - `IG_PERFIL`, `CONTA_INSTAGRAM`, `CONTA_TIKTOK`: o perfil de onde baixar e a conta onde postar.
   - `NAVEGADOR`: o navegador logado no Instagram. Se usar um perfil específico do Chrome, escreva
     `chrome:Profile 3`, trocando pelo nome da pasta do perfil, que aparece em `chrome://version`.

   > Evite dois-pontos `:` e aspas simples `'` nos caminhos. O ffmpeg não aceita esses caracteres dentro do filtro de vídeo.

4. **Guarde as chaves no Keychain.** Assim elas não ficam em nenhum arquivo. O `-w` no fim faz o macOS
   pedir a chave sem mostrar o que você digita.
   ```bash
   security add-generic-password -s elevenlabs-api-key -a "$USER" -U -w
   security add-generic-password -s reconecta-publer -a api-key -U -w
   security add-generic-password -s reconecta-publer -a workspace-id -U -w   # opcional
   ```
   Também dá para preencher `ELEVENLABS_API_KEY` e `PUBLER_API_KEY` no `config.env`. O `config.env` nunca vai
   para o git, mas, se fizer isso, não mande o arquivo para ninguém.

5. **Rode `zsh instalar.sh` de novo.** O instalador marca o que ainda falta. Quando ele disser **"tudo certo."**, está pronto.

---

## 3. O que NÃO vem no repositório, e o que fazer

O repositório só tem código e instruções. Mídia, dados e material licenciado ficam fora.

| Não vem | Por quê | O que você faz |
|---|---|---|
| **Reels baixados** | mídia da conta | Baixe com `zsh baixar_reels.sh`, como na seção 5. |
| **Transcrições** | geradas a partir da mídia | Gere com `zsh transcrever_reels.sh`. Para economizar crédito, peça ao Sávio o zip das transcrições já feitas e descompacte em `$REELS_BASE/transcricoes/`. |
| **Acervo de B-roll** | tem memes, celebridades e clipes de terceiros, com direito de imagem | Monte o seu, como na seção 4. Sem ele, o estilo dividida não roda. |
| **Histórico de ganchos** (`planos/ht_*.json`) | dado de trabalho | Para os agentes não repetirem gancho já usado, copie os planos antigos de quem já usa o projeto para a sua pasta `planos/`. |
| **Kit de efeitos e SFX** (`kit_peles/`) | sai de pacotes pagos (Cineva, Pack editor) | **Opcional.** Clean e dividida funcionam sem o kit; só o som do obturador fica de fora. As peles manchete, cinema e dinâmica precisam dele. Quem tem as licenças preenche `CINEVA_DIR` e `PACK_EDITOR_DIR` e roda `python3 kit_peles.py`. |
| **LUTs da pele cinema** | pagas | **Opcional.** Qualquer `.cube` serve: preencha `LUTS_DIR` e `LUT_1..3`. |
| **Fontes Grift e 403 Degrad Mono** | pagas | **Opcional.** Só as peles antigas usam. A Inter, usada pela headline e pela legenda, vem em `fontes/` (licença OFL, livre). |
| **Vocabulário de grafias** (`scribe/vocab.txt`) | tem nomes de pessoas | Copie `scribe/vocab.exemplo.txt` para `scribe/vocab.txt` e acrescente os nomes e termos que a transcrição erra. Quem já usa o projeto pode te passar o dela. |
| **Tela final de CTA** | marca | Só para a versão de anúncio, com tela final. O orgânico não usa. Preencha `TELA_FINAL`. |
| **`config.env`, filas do Publer, legendas geradas** | locais | São criados na sua máquina conforme você usa. |

---

## 4. B-roll (obrigatório para a tela dividida)

O B-roll é o que aparece na metade de cima: clipes curtos, sem áudio, trocando a cada 3 segundos.

1. **Junte os clipes numa pasta de origem, separados em subpastas por tema.** Por exemplo: `01-reacao`,
   `02-textura`, `03-luxo`, `04-desenho`, `05-animais`. Vale vídeo vertical, quadrado ou deitado. Deitado
   precisa ser pelo menos Full HD, porque o recorte usa a altura.
   - **Quantidade:** com ~120 clipes, cada uma das 3 versões de um Reel ganha um conjunto só dela, de ~40
     clipes. Com menos de ~60 clipes, as versões passam a repetir clipe entre si.

2. **Normalize para 1080×956.** O script gera cópias no `BROLL_DIR` e não mexe nos originais. Pode rodar de
   novo sempre que entrar clipe novo; ele pula o que já fez.
   ```bash
   python3 ferramentas/normalizar_broll.py "/caminho/da/pasta/de/origem"
   ```

3. **Faça a triagem no olho.**
   ```bash
   python3 ferramentas/triagem_broll.py
   ```
   O script gera `planos/_broll_triagem.json`, com todos os clipes em `"ok"`, e folhas de contato em
   `planos/_broll_folhas/`, com 3 quadros por clipe. Abra as folhas e mova para `"excluir"`, com o motivo, tudo
   o que se encaixar nas regras abaixo. **Na dúvida, exclua.**
   - qualquer **criança**, inclusive personagem criança de desenho;
   - qualquer coisa **sensual ou sugestiva**;
   - **outra doutora ou profissional** atendendo (parece concorrente);
   - **pessoa falando para a câmera**, porque lê como depoimento falso;
   - **texto grande queimado** no quadro, que briga com a legenda e a headline;
   - clipe **parado** demais.

   Para a Dra. Fernanda, o B-roll ideal são cenas dela mesma: clínica, aparelho, pele em close, bastidor.
   Exclua também:
   - **meme, celebridade ou humor**;
   - **agulha, sangue ou close** de procedimento que assuste;
   - **paciente sem autorização** de imagem;
   - **antes e depois de terceiros**.

---

## 5. A rotina do dia

Rode tudo de dentro da pasta do projeto. Os exemplos usam a semana `SEM43`, a segunda-feira e 7 Reels.

### 5.1 Baixar e transcrever
```bash
zsh baixar_reels.sh                 # os 15 Reels mais recentes de IG_PERFIL (ou: zsh baixar_reels.sh perfil 20)
zsh transcrever_reels.sh            # transcreve só o que ainda não tem transcrição
```

### 5.2 Escolher os Reels base
- **Quantos:** no mínimo 5. O ideal é 7, porque 7 × 3 ganchos = 21 vídeos.
- **Bloqueados:**
  - Reels de lançamento pago, como o Desafio SUPERCASO;
  - lives;
  - Reels sem fala;
  - Reels muito antigos (a equipe combina a data de corte; hoje, nada de 22/07/2026 para trás);
  - **os nossos próprios Trial Reels** que voltaram pelo download. Para identificar, confira a legenda.
- **Checagem de lançamento:** procura Desafio, lançamento e live na fala e no texto da tela.
  ```bash
  python3 checar_lancamento.py DeVFJ2Ei65T DeMoWouilUT ...
  ```
- **Lista do dia:** registre os Reels escolhidos. `--primeiro` é o número do primeiro VD do dia: 1 na segunda, 8 na terça, 15 na quarta…
  ```bash
  python3 ferramentas/novo_lote.py --semana SEM43 --dia segunda --primeiro 1 DeVFJ2Ei65T DeMoWouilUT ...
  ```

### 5.3 Ganchos (Claude Code)
Abra o Claude Code na pasta do projeto e peça:

> Para cada Reel de `segunda` em `planos/_sem43_reels.json`, rode um agente seguindo
> `planos/_instrucoes_ganchos.md`. Grave a saída em `planos/_rascunho_sem43_segunda/<VD>.json`.

Cada agente devolve:
- 3 ganchos (A, B e C), de partes diferentes do vídeo, nunca dos 8 primeiros segundos;
- a **headline** de cada um (o campo `titulo`, com até 45 caracteres);
- 3 variações da legenda do post;
- para Reels acima de 175 s, os trechos que podem sair da versão curta.

Leia os ganchos e as headlines antes de seguir.

### 5.4 Medir a janela da pessoa (tela dividida)
Faça isso para cada Reel novo. Os Reels já medidos ficam guardados em `planos/_dividida_y.json`.
```bash
python3 ferramentas/medir_janela.py DeVFJ2Ei65T                    # folha com régua em planos/_janelas/
python3 ferramentas/medir_janela.py DeVFJ2Ei65T --y 300            # confere o recorte
python3 ferramentas/medir_janela.py DeVFJ2Ei65T --y 300 --gravar   # grava
```
Como escolher o `y`:
- o rosto inteiro fica dentro da janela;
- o topo da cabeça fica logo abaixo da borda de cima;
- se der, a legenda original do Reel fica fora da janela.

Reel sem medição usa `DIVIDIDA_Y_PADRAO`.

### 5.5 Plano do dia
```bash
python3 montar_plano_dia.py --semana SEM43 --dia segunda --rascunho planos/_rascunho_sem43_segunda \
    --estilo dividida --dividida-y planos/_dividida_y.json --broll-triagem planos/_broll_triagem.json
python3 blocos_legenda.py --plano planos/ht_sem43_segunda.json --aplicar     # confere a borda de cada gancho
python3 escrever_legendas.py planos/ht_sem43_segunda.json planos/_rascunho_sem43_segunda/_legendas.json
```
Se o `blocos_legenda.py` mandar **TROCAR** algum gancho, peça outro ao agente e monte o plano de novo.
- **Ajuste fino:** o script grava sozinho no plano.
- **"Por que" escrito × "porque" falado:** costuma ser falso positivo do OCR.

### 5.6 Render: um vídeo por vez
```bash
caffeinate -m python3 lote_peles.py planos/ht_sem43_segunda.json --versao ORG AD
```
- **Tempo e memória:** cada vídeo leva ~1 min 45 s e usa ~1,2 GB de memória.
- **Vigia:** o lote tem um vigia. Se um render travar, ele mata e refaz. Se o vídeo passar de 195 MB, refaz mais
  comprimido, sem perder qualidade, porque o Publer recusa acima de 200 MB.
- **Não rode dois lotes ao mesmo tempo.**
- **HD externo:** o `caffeinate -m` impede o Mac de desmontá-lo no meio do lote.

Antes do lote inteiro, vale um **piloto**:
```bash
python3 montar_ht_peles.py planos/ht_sem43_segunda.json --so VD001_A --versao ORG
```

### 5.7 Conferir antes de postar
Abra as tiras em `$SAIDA_DIR/SEM43/segunda/_conferencia/`: 5 quadros por vídeo. Procure:
- legenda cortada no meio;
- palavra sobrando no fim do gancho;
- headline ilegível;
- clipe de B-roll que não deveria estar lá.

O relatório `_relatorio_*.json` aponta alertas como "ABRE NO PRETO" e "PASSOU DO LIMITE".

### 5.8 Organizar, montar a fila e agendar
- **Aprovação:** o `pasta_aprovacao.py` monta `saida/SEM43/aprovar/`, uma pasta por dia com os vídeos no horário em que vão ao ar, a legenda, a tira de quadros e o checklist `_aprovar.md`. Use a mesma grade (`--inicio`, `--por-dia`, `--intervalo`) do agendamento.
- **Fernanda:** 1 Reel por dia nas 3 versões (`--por-dia 3 --intervalo 180`, a partir das 12:00), na ordem por Reel, sem o `intercalar`.
```bash
python3 organizar_organico.py planos/ht_sem43_segunda.json
cd publicar
python3 fila.py montar ../planos/ht_sem43_segunda.json
cd ..
python3 ferramentas/pasta_aprovacao.py SEM43-segunda-ht --inicio "2026-10-19 12:00" --por-dia 3 --intervalo 180
cd publicar
python3 fila.py intercalar SEM43-segunda-ht        # todos os A, depois os B, depois os C
python3 publer_postar.py postar SEM43-segunda-ht --rede instagram --inicio "2026-10-19 19:00" \
    --intervalo 2 --por-dia 21 --simular            # confere horários, contas e legendas
python3 publer_postar.py postar SEM43-segunda-ht --rede instagram --inicio "2026-10-19 19:00" \
    --intervalo 2 --por-dia 21                      # agenda de verdade (Trial Reel MANUAL)
```
- **Limite do Publer:** 25 posts no Instagram por conta a cada 24 h, contando os carrosséis do dia. 21 vídeos + 2 carrosséis cabem.
- **Fila com nome único:** a fila de vídeos termina em `-ht`. Não reaproveite o nome de uma fila de carrossel.
- **Se faltar algum vídeo:** o `fila.py montar` avisa quais. Renderize os que faltam e rode de novo.

### 5.9 Vídeos brutos (ainda não postados)
Uma subpasta de `brutos/entrada/` = um vídeo final. Dentro dela vão os takes da fala (`.MOV`/`.mp4`, em qualquer ordem: eles são juntados pela hora de gravação) e as imagens de apoio, como o antes e depois.
```bash
python3 ferramentas/importar_brutos.py teste1        # normaliza, junta os takes e transcreve → id BR001
```
Peça ao Claude Code um agente seguindo `planos/_instrucoes_bruto.md` para `BR001`. Ele grava `dados/brutos/BR001_edicao.json`, com os trechos que ficam e onde entra a imagem. Depois:
```bash
python3 ferramentas/editar_bruto.py BR001             # versão SEM gancho → saida/brutos/BR001/sem gancho/
python3 ferramentas/novo_lote.py --semana SEM43 --dia terça --primeiro 8 BR001E
```
A partir daí, siga a rotina normal (5.3 em diante) com o id `BR001E` para as 3 versões com gancho.
- **Edição:** emendas com 0,30 s de pausa (o ritmo natural dela), enquadramento alternado (normal e 1,1×) a cada trecho e legenda palavra por palavra no terço de baixo.
- **Antes e depois:** sem limite no orgânico. Em vídeo para anúncio (`"para_anuncio": true` no `_edicao.json`), no máximo **2,5 s** por aparição, travado no script, porque o Meta barra acima de 3 s.
- **Ganchos:** os agentes não usam o `blocos_legenda.py` nesses vídeos (a legenda é nossa, sincronizada com a fala) e cortam pela fronteira das palavras.

### 5.10 Posts de foto (antes e depois em carrossel)
A Fernanda manda as fotos pela pasta **"Posts Fernanda"** do iCloud Drive, uma subpasta por post. Dentro de cada subpasta vão as fotos na ordem do carrossel (nome com "antes" vem primeiro, "depois" em seguida, o resto pelo nome) e, se ela quiser, um `legenda.txt`. Subpastas que começam com `_` são ignoradas. O `_COMO USAR.txt` da pasta explica isso para ela. Para ela enviar, compartilhe a pasta com ela no Finder (Compartilhar → Colaborar).
```bash
python3 ferramentas/importar_fotos.py FOTOS-SEM44                # 4:5 (1080×1350), HEIC → JPEG, sem EXIF/GPS
python3 ferramentas/importar_fotos.py FOTOS-SEM44 --lado-a-lado  # + capa ANTES | DEPOIS (posts com 2 fotos)
# olhe dados/fotos/FOTOS-SEM44/_conferencia.jpg e escreva as legendas vazias em dados/fotos/FOTOS-SEM44/Pnn/legenda.txt
cd publicar
python3 fila.py montar-fotos FOTOS-SEM44                         # recusa se faltar legenda ou foto
python3 publer_postar.py postar FOTOS-SEM44 --rede instagram --inicio "2026-10-27 10:00" --horarios "10:00" \
    --conta <id> --conta-confirmada "Fernanda Porto | Rejuvenescimento Facial" --simular
python3 publer_postar.py postar FOTOS-SEM44 --rede instagram --inicio "2026-10-27 10:00" --horarios "10:00" \
    --conta <id> --conta-confirmada "Fernanda Porto | Rejuvenescimento Facial" --max 1   # 1º de teste
```
- **Vai pro feed**, não é Trial Reel. Sai para os seguidores no horário marcado.
- **Horário:** use um horário que não tenha Reel. Horário já ocupado na conta é pulado para o dia seguinte.
- **Pasta já importada** é pulada. Para refazer, use `--de-novo "nome da pasta"`; a legenda já escrita é mantida.
- **CFM:** só foto com autorização escrita da paciente, legenda educativa, sem promessa de resultado e sem preço.

### 5.11 Limpeza semanal
```bash
python3 ferramentas/limpeza.py            # mostra o que sairia e quanto espaço libera
python3 ferramentas/limpeza.py --apagar   # manda para a Lixeira do Mac
```
Sai: sobras de render e de transcrição, vídeos de post que o Publer já publicou (agendado nunca sai) e o que estiver em `planos/_descartados.json`. Não toca em `dados/videos`, transcrições, edições, planos, filas nem na pasta do iCloud.

---

## 6. Estilos

| Estilo | Como fica | Precisa de |
|---|---|---|
| `dividida` (atual) | B-roll em cima, pessoa embaixo, legenda nova na emenda, headline de 4 s. Abertura alternando corte seco e flash. | `BROLL_DIR` e a triagem |
| `clean` | O Reel quase sem edição: puro, zoom só no gancho, ou caixa de texto do Instagram no meio. | nada a mais |
| `peles` | manchete (cartão + título), cinema (LUT + grão), dinâmica (zoom a cada frase + glitch) | kit de efeitos, LUTs, fontes pagas |

Troque o estilo com `--estilo` no `montar_plano_dia.py`.

---

## 7. Problemas comuns

| Sintoma | Causa e saída |
|---|---|
| `baixar_reels.sh` lista 0 Reels | A sessão do Instagram expirou. Abra o Instagram no navegador do `NAVEGADOR`, faça login e tente de novo. Na primeira vez, o macOS pede permissão para ler os cookies do Chrome: clique em "Permitir". |
| "chave ... não encontrada" | Grave a chave no Keychain (seção 2, passo 4) ou preencha no `config.env`. |
| Render parado sem usar CPU | É o vigia do `lote_peles.py` que resolve. Se acontecer fora do lote, mate o processo e rode o lote. |
| "caminho com dois-pontos ou aspas" | Renomeie a pasta do `SAIDA_DIR` ou do `BROLL_DIR`. |
| Publer recusa o vídeo | O vídeo passou de 200 MB ou o post passou de 25 em 24 h. Veja o log em `publicar/filas/*.instagram-lote.log`. |
| Rosto cortado na metade de baixo | Meça a janela de novo com `medir_janela.py` e rode o plano e o render só daquele Reel com `--so VDxxx_A --forcar`. |

---

## 8. Segurança e combinados da equipe

- **Chaves e cookies:** nenhuma chave fica no código. Elas ficam no Keychain ou no `config.env`, que está no
  `.gitignore`. Os scripts nunca imprimem chave, e a da ElevenLabs entra pelo stdin do `curl`.
- **Originais intocáveis:** os Reels originais e o acervo de B-roll de origem nunca são alterados. Tudo sai em
  pasta nova.
- **Vídeo publicado:** depois de publicado, não se sobrescreve. Uma versão nova é um arquivo com outro nome.
- **Antes de agendar:** confira as tiras e rode o `--simular`.

## 9. Mapa do repositório

```
config.exemplo.env    modelo da configuração (copie para config.env)
config.py / config.sh leitura da configuração (Python / zsh)
instalar.sh           confere e prepara a máquina
baixar_reels.sh       baixa os Reels mais recentes do perfil
transcrever_reels.sh  transcreve com ElevenLabs Scribe (usa scribe/)
checar_lancamento.py  barra Reel de lançamento, live ou Desafio
frases.py             frases cronometradas, para escolher os ganchos
blocos_legenda.py     confere a borda de cada gancho na legenda queimada (OCR)
montar_plano_dia.py   rascunhos dos agentes → plano do dia (estilo, abertura, B-roll)
lote_peles.py         render em lote, 1 por vez, com vigia
montar_ht_peles.py    render de 1 vídeo (todas as peles, inclusive a dividida)
montar_ht_hooks.py    biblioteca do corte do gancho
escrever_legendas.py  legenda do post + título, por vídeo
organizar_organico.py uma pasta por vídeo (mp4 + título + legenda)
kit_peles.py          gera o kit de efeitos (só com os pacotes pagos)
ranquear_reels.py     modo "campeões": ranqueia por curtidas + comentários
publicar/             fila e agendamento no Publer (vídeos e carrosséis de foto)
ferramentas/          novo_lote, normalizar_broll, triagem_broll, medir_janela, importar_fotos
planos/               modelo do plano + instruções dos agentes (o resto é local)
scribe/               chamada do Scribe + vocab.exemplo.txt (copie para vocab.txt, que fica fora do git)
fontes/               Inter (OFL)
```

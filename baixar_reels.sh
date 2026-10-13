#!/bin/zsh
# Baixa os N Reels mais recentes de um perfil do Instagram, com o json de metadados (data, curtidas, legenda).
# Usa o gallery-dl mais novo via uvx, com o yt-dlp junto (é ele que baixa o vídeo): o Instagram quebra o
# extrator com frequência e a versão do Homebrew fica pra trás (a 1.32.10 dava "redirect to home page";
# a 1.32.12, de 12/09/2026, corrigiu os extratores de posts e reels).
# A sessão vem do navegador (NAVEGADOR no config.env, ex.: "chrome" ou "chrome:Profile 3" = nome da PASTA do perfil).
# uso: zsh baixar_reels.sh [perfil] [quantidade]   (padrões: IG_PERFIL do config.env e 15)
set -u
source "${0:A:h}/config.sh"
perfil="${1:-$IG_PERFIL}"
quantidade="${2:-15}"
navegador="$NAVEGADOR"
base="$REELS_BASE"
mkdir -p "$base/videos"
lista="$base/lista_${perfil}.json"
selecao="$base/selecionados_${perfil}.txt"
galleryDl=(uvx --quiet --from "gallery-dl@latest" --with yt-dlp gallery-dl --cookies-from-browser "$navegador" -o sleep-request=2)

# 1) lista com metadados, sem baixar; a folga de 10 cobre Reel antigo fixado no topo da aba
echo "1/3 listando os Reels de @$perfil com a sessão do $navegador..."
"${galleryDl[@]}" -j --range "1-$((quantidade + 10))" "https://www.instagram.com/$perfil/reels/" \
  > "$lista" 2> "$base/erro_listagem.log"

# 2) escolhe os mais recentes por data, pra fixado antigo não entrar só por estar no topo
python3 - "$lista" "$quantidade" "$selecao" "$base/erro_listagem.log" <<'PY'
import json, sys
lista, quantidade, saida, log = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
try:
    mensagens = json.load(open(lista, encoding='utf-8'))
except (json.JSONDecodeError, FileNotFoundError):
    mensagens = []
reels = {}
for mensagem in mensagens:
    # no -j do gallery-dl, a mensagem do tipo 3 é um arquivo: [3, url, metadados]
    if isinstance(mensagem, list) and len(mensagem) >= 3 and mensagem[0] == 3 and isinstance(mensagem[2], dict):
        codigo = mensagem[2].get('post_shortcode')
        if codigo:
            reels.setdefault(codigo, mensagem[2])
if not reels:
    print(open(log, encoding='utf-8', errors='ignore').read()[-1500:])
    print("Não consegui listar os Reels. Se o erro for 'redirect', confira se esse perfil do navegador está logado no Instagram.")
    sys.exit(1)
escolhidos = sorted(reels.values(), key=lambda m: str(m.get('date')), reverse=True)[:quantidade]
with open(saida, 'w', encoding='utf-8') as f:
    for meta in escolhidos:
        f.write(f"https://www.instagram.com/reel/{meta['post_shortcode']}/\n")
print(f"2/3 {len(reels)} Reels listados, {len(escolhidos)} mais recentes selecionados:")
for meta in escolhidos:
    fixado = "  (fixado)" if meta.get('pinned') else ""
    print(f"   {str(meta.get('date'))[:10]}  {meta['post_shortcode']}  {meta.get('likes', '?')} curtidas{fixado}")
PY
(( $? == 0 )) || exit 1

# 3) baixa só os selecionados; o nome começa pela data pra ordem cronológica sair de graça
echo "3/3 baixando..."
"${galleryDl[@]}" --write-metadata -D "$base/videos" -f "{date:%Y-%m-%d}_{post_shortcode}.{extension}" -i "$selecao"
echo "\nPronto: $(ls "$base/videos"/*.mp4 2>/dev/null | wc -l | tr -d ' ') vídeos em $base/videos"

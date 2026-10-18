# Carregado pelos scripts .sh: lê o config.env da raiz (se existir) e põe os padrões.
# uso dentro de um script zsh:  source "${0:A:h}/config.sh"
PROJETO="${0:A:h}"
[[ -f "$PROJETO/config.env" ]] && { set -a; source "$PROJETO/config.env"; set +a; }
: "${REELS_BASE:=$PROJETO/dados}"
: "${IG_PERFIL:=drafernanda.porto}"
: "${NAVEGADOR:=chrome}"
: "${KEYCHAIN_ELEVENLABS:=elevenlabs-api-key}"
REELS_BASE="${~REELS_BASE}"

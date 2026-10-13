#!/bin/zsh
# Prepara a máquina pra rodar o projeto (macOS). Pode rodar de novo sem estragar nada.
# uso: zsh instalar.sh
set -u
cd "${0:A:h}"
ok()   { print -P "%F{green}ok%f   $1"; }
falta(){ print -P "%F{red}FALTA%f $1"; FALTOU=1; }
FALTOU=0

[[ "$(uname)" == "Darwin" ]] || print "aviso: feito pro macOS (Keychain, OCR do Vision). Em Linux, ver README."

# 1) programas
for p in ffmpeg ffprobe uvx python3 curl; do
  command -v $p >/dev/null && ok "$p" || falta "$p  ->  brew install $( [[ $p == uvx ]] && echo uv || ([[ $p == ffprobe ]] && echo ffmpeg || echo $p) )"
done
if command -v ffmpeg >/dev/null; then
  for f in movie lut3d vstack; do
    ffmpeg -hide_banner -filters 2>/dev/null | grep -q " $f " && ok "ffmpeg tem o filtro $f" || falta "ffmpeg sem o filtro $f (instale o ffmpeg do Homebrew)"
  done
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264 && ok "ffmpeg tem libx264" || falta "ffmpeg sem libx264"
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx265 && ok "ffmpeg tem libx265" || print "aviso: sem libx265 (só usado quando o vídeo passa de 195 MB)"
fi

# 2) pacotes Python
python3 -m pip install --quiet --user -r requirements.txt 2>/dev/null || python3 -m pip install --quiet --break-system-packages -r requirements.txt
python3 -c "import PIL, numpy" 2>/dev/null && ok "Pillow e numpy" || falta "pip install -r requirements.txt"

# 3) OCR (Vision da Apple): confere a legenda queimada dos ganchos
mkdir -p bin
if [[ ! -x bin/ocr_legenda || ocr_legenda.swift -nt bin/ocr_legenda ]]; then
  if command -v swiftc >/dev/null; then swiftc -O ocr_legenda.swift -o bin/ocr_legenda && ok "OCR compilado (bin/ocr_legenda)"
  else falta "swiftc (instale as ferramentas de linha de comando: xcode-select --install)"; fi
else ok "OCR (bin/ocr_legenda)"; fi

# 4) config
if [[ ! -f config.env ]]; then cp config.exemplo.env config.env; print "criei o config.env: ABRA E AJUSTE os caminhos antes de usar"; else ok "config.env existe"; fi
source ./config.sh
mkdir -p "$REELS_BASE/videos" "$REELS_BASE/transcricoes" "$REELS_BASE/audio" && ok "pastas de dados em $REELS_BASE"

# 5) segredos (só confere se existem; nunca mostra)
[[ -n "${ELEVENLABS_API_KEY:-}" ]] || security find-generic-password -s "$KEYCHAIN_ELEVENLABS" -w >/dev/null 2>&1 \
  && ok "chave da ElevenLabs" || falta "chave da ElevenLabs  ->  security add-generic-password -s $KEYCHAIN_ELEVENLABS -a $USER -U -w"
[[ -n "${PUBLER_API_KEY:-}" ]] || security find-generic-password -s "${KEYCHAIN_PUBLER:-reconecta-publer}" -a api-key -w >/dev/null 2>&1 \
  && ok "chave do Publer" || falta "chave do Publer  ->  security add-generic-password -s ${KEYCHAIN_PUBLER:-reconecta-publer} -a api-key -U -w"

# 6) B-roll (só pro estilo dividida)
if [[ -n "${BROLL_DIR:-}" && -d "${~BROLL_DIR}" ]]; then ok "B-roll em $BROLL_DIR"
else print "aviso: BROLL_DIR vazio ou inexistente; o estilo dividida precisa dele (README, seção B-roll)"; fi

(( FALTOU )) && print "\nresolva os itens FALTA e rode de novo." || print "\ntudo certo."

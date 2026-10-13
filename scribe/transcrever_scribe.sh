#!/bin/zsh
# Transcreve um WAV com ElevenLabs Scribe v2 (verbatim, timestamp por palavra). Chave: ELEVENLABS_API_KEY
# no ambiente/config.env ou, no Mac, no Keychain (serviço KEYCHAIN_ELEVENLABS, padrão elevenlabs-api-key)
# e o banco de grafias (vocab.txt) como keyterms. Nunca imprime a chave.
# uso: transcrever_scribe.sh <audio.wav> <saida.json> [vocab.txt]
set -u
AUDIO="$1"; OUT="$2"; VOCAB="${3:-$(dirname "$0")/vocab.txt}"
[[ -f "$VOCAB" ]] || VOCAB="$(dirname "$0")/vocab.exemplo.txt"   # o vocab.txt real fica fora do git
K="${ELEVENLABS_API_KEY:-}"
[[ -z "$K" ]] && K=$(security find-generic-password -s "${KEYCHAIN_ELEVENLABS:-elevenlabs-api-key}" -w 2>/dev/null)
[[ -z "$K" ]] && { echo "chave da ElevenLabs não encontrada (ELEVENLABS_API_KEY ou Keychain ${KEYCHAIN_ELEVENLABS:-elevenlabs-api-key}); veja o README"; exit 1; }
ARGS=()
while IFS= read -r t; do
  [[ -z "$t" || "$t" == \#* ]] && continue
  (( ${#t} < 50 )) && ARGS+=(-F "keyterms=$t")
done < "$VOCAB"
echo "keyterms: $(( ${#ARGS[@]} / 2 ))"
# a chave entra pelo stdin (-K -), não pela linha de comando: assim não aparece no `ps` enquanto o curl roda
print -r -- "header = \"xi-api-key: $K\"" | curl -K - -s -o "$OUT" -w "HTTP %{http_code} em %{time_total}s\n" \
  -F "file=@$AUDIO" -F "model_id=scribe_v2" -F "language_code=pt" \
  -F "timestamps_granularity=word" -F "diarize=false" -F "tag_audio_events=false" -F "no_verbatim=false" \
  "${ARGS[@]}" https://api.elevenlabs.io/v1/speech-to-text
python3 - "$OUT" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
if 'text' in d:
    ws=[w for w in d['words'] if w.get('type')=='word']
    print(f"palavras: {len(ws)} | idioma: {d.get('language_code')} p={round(d.get('language_probability',0),3)} | duração última palavra: {ws[-1]['end']:.2f}s")
    print("início:", d['text'][:160]); print("fim   :", d['text'][-160:])
else:
    print("erro:", json.dumps(d, ensure_ascii=False)[:600])
PY

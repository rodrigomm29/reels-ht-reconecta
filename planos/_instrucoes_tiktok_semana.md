# Rotina semanal do TikTok (tarefa agendada, toda segunda)

Projeto: /Users/rodrigomadruga/projetos/reels-ht (branch fernanda). Nunca imprima chaves; nunca agende sem o OK do Rodrigo.

1. `python3 publicar/tiktok_semana.py` (baixa os reels recentes do perfil, escolhe a versão vencedora dos Trials
   e monta `publicar/filas/TIKTOK-<data>.json` continuando o rodízio 12:30 / 19:30 / 21:00).
   Se o download do Instagram falhar (sessão do navegador), rode de novo com `--sem-baixar` e avise no resumo.
2. Se disser "Nada novo", avise o Rodrigo em uma linha (com o que está "Esperando", se houver) e pare.
3. Para cada item com `"legenda_pendente": true`: escreva a legenda do TikTok seguindo
   `planos/_instrucoes_legenda_tiktok.md` (leia a legenda do Instagram, a transcrição em
   dados/transcricoes/ e olhe 6 quadros do vídeo com ffmpeg). Grave em `legenda`, apague `legenda_pendente`
   e, se a fala tiver risco, preencha `alerta_fala`.
4. Mande ao Rodrigo (notificação) o resumo de `saida/tiktok/semana_<data>.md`: dia/hora, vídeo, motivo,
   primeira linha da legenda e alertas. Pergunte se pode agendar.
5. SÓ depois do OK dele: `python3 publicar/tiktok_semana.py --agendar TIKTOK-<data>`. Ele agenda no Publer
   (conta TikTok "Dra. Fernanda Porto") e atualiza `saida/tiktok/calendario_tiktok.md/.csv` para a recepcionista.

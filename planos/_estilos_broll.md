# Estilos de B-roll e foto que a Dra. Fernanda gosta (referências de 18/10/2026)

Tirado dos prints que o Rodrigo mandou (Reels dela e de referências de outros perfis). Ainda NÃO implementado,
exceto onde está marcado. Em todos vale a regra inegociável: **foto de antes, de depois ou de antes/depois no
máximo 2,5 s na tela**, somando aparições seguidas, **mas só em anúncio**. No orgânico não há limite.

| # | Estilo | Como é | Onde aparece | Status |
|---|---|---|---|---|
| 1 | **Janela sobre ela** | Foto quadrada ou 4:5, sem borda, no centro da tela, cobrindo o peito/tronco; ela continua falando e gesticulando em volta | Reel "Ela tem 50 anos…" | falta |
| 2 | **Janela arredondada** | Foto ou vídeo em cartão de cantos arredondados (~raio 40 px), largura ~60 % da tela, na metade de baixo; a legenda dela fica logo acima | Reel "Amei perder o ar de cansada" | falta |
| 3 | **Cartão grande de antes/depois** | Antes e depois lado a lado num cartão arredondado de ~90 % da largura, sobre o vídeo dela desfocado | Reels "Ela morria de medo…" e "Método AURA" | falta |
| 4 | **Foto em tela cheia** | A foto ocupa a tela toda; a legenda continua por cima | Reel "Ela tem 51 anos" | pronto (`editar_bruto.py`, imagens) |
| 5 | **Tela dividida, foto em cima** | A tela divide SÓ enquanto a foto do caso aparece (até 2,5 s no anúncio): foto em cima, ela embaixo; fora disso, ela em tela cheia. Nunca cena aleatória em cima (testado e reprovado em 18/10/2026) | Referências de outro perfil (o médico de terno) | pronto (`editar_bruto.py`, imagens com `"modo": "dividida"`) |
| 6 | **Janela no canto** | Foto pequena (~45 % da largura) no canto de cima, ao lado da cabeça de quem fala, que aponta para ela | Referências de outro perfil | falta |

Ideia de implementação: cada inserção no `_edicao.json` ganha `"modo"`: `tela_cheia` | `dividida` | `janela` |
`janela_arredondada` | `cartao` | `canto`. O agente de takes escolhe o modo por momento, variando ao longo do
vídeo (não repetir o mesmo modo duas vezes seguidas), e o `editar_bruto.py` monta cada um.

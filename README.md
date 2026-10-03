# Editor de Vídeos com IA

Editor local, estilo CapCut, focado em **vídeo falado**: você joga o vídeo cru, ele transcreve, corta pausas/hesitações/regravações sozinho, e você ajusta editando o **texto** em vez da timeline.

## Como usar

```bash
./iniciar.sh
```

Abre em http://localhost:8765. Na primeira execução instala as dependências (Python 3 do macOS já basta — o ffmpeg vem embutido).

Para ligar os recursos de IA, coloque sua chave no arquivo `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## O que ele faz

| Recurso | Como |
|---|---|
| Transcrição palavra a palavra | Whisper local (offline, roda no Mac) |
| Corte de pausas | Toda pausa maior que X segundos some (ajustável) |
| Corte de hesitações | "ahn", "hum", "éé"… cortados automaticamente |
| Limpeza com IA | Claude encontra regravações, falsos começos, gaguejos e falas de bastidor ("corta essa parte") e mantém só a melhor versão |
| Edição por texto | Selecione palavras → `Delete`. Clique duplo restaura |
| Inserções | Selecione palavras → **+ Mídia** (imagem/vídeo, tela cheia ou janela) ou **+ Texto** (título na tela). A inserção fica presa às palavras, então sobrevive a novos cortes |
| Sugestões com IA | Claude sugere títulos na tela (já aplicados) e ideias de B-roll com link de busca no Pexels |
| Transições | Corte seco, zoom alternado (punch-in estilo YouTube) ou suave (crossfade) |
| Legendas | Estilo "destaque" (palavra atual em amarelo), clássica ou sem |
| Formatos | Original, 9:16 (Reels/TikTok/Shorts), 1:1, 16:9 |
| Música | Com ducking automático (abaixa quando você fala) |
| Áudio | Normalização de volume para redes (-14 LUFS) |
| Exportação | MP4 H.264 usando o encoder de hardware do Mac |

## Estrutura

```
app/
  server.py      API (FastAPI) + jobs em segundo plano
  timeline.py    núcleo: palavras mantidas → trechos, mapeamento de tempo, legendas
  render.py      monta o comando ffmpeg (cortes, zoom, transições, inserções, legendas ASS, música)
  ai.py          chamadas ao Claude (limpeza e sugestões) com saída JSON estruturada
  transcribe.py  faster-whisper com timestamps por palavra
  media.py       utilitários de ffmpeg
  static/        interface (HTML/CSS/JS puro, sem build)
projects/        seus projetos (vídeo original, assets, exportações) — fora do git
```

O projeto salva só *quais palavras foram apagadas* + configurações + inserções. Todo o resto (trechos, tempos, legendas) é recalculado, por isso desfazer/refazer e mudar configurações é instantâneo e nada é destrutivo.

## Configuração

- `WHISPER_MODEL` no `.env`: `small` (padrão), `medium` ou `large-v3` para mais precisão (mais lento).
- `CLAUDE_MODEL`: padrão `claude-opus-5-5`.

# Editor de Vídeos com IA

Editor local, estilo CapCut, focado em **vídeo falado**. Você arrasta o vídeo cru e ele:

1. **transcreve** tudo o que foi dito (Whisper, no seu Mac, palavra por palavra);
2. **corta** pausas, hesitações, regravações e falas de bastidor;
3. **entende o roteiro** (gancho, seções, listas, números, nomes citados) e **monta um plano de edição**:
   títulos, palavras-chave, motions, efeitos sonoros, zooms, flashes, texto atrás de você, perspectiva 3D e B-rolls;
4. **corre atrás dos materiais** na internet: fotos reais (Wikipedia), acervos históricos (Wikimedia Commons),
   filmes antigos de domínio público (Internet Archive), NASA e **cards de manchete** de notícias reais;
5. exporta o MP4 com legendas, cor cinematográfica, voz tratada e créditos dos materiais.

Tudo isso é **100% gratuito** por padrão. Você ajusta o que quiser editando o *texto*, não a timeline.

## Como usar

```bash
./iniciar.sh
```

Abre em http://localhost:8765. Na primeira execução instala as dependências (o Python 3 do macOS basta; o ffmpeg vem embutido).
Para prints e motions é preciso ter o Google Chrome instalado.

## O "cérebro" (quem decide o plano)

| Motor | Custo | Qualidade |
|---|---|---|
| **Regras locais** | grátis | boa: listas, números, nomes próprios, ênfases, regravações |
| **Claude Code** | grátis com sua assinatura | ótima: ele lê o roteiro e escreve o plano (botão "Pedir ao Claude Code") |
| **Ollama** (IA local) | grátis | média/boa, roda no seu Mac — instale em ollama.com |
| **Claude API** | pago por uso (centavos por vídeo) | ótima, 100% automática — `ANTHROPIC_API_KEY` no `.env` |

### Editar conversando com o Claude Code

Abra o Claude Code nesta pasta e peça em português, por exemplo:
*"edita o projeto real_test: corta as pausas, deixa no formato 9:16 com look cinema e põe manchetes como prova"*.
O `CLAUDE.md` e as skills em `.claude/skills/` ensinam a ele a operar o editor (`app/cli.py`), gerar uma
**amostra**, olhar os quadros, corrigir e exportar.

## Recursos

| Recurso | Detalhe |
|---|---|
| Transcrição + edição por texto | selecione palavras → corta, ou insere mídia/texto/motion/som/zoom/3D ali |
| Corte inteligente | pausas (ajustável), hesitações, repetições, regravações, "corta essa parte" |
| Motions (HTML → vídeo) | lettering, ícone animado, lista explicativa, contador, comparação, card 3D, carrossel 3D |
| Composição | texto atrás da pessoa e fundo desfocado/escuro (recorte com IA local — MediaPipe), perspectiva 3D |
| Materiais | Wikipedia, Commons, Internet Archive, NASA, notícias (card de manchete), print de qualquer site, seus arquivos |
| Efeitos sonoros | 9 efeitos gerados localmente (whoosh, pop, ding, impacto…) + os seus na pasta `sfx/` |
| Transições | corte seco, zoom alternado, suave, flash, zoom de ênfase |
| Look | cinema, quente, frio, vívido, P&B, vintage |
| Áudio | voz de estúdio (ruído, EQ, compressão), música com ducking, normalização -14 LUFS |
| Formatos | original, 9:16, 1:1, 16:9 |
| **Referências → formato** | mande vídeos que você admira: ele mede ritmo de cortes, palavras/min, densidade visual, música, cor e gancho, e cria um formato que o planejador segue |

## Estrutura

```
app/
  server.py      API (FastAPI) + jobs em segundo plano
  cli.py         linha de comando (usada pelo Claude Code)
  timeline.py    núcleo: palavras mantidas → trechos, zoom por trecho, mapeamento de tempo, legendas
  rules.py       análise grátis do roteiro (limpeza + plano)
  brain.py       motores do plano (regras, Ollama, Claude Code, Claude API) e esquema único
  plan.py        aplica o plano ao projeto, busca automática de materiais
  sources.py     busca/baixa materiais, cards de manchete e prints (Chrome)
  motion.py      renderiza os templates de app/motion/*.html em PNG transparente (Chrome DevTools)
  segment.py     recorte de fundo (MediaPipe)
  reference.py   análise de vídeos de referência → formatos
  render.py      monta o ffmpeg final (camadas, look, áudio)
  sfx.py         biblioteca de efeitos sonoros
  static/        interface (HTML/CSS/JS puro, sem build)
projects/  formatos/  sfx/  models/   ← dados locais (fora do git)
```

## Licenças dos materiais

Wikipedia/Commons: licenças livres (ver página de cada arquivo). Internet Archive: filtrado para coleções de domínio
público. NASA: domínio público. Notícias: citação jornalística — a busca usa o RSS do Bing, que permite só uso pessoal;
para uso comercial, cole a URL da matéria. A exportação gera um `.creditos.txt` com autor/licença de cada material usado.

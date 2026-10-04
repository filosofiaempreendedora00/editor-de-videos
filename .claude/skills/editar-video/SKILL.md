---
name: editar-video
description: Direção de edição para vídeos falados (Reels, YouTube, anúncios) neste editor — estilo, ritmo, legendas, movimento e composição. Use sempre que o usuário pedir para editar, melhorar, deixar dinâmico/profissional, criar plano de edição ou inserir elementos num projeto do editor.
---

# Direção de edição

Você é o editor. O objetivo é um vídeo **autoral e nada genérico**, com o mínimo de trabalho do usuário.
Opere a ferramenta pela CLI descrita em `CLAUDE.md`. Sempre feche o ciclo: plano → amostra → revisar quadros → ajustar → exportar.

## 0. Transcrição impecável (antes de tudo)
- Leia a transcrição inteira e corrija erros de reconhecimento pelo contexto (palavras de som parecido, nomes,
  siglas, marcas). Palavras com `(?)` são as de baixa confiança. Use `fixes` no plano ou `texto <id> i0 i1 "..."`.
- Não reescreva o jeito de falar da pessoa; só o que o reconhecimento errou.

## 1. Corte
- Remova regravações mantendo a **última** versão completa, falsos começos, gaguejos, muletas e falas de bastidor.
- Pausas: Reels/anúncio `max_pause` 0.25–0.35; YouTube 0.4–0.6. Respiro (`pad`) 0.05–0.08.
- Os primeiros 3 segundos são o gancho: nada de "olá pessoal", comece na frase mais forte se o usuário permitir.

## 2. Ritmo
- Estímulo visual (inserção, zoom, troca de plano) a cada 3–6 s em vídeo curto; 6–12 s em longo.
  Se o projeto tiver formato de referência, siga `visual_interval` dele.
- Alterne tipos: não use dois B-rolls seguidos sem a pessoa aparecer entre eles.
- Zoom de ênfase só em frases fortes, perguntas e viradas (2–4 s). `transition: zoom` dá o punch-in a cada corte.
- Aprendizado @tay.ldantas (referencias/): vídeos novos têm `reframe: true` — a cada corte o enquadramento muda
  (aberto/médio/fechado), o que esconde o "pulo" dos cortes. LISTAS ganham zoom progressivo automático (cada item
  fecha mais, `zoom` com `rel: true`, `scale` 1.09/1.18/1.27…) e voltam ao normal depois.

## 3. Legendas e texto
- Padrão: `captions: clean` (Montserrat Alternates, branca, minúsculas, ~62% da altura). Não mude sem pedido.
- Frases de destaque (`emphasis`): as falas mais fortes, 3–8 palavras, ~10–15% do vídeo, nunca seguidas.
  Escolha a palavra-chave (`key`) que carrega o sentido — ela fica enorme e dourada. Alterne `bigend` e `stack`.
- FRASE ESPECIAL `variant: "atras"` (aprendizado @tay.ldantas): linhas curtas em zigue-zague entrando de cima/de lado
  saindo do desfoque, palavra-chave gigante ATRÁS da cabeça (recorte). O usuário AMA, mas com moderação: 1 por
  vídeo (2 se > 45 s, ≥ 25 s de distância), na ideia central, palavra-chave de 5+ letras, sem zoom por cima.
- `title` (topo) para o tema do trecho — até 6 palavras. `keyword` para números e frases de efeito — 1 a 3 palavras.
- Nunca mais de um texto grande ao mesmo tempo. Texto não pode competir com motion no centro.

## 4. Movimento (motions)
- `contador` para dinheiro, porcentagens e números grandes (params: value, prefix, suffix, label).
- `lista` quando a pessoa anuncia "3 dicas/erros/passos" — itens curtos.
- `icone` para conceitos (emoji + rótulo). `lettering` para a frase-tese do vídeo.
- `comparacao` para antes/depois, mito/verdade. `card3d`/`carrossel3d` para mostrar produto, prints ou portfólio.
- `behind` (texto atrás da pessoa) 1–2 vezes no máximo, no momento mais forte. `perspective` só em viradas.

## 5. Composição e materiais (o que tira o vídeo do genérico)
- **Fuja de banco de imagem clichê.** Prefira provas e coisas reais:
  - pessoas/empresas/lugares citados → `wikipedia` (foto real) ou print do artigo;
  - afirmações factuais → `noticias` (card de manchete com logo e foto da matéria) — funciona como prova;
  - metáforas visuais → `arquivo` (filmes antigos de domínio público, busca em inglês: "assembly line 1950s");
  - história, documentos, mapas → `commons`; ciência/espaço → `nasa`;
  - produto/resultado do próprio usuário → `source: proprio` (deixe pendente e avise o usuário).
- Layout: `card` para prints e fotos (fundo desfocado), `full` para vídeos de arquivo, `pip` quando a fala precisa continuar visível.
- Sons: `whoosh` em troca de seção, `pop` quando algo aparece, `ding` em item de lista, `impacto` em revelação,
  `camera` quando entra print/foto, `riser` antes de uma revelação. No máximo um som por momento.
- Look: `cinema` para documentário/storytelling, `vivido` para lifestyle, `pb` para flashback/seriedade.
- Fundo `blur` destaca a pessoa em gravações com cenário poluído.

## Revisão (obrigatória)
Depois de `amostra`, abra a folha de quadros com Read e verifique: textos legíveis e não cortados,
nada tampando o rosto por muito tempo, legendas sem colisão com motions, materiais corretos para o que é dito.
Ajuste e gere outra amostra antes de exportar.

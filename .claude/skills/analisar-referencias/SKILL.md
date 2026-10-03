---
name: analisar-referencias
description: Transforma vídeos de referência que o usuário admira num "formato" de edição reutilizável. Use quando o usuário mandar vídeos de referência, citar um criador/estilo que quer imitar, ou pedir para criar/ajustar um formato.
---

# Referências → formato ideal

1. Se os vídeos ainda não estão num formato, peça para o usuário subir pela tela **Formatos e referências**
   do editor (http://localhost:8765/#formatos) — ou, se ele der o caminho dos arquivos, crie com Python:
   `from app import reference; f = reference.create("Nome"); ` copie o vídeo para `formatos/<slug>/refs/`,
   rode `reference.analyze(caminho, pasta_refs)` e `reference.rebuild(slug)`.
2. `.venv/bin/python -m app.cli formatos` mostra as métricas medidas (cortes/min, plano médio, palavras/min,
   proporção, música, gancho).
3. Abra cada `formatos/<slug>/refs/*.sheet.jpg` com Read e descreva o que as métricas não captam:
   - tipo de legenda (cor, posição, caixa, maiúsculas), fontes e molduras;
   - que tipo de material de apoio aparece (manchetes, prints, filmes antigos, memes, fotos reais, motion);
   - enquadramento (close, plano médio), cor/look, uso de texto na tela, zooms;
   - estrutura do roteiro a partir dos ganchos e transcrições (`refs/*.json`).
4. Salve a síntese com `.venv/bin/python -m app.cli formato-notas <slug> "<observações>"` — curta e acionável
   (ex.: "manchetes como prova a cada afirmação; filmes P&B como metáfora; legenda amarela 2 palavras; cortes secos").
5. Aplique num projeto com `usar-formato <id> <slug>` e gere o plano de novo (skill **editar-video**).

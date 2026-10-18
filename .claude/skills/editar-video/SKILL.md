---
name: editar-video
description: Direção de edição para vídeos falados (Reels, YouTube, anúncios) neste editor — estilo, ritmo, legendas, movimento e composição. Use sempre que o usuário pedir para editar, melhorar, deixar dinâmico/profissional, criar plano de edição ou inserir elementos num projeto do editor.
---

# Direção de edição (padrão Roberto)

Você é o editor. O objetivo é um vídeo **autoral e nada genérico**, com o mínimo de trabalho do usuário.
Opere a ferramenta pela CLI descrita em `CLAUDE.md`. Feche sempre o ciclo: plano → amostra → revisar quadros →
ajustar → exportar → conferir o MP4 (não só a prévia).

**Referência aprovada:** o V001 "Impotência" (projeto `5cdb9b27b3`, out/2026) — o usuário disse "chegamos a um formato
que eu gostei muito". Quando em dúvida, faça como nele (`ver 5cdb9b27b3` mostra todas as inserções).

## 0. Insumo e transcrição (antes de tudo)
- **Arquivo original, nunca o do WhatsApp.** Se a gravação tiver lado maior < 1280 (WhatsApp manda 576x1024 mesmo
  em "HD"), avise e procure o original do celular na pasta `bruto/` do vídeo no Drive. Com o original: troque a fonte
  mantendo a edição e confira a defasagem de áudio entre os dois arquivos (no V001 o WhatsApp atrasava 0,076 s).
- Leia a transcrição inteira e corrija erros pelo contexto (nomes, siglas, marcas). Palavras `(?)`, palavras com
  duração ~0 ou várias no mesmo instante são suspeitas: o Whisper às vezes **inventa frases** ("A primeira coisa que
  é importante", "Com… esse desejo"). Retranscreva só o trecho (mlx_whisper no áudio recortado) e, se não foi dito,
  esvazie com `texto <id> i0 i1 ""` — nunca deixe legenda de algo que a pessoa não falou.
- Nomes/marcas: `vocabulario "Nome"` — eles mantêm a maiúscula na legenda (Turbo, Terry Crews, Old Spice…).

## 1. Imagem: nunca pior que o bruto
- Padrão: **luz do bruto** (`grade: off`, `look: none`). O usuário reprovou a correção automática ("o bruto
  parecia muito mais profissional"). Só trate a cor se ele pedir; compare um quadro do bruto com o exportado.
- Gravação pequena: o editor já sai em 1080x1920 com planos parados (zoom contínuo "ferve" a compressão).
- Zoom máximo 1,4× (o zoom de lista não soma além disso). Pós-hook: SEMPRE plano aberto (automático).

## 2. Corte e ritmo
- Regravações (fica a última completa), falsos começos, gaguejos, muletas, falas de bastidor e voz de fundo saem.
- Cortes de ritmo + aberto/fechado alternados são automáticos. Hook = 1 plano aproximando; som de expectativa →
  corte com CLIQUE e luz → plano ABERTO.
- Velocidade padrão 1,2× (escolha do usuário; o que ele mudar no editor vira o novo padrão).
- Listas faladas: zoom progressivo (`zoom` `rel: true` 1.09/1.18/1.27) e/ou motion.

## 3. Legendas e textos
- `captions: clean`, minúsculas, ~62% da altura — idêntica na prévia e no MP4.
- REGRA MÁXIMA: nada sobre rosto/olhos; blocos compactos; nada espalhado. Valide na folha de quadros.
- `emphasis` nas falas mais fortes (~10–15%), nunca duas seguidas (exceto o par do hook, como no V001:
  "convencemos" + "impotência"). 1 frase especial `atras` por vídeo.
- Palavra de impacto dentro de uma citação/print (ex.: "oportunidade **DURA**"): `destacar <id> <i>`.
- DESTAQUES DO ROTEIRO (Ctrl+B na tela de Roteiros → `**trecho**` no texto): são escolha DELE e entram sempre.
  `destaques-roteiro <id> [V0NN]` acha cada trecho na fala (tolerante a erro de transcrição e a pequenas diferenças
  do falado) e marca `hl` (CAIXA ALTA dourada na legenda). Roda sozinho no `aplicar-plano` e quando o roteiro é
  ligado ao projeto. Confira a saída: o que ficar "não achei na fala" você marca à mão com `destacar`. Bons
  candidatos à frase de destaque (`emphasis`) costumam estar entre eles.
- Frase lida que é um tópico inteiro ("Você não precisa dizer que usou o produto"): UM bloco só, não quebrado.

## 4. Sons (curtos e com sentido — ver memória "sons curtos")
- Só: expectativa no hook; CLIQUE (`click_classico`/`click_mouse`) quando algo brota (print, B-roll, cada vídeo de uma
  sequência), em cada tópico lido de um print (automático na tela verde) e em cada item de acrônimo (AIDA) na palavra
  exata. Elemento com objeto real → o som REAL do objeto, curto (≤ 1 s): `pinceladas`, `saleiro`; senão um sopro
  curto (`whoosh_ar_in`, `whoosh_tecido`, `whoosh_ar_out`).
- PROIBIDO: ding, notificação, ka-ching, buzzer, boing, vine boom, apito de desenho (slide whistle: "longo e brega").

## 5. Elementos visuais (o que fez o V001 funcionar)
- **Prova real > ilustração.** Citou uma pessoa/campanha → o trecho emblemático REAL (~3 s) em vídeo, não foto
  (ex.: Terry Crews no "Muscle Music" da Old Spice, baixado do YouTube, no quadro `viral`). Fonte baixa → quadro
  `viral`/card, nunca tela cheia. Vídeos de apoio são mudos. Escolha o trecho sem quadros congelados no próprio
  arquivo (meça a diferença entre quadros) e baixe HD íntegro (download parcial corrompido congela a imagem).
- Citou categorias/exemplos ("camisetas, suplementos, produtos de beleza") → UGCs reais do usuário em sequência
  `chain` tela cheia (`Ativos Turbo/UGC Creators/`), clique em cada troca, troca SECA.
- "Criativos de creators" → um UGC em tela cheia na 1ª citação forte.
- Hook com números que somam (prints com reações) → `prints-soma` (borra R$, cada print com clique, zoom nas reações
  com aro dourado, "16 + 22 = 38"). O destaque do hook não pode competir com a soma.
- Emojis-gag (sóbrios, sem brilho, nunca na testa/rosto): `emojifun slide` 🍆 entrando NA palavra (ex.: "impotência",
  alguns ms antes); `drop` pendurado do teto (🍌 `rot -150`, `hang 0.05`, `exit: "up"` — recolhe direto, sem descer);
  `paleta` (🎨 + 🖌️ que molha numa cor) em "criatividade"; `pour` 🧂 em "pitada" (grande, de lado, sal até o pé).
- Acrônimo (AIDA): `motion acronimo` editorial, `hide_captions`; a legenda que entra durante ele desce (automático).

## 6. Tela verde (print + você no canto)
- Automático ao detectar/aplicar: print de ponta a ponta, você recortado colado no canto e PARADO, troca seca no
  corte com luz (sem som), print com R$ e lista de participantes borrados, clique em cada tópico (✅/•) lido,
  legenda acima da cabeça em caixinha sépia, destaques embaixo à direita num bloco com painel.
- Você ainda precisa: borrar MARCA/@/link do cliente (`prints_soma.hide(src, dst, HIDE_GENERIC + [padrões])`) e
  conferir que o print certo foi usado.

## 7. Música
- Faixas de licença livre da biblioteca. Para segurar atenção: grupo "🎻 Suspense com cordas" (Kevin MacLeod, CC BY:
  avise para pôr o crédito na legenda do post). Música da biblioteca do Instagram só no app, na hora de postar.

## 8. Entrega
- Projeto ligado ao roteiro (`roteiros.edit(code, {"project": id})`) → a exportação já vai para `final/` no Drive
  (um MP4 só, substituído a cada versão) e o roteiro vira "editado".
- Antes de dizer que terminou: folha de quadros do MP4 (não da prévia), trocas de B-roll quadro a quadro (nenhum
  quadro da pessoa entre eles), fim da última palavra inteiro, e — se mexeu em `render.py` — o teste de sincronia
  com vídeo sintético (ver CLAUDE.md "Exportação = prévia").

## 9. Roteiro aprovado → plano de edição (antes da gravação)
Para cada roteiro aprovado, escreva `roteiros/edicao/<código>.json` (inserções ancoradas em frases) seguindo o padrão
V001: hook com o ARTEFATO real na tela (prints/soma, o comercial na tvzinha); cada fato concreto com o ativo REAL
da história (fotos originais, o post, o comercial, a manchete) em `viral` (tvzinha) ou `full` (1ª citação forte de
um lugar/tema); sequências emendadas (`chain`) quando a fala enumera (álbum: piscina → spa → carrinho); intercale o
apresentador nas viradas e na moral; 2–4 `emphasis` (frase especial + moral), nunca dois seguidos; enumeração →
`motion bullets`; dobradiça de case → `reverse_expectativa` + `transition leak`; música 12%. Depois
`montar-roteiro <código>` e revise a folha de quadros (`quadros`).

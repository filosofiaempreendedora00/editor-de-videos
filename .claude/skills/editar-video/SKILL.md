---
name: editar-video
description: Direção de edição para vídeos falados (Reels, YouTube, anúncios) neste editor — estilo, ritmo, legendas, movimento e composição. Use sempre que o usuário pedir para editar, melhorar, deixar dinâmico/profissional, criar plano de edição ou inserir elementos num projeto do editor.
---

# Direção de edição (padrão Roberto)

Você é o editor. O objetivo é um vídeo **autoral e nada genérico**, com o mínimo de trabalho do usuário.
Opere a ferramenta pela CLI descrita em `CLAUDE.md`. Feche sempre o ciclo: plano → amostra → revisar quadros →
ajustar → exportar → conferir o MP4 (não só a prévia).

## §0 RECEITA CONSOLIDADA — leia ANTES de tudo (destila §1–14 e as observações do Joshie/Liquid Death)
Quando chegar a gravação dele de um roteiro com plano (`roteiros/edicao/<código>.json`): suba o projeto, rode
`aplicar-edicao <pid> <código>`, depois `lacunas`, `exportar` e
confira a folha de quadros de TODA inserção (`montar_roteiro.lacunas` + extrair um quadro do meio de cada overlay).
Sem plano ainda: escreva-o seguindo isto:

**1. Ritmo visual (a regra que mais pesa)**
- Nunca > 5–7 s só ele falando sem algo visual. Única pausa aceitável: a virada da história (contraste).
- REGRA PARA SEMPRE (V008, 18/10): a cara dele "solo" NUNCA fica entre B-rolls nem entre telas divididas — "broll
  broll broll, ou dividida dividida dividida". Ativos a < 24 palavras (`SOLO_MIN_W`, ~7 s) se emendam e o anterior
  fica até o próximo chegar; ele só volta sozinho para um bloco de fala dele de verdade (≥ ~7 s) ou para uma frase de
  destaque (o ativo encosta nela), e a volta tem transição COM som. Cubra o buraco com ativo que bata com a FALA
  daquele trecho — esticar um ativo sobre outra ideia ("energético" sobre "mas a água não") também é erro. Transição (desfoque + clique de câmera) só ao ENTRAR numa cena; dentro
  de um bloco 50/50 os ativos trocam em cima SEM transição nem som. Nunca "whoosh/vento".
- Exemplos/enumerações = um B-roll por exemplo, SEGUIDOS, sem o rosto dele no meio, até o fim da frase.

**2. Cada ativo bate com a fala, literalmente, e é REAL**
- Ativo da própria história primeiro (foto original, o comercial, a manchete, a gravura/estátua/edição histórica no
  Commons); banco de imagem só para o genérico, preferindo mãos/objeto/detalhe a gente posando.
- "filhO" = menino; nunca dois B-rolls parecidos seguidos; sem spoiler (o ativo só entra depois do fato na fala).
- QUALIDADE: genérico abundante só em HD (≥1080p) ou foto em alta; baixa qualidade só para o que é único.

**3. Formato de cada ativo (5 tipos de cena: ele · B-roll · tvzinha · dividida 1 · dividida 2, + duo e tv)**
- `full` só com VERTICAL de verdade (vertical nativo, HD ≥ 1080p com corte 9:16 conferido = `crop_ok`, ou foto em alta).
- (18/10, Joshie) A tela dividida "cabeça invadindo" (`topo`) SAIU: dava cabeça fantasma/bugada. Toda tela dividida é
  o 45/55 (`meio`), a cabeça dele NUNCA invade a faixa de cima, e um bloco seguido mantém o MESMO layout. A legenda
  fica na posição NORMAL (terço de baixo) em toda tela dividida/duo/TV — na divisa ela parecia "cortada".
- PREFIRA VÍDEO a foto. Foto: nunca cortada (quadrada/horizontal → tvzinha na proporção dela) e sempre com zoom in
  lento (6%, render e prévia). Listas faladas ("o seu preço, o seu produto, o seu argumento") = estética do AIDA
  (`acronimo` com `final: false`: inicial dourada + fio + palavra em versalete) + `click_classico` em cada item.
- Horizontal bom → 50/50 (`meio`: o ativo PREENCHE a faixa de cima 45%, ele embaixo 55% no máximo; o desfoque é SÓ a linha
  da divisa — blur gigante em cima/embaixo foi reprovado; o que sobra na largura é cortado do lado sem importância com
  `fx` 0..1, ex.: nome do Mike à esquerda → `fx: 0`; olhe um quadro de cada ativo com a janela de ~75%). A legenda
  fica SEMPRE NA DIVISA, na caixinha sépia (regra dele, reprovado 2× com a legenda no alto: `cap_y` não existe mais);
  se a base do ativo tem texto que importa (nome, manchete), escolha outro trecho/recorte (`fx`, `clip_start`).
- `viral` (tvzinha) para fotos/prints e coisas quase quadradas, na proporção do ativo, legenda SEMPRE embaixo; vídeo
  largo vai para o 50/50. `tv` = TV DE VERDADE numa sala (Mixkit 9612 em `backgrounds/tv_sala.mp4`: TV no rack, abajur,
  câmera passeando; o comercial cobre a tela verde) na faixa de cima, ele embaixo — a TV desenhada foi reprovada
  ("cara de IA"). Comercial com planos curtos: `shot_end` (detectado sozinho) segura o plano escolhido, toca até 0,55×
  e congela — nunca escorrega para a cena seguinte (a viatura no lugar da lata); escolha `clip_start` no início do
  plano (mapa de planos com `select='gt(scene,0.3)'`) e `fx` para o objeto da fala. `duo` para dois ativos (ex.: o escravo × o
  imperador; o celular × a turma no bar). O apresentador nunca vai dentro da tvzinha.
- Bordas de toda inserção encostam nos cortes (sem fatia de 2–3 quadros do enquadramento anterior).

**4. Texto**
- Legenda 4,4% da altura, minúscula, terço de baixo (~72%) — com ele sozinho E nas telas divididas; nunca no rosto.
- Destaques (`emphasis`) 3–5 por vídeo, nunca dois seguidos: gancho, frase-tese, número/virada, fecho. Gancho pode ir à
  direita (`align: right`). O negrito do roteiro vira destaque dourado da legenda sozinho.

**5. Gancho**: elementos NA TELA (como os prints+soma do V001; `hook_cards` com quadros reais, etiqueta, carimbo,
número grande) ou a frase inteira em destaque — nunca um 50/50 genérico. TUDO no bloco de baixo (~58–90%), rosto
livre; dinheiro = odômetro (dígitos rolando) numa placa de cédula; carimbo de borracha de verdade (tinta falhada,
borda dupla, bate e o card treme); o card anterior e a etiqueta SAEM quando o próximo card entra.

**6. Ideias abstratas** (cérebro, memória, slogan): ativo realista/3D ou motion próprio caprichado e sóbrio
(`slogan`, `riscados`…) — nunca desenhinho, nunca lista de tópicos para exemplos concretos. Frase impressa num
produto: ache a foto/vídeo REAL em que ela aparece (OCR nos quadros dos vídeos de apoio: `app/ocr.py`) e marque-a
(`slogan` com `box`: aro dourado em volta do texto impresso + o resto escurece + slogan grande + tradução) — nunca
escrever o texto por cima de uma lata que não o tem.

**7. Som e música**: só o som de expectativa no fim do gancho/dobradiça + cliques de câmera nas entradas de cena e nas
fotos em sequência. Música ANIMADA que retém, 12% (`mk_hip_hop_02`, `mk_sweet_september`); nunca suspense.

**7b. Ensaio (voz de IA)**: confira a transcrição contra o roteiro — o reconhecimento inventa palavras em pausas
("Então,", "Por isso,"), duplica trechos com duração zero e PERDE nomes ("Carl Jung"); o corte automático pode tomar
uma frase do roteiro por regravação (frases que começam igual): `aplicar-edicao` restaura sozinho no ensaio
(`cortes_do_roteiro`) e avisa na gravação real. Arquivo real em baixa resolução (360p) → só na tvzinha.

**8. Antes de entregar**: folha de quadros de TODAS as inserções + `lacunas` vazio + observações dele resolvidas com
`resolver-obs` dizendo o que foi feito; abra a foto de cada observação (`projects/<id>/obs/`).

**Referência aprovada:** o V001 "Impotência" (projeto `5cdb9b27b3`, out/2026) — o usuário disse "chegamos a um formato
que eu gostei muito". Quando em dúvida, faça como nele (`ver 5cdb9b27b3` mostra todas as inserções).

## §0b CRIVO DO ROBERTO (observações do Joshie real, 19/10 — confira ANTES de entregar)
1. **Som só com evento**: clique/"flash de câmera" só quando algo aparece ou há transição real. A timeline faz os
   sons de cena seguirem a cena DE VERDADE (`_sync_scene_fx`); confira com a auditoria (som × borda de ativo ≤ 0,1 s).
2. **Tela dividida**: legenda SEMPRE entre as duas cenas (na divisa, caixinha sépia); ele PARADO embaixo (sem zoom
   suave no trecho); ao entrar, só a transição normal. O pós-hook é dele: nenhum ativo é puxado para dentro dele.
3. **Lettering grande**: frase de destaque ≤ 7 palavras (ponta = palavra-chave), letras ≥ ~5,5% da altura; lista
   estilo AIDA grande; palavra de emoção pede lettering especial (ENCANTADO → destaque próprio; MAIS → `destacar`).
4. **A fala vence o roteiro**: itens de lista/lettering usam as palavras FALADAS na gravação.
5. **Nada monótono**: ativo parado muito tempo cansa — quebre com outro ativo REAL (ex.: foto do álbum); B-roll
   puro em tela cheia quando a fala pede (o "mundo").
6. **Momento-chave = motion de impacto** (ex.: `polaroid` — foto real caindo em 3D, assentando sem quique e
   revelando, com som de câmera ao assentar).
7. **A prévia é o que ele avalia**: proxy 1080p (720p "fervia" com o zoom = tremido); cópia da gravação conferida
   byte a byte (Drive zerou 4 MB e "bugou" um quadro).
8. **Estalo + cenário**: o estalo É a transição do gancho (sem a luz/clique do pós-hook por cima); cenário pode ser
   VÍDEO (`estalo <id> safari`: girafas reais em câmera lenta, dia de sol no brilho dele).

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

## 10. FORMATO DOS ATIVOS (regras dele, 2026-10-18 — valem para TODO vídeo)
- **Tela cheia (`full`) SÓ com ativo VERTICAL de verdade.** Horizontal nunca é esticado/cortado na tela toda (fica
  borrado e perde metade da cena). B-roll VERTICAL é "ultra mega importante": procure primeiro vertical (Mixkit/Pexels
  filtrando vertical, Reels/TikTok/Shorts da própria marca); ele SEMPRE sobrepõe você na tela inteira.
- **Ativo horizontal bom → `meio` (45/55, ver §0):** [o antigo `topo`, com a cabeça invadindo o ativo, foi ABOLIDO em
  18/10]. `aplicar-edicao` converte sozinho `full` horizontal → `meio` (vídeo) ou `viral` (foto).
- **Ou → `viral` (tvzinha):** qualquer formato cabe no quadrado. **100% das vezes a legenda DESCE para baixo do quadro**
  (~80% da altura) — `timeline._lift_over_greenscreen`.
- **A tvzinha NUNCA é para o apresentador:** quem fala (você/avatar) fica na tela inteira, com zoom in/out e cortes de
  ritmo. Pessoa falando DENTRO do quadrado = só se for o próprio ativo (ex.: a atriz do comercial banido).
- Avatar provisório (antes da gravação dele) = a gravação DELE do V001, sem som — fica claro o que é ele e o que é B-roll.

## 11. Ritmo visual e acabamento (revisão do Joshie, 2026-10-18 — valem para TODO vídeo)
- **Nunca mais de 5–7 s só ele falando sem nada visual** (dopamina). Rode `montar_roteiro.lacunas(pid)` e preencha
  cada trecho: B-roll, tvzinha, tela dividida, motion próprio (ex.: `cerebro`, `riscados` riscar/copiar) ou destaque.
  A única pausa aceitável é a virada da história (contraste).
- **Motions PRÓPRIOS para ideias abstratas** (cérebro, memória, comparação), editoriais e sóbrios na paleta Kronos —
  nunca "cara de IA"/commodity. Templates em `app/motion/` (`cerebro`, `riscados`, `acronimo`, `bullets`…).
- **Legenda padrão:** 4,4% da altura (não encosta nas laterais) e no terço de baixo (~72%) quando é só ele (longe da
  boca). Tvzinha → abaixo do quadro (o quadro toma a proporção do ativo, `ar`, e a legenda acompanha). Tela dividida 1
  → ~84%. Tela dividida 2 (50/50) → EXATAMENTE na divisa (50%), sobre o desfoque.
- **Telas divididas pela altura REAL da cabeça** (`head`, Vision, medida no `aplicar-edicao`): no estilo 1 o alto da
  cabeça SEMPRE invade ~7% o ativo; no 50/50 a cabeça fica logo abaixo da divisa (mostra o corpo).
- **Sons de troca de cena: câmera e clique** (`camera_mirrorless`, `click_mouse`, `click_classico`) — ele NÃO gosta do
  "vento" (whoosh).
- **Foto que não é quadrada não é cortada na tvzinha:** o quadro toma a proporção do ativo.
- **Imagens a ≤ 2 palavras uma da outra ficam emendadas** (senão ele aparece 1–3 quadros na pausa = "frame bugado").
- **Música no estilo das referências** (Demucs separou a trilha delas: 70–80 BPM, batida discreta, grave quente, pouco
  agudo). Pílula/história → `mk_curiosity` (ou `mk_tides_turning`); case (Beirão) → `long_note_four`. Nunca piano
  alegre tipo "Inspired".

## 12. Menos vaivém, nada cortado, vertical HD (revisão do Liquid Death, 2026-10-18)
- **Blocos 50/50 contínuos:** ativos horizontais em sequência (≤ 8 palavras entre eles) = UM bloco de tela dividida;
  ele fica embaixo e os ativos trocam em cima SEM transição nem som. Trocar de cena a cada frase "ficou exagerado".
- **Transição só ao ENTRAR numa cena** (desfoque + clique de câmera discreto); voltar para ele é corte seco, sem som.
  Clique só quando fotos se sucedem na tvzinha.
- **Tvzinha não corta nada:** o quadro toma a proporção do ativo; vídeo LARGO (programa de TV, ar > 1,35) vai para o
  50/50 em vez da tvzinha (o Mike e a apresentadora ficavam cortados).
- **B-roll VERTICAL de verdade faz falta:** use HD (≥ 1080p) com corte central 9:16 CONFERIDO na folha (assunto
  inteiro dentro) — marque `crop_ok: true` no plano. Nunca 360p em tela cheia. Ex.: as cenas da lata em HD
  (`lata_hd.mp4`: 1 s lata branca, 13 s respingo, 7 s cirurgião, 11 s juiz, 18 s latas no gelo, 4 s mão abrindo).

## 13. Observações do Joshie (2026-10-18) — sentido e acabamento
- **Sem spoiler:** um ativo só aparece DEPOIS de o fato acontecer na narração (a foto do Joshie na espreguiçadeira
  só entra quando o hotel já fez o álbum — no "pedido do pai" entra uma espreguiçadeira vazia).
- **O ativo tem de bater com a fala, literalmente:** "filhO" = menino, não menina; nada de B-roll "parecido demais"
  com o anterior (duas crianças seguidas incomodou).
- **Ideia abstrata (cérebro) pede ativo realista e caprichado** (3D/real), não desenhinho em traço.
- **Exemplos concretos = um B-roll VERTICAL para cada exemplo**, não lista/tópicos animados ("esteticamente muito
  feio"). Lista animada só para conceitos sem imagem.
- **Menos cara de banco de imagem:** prefira mãos/objeto/detalhe e cenas naturais a gente posando em grupo.
- **Cena que conta uma ação dura o tempo da ação** (a caixa chegando vai até "Dentro, estava o Joshie"); cena longa
  demais numa foto só → divida com outro ativo (ex.: "rodou o mundo" ganhou um ativo de internet/mundo).
- **Bordas das inserções encostam nos cortes** (`timeline._snap_to_cuts`): nada de fatia de 2–3 quadros com o
  enquadramento anterior antes de um salto de zoom.
- **50/50 em largura total** (nada de tarja preta nas laterais); recorte da cabeça em ALTA qualidade
  (`recorte-hq <pid>`: Vision + filtro guiado, em pedaços de 20 s) antes de exportar vídeo com tela dividida 1.
- Frase do gancho pode ir alinhada à direita (`align: "right"` no `emphasis`).

## 14. Rodada 2 do Joshie e do Liquid Death (2026-10-18)
- **QUALIDADE PRIMEIRO:** ativo abundante na internet (mundo, cidade, comida, gente…) tem de ser em ALTA qualidade
  (1080p+ ou foto em alta, ex.: NASA/Commons). Baixa qualidade só para algo hiper específico e único da história
  (o comercial banido, o post original). Nunca 720p ampliado em tela cheia.
- **Exemplos/enumeração = B-rolls SEGUIDOS, sem o rosto dele no meio** — o último vai até o fim da frase
  ("…do filho dele"). Padrão de edição coeso, nada de ele aparecer "aleatoriamente".
- **Tela dividida 1:** a faixa de cima toma a altura EXATA do ativo (16:9 → 31,6% da tela), sem sobra desfocada; a
  cabeça dele SOBE se precisar para invadir ~12% a faixa. Nas telas divididas o ativo aparece INTEIRO (nada de
  cabeça/rosto cortado — o Mike e a apresentadora ficavam cortados), com desfoque preenchendo o resto.
- **Layouts novos:** `duo` (dois ativos, um em cima e outro embaixo: `file` + `file2`/`clip_start2`, legenda na divisa)
  e `tv` (uma TV de verdade desenhada, `app/static/img/tv.png`, com o vídeo INTEIRO na tela — ex.: o comercial).
- **Motions de gancho/slogan:** `hook_cards` (cards com quadros reais, etiqueta, carimbo, número grande — gancho
  no espírito dos prints+soma do V001) e `slogan` (o slogan se imprime no produto + tradução em dourado).
- **Nada de quicar entre ele sozinho e tela dividida** (o que mais o incomodou): ativos a ≤ 12 palavras se emendam;
  ele só volta sozinho para ficar ~4 s ou mais, e a volta tem transição COM som.
- **Destaque alinhado à direita vale para todas as variantes** (`align: "right"`).
- **Música animada que retém** (ele reprovou suspense e a "Curiosity"): Joshie → `mk_hip_hop_02`; Liquid Death →
  `mk_sweet_september`.
- **Observações com foto:** cada observação salva um JPEG da cena como ele viu na prévia (com o retângulo) em
  `projects/<id>/obs/<id>.jpg` — ABRA a foto (Read) antes de corrigir.

# Editor de Vídeos — instruções para o Claude Code

Este repositório é um editor de vídeo local (FastAPI + ffmpeg + Whisper + Chrome headless).
O usuário fala em português e quer **o mínimo de trabalho**: quando ele pedir algo sobre um vídeo,
você opera o editor pela linha de comando abaixo — não edite `project.json` à mão.

## Comandos (sempre a partir da raiz do repo)

```
.venv/bin/python -m app.cli projetos                     # lista projetos (id, status, duração, nome)
.venv/bin/python -m app.cli ver <id>                     # transcrição com índices [i]palavra + inserções + config
.venv/bin/python -m app.cli plano <id> regras            # plano automático grátis (cortes + inserções)
.venv/bin/python -m app.cli pedido-claude-code <id>      # gera projects/<id>/para_claude_code.md
.venv/bin/python -m app.cli aplicar-plano <id> [json]    # aplica projects/<id>/plano.json
.venv/bin/python -m app.cli cortar <id> <i0> <i1>        # corta palavras (inclusivo)
.venv/bin/python -m app.cli restaurar <id> <i0> <i1>
.venv/bin/python -m app.cli trecho <id> <ini_s> <fim_s> cortar|restaurar   # por tempo (inclui silêncio/ruído)
.venv/bin/python -m app.cli texto <id> <i0> <i1> "texto"                   # corrige a transcrição
.venv/bin/python -m app.cli retranscrever <id>
.venv/bin/python -m app.cli inserir <id> '<json>'        # ver tipos abaixo
.venv/bin/python -m app.cli remover <id> <overlay_id>
.venv/bin/python -m app.cli config <id> chave=valor ...  # valores em JSON: format='"9:16"' look='"cinema"'
.venv/bin/python -m app.cli buscar <fonte> "<busca>"     # wikipedia|commons|arquivo|nasa|noticias|site
.venv/bin/python -m app.cli preencher <id>               # baixa materiais para B-rolls pendentes
.venv/bin/python -m app.cli amostra <id> [segundos]      # prévia rápida + folha de quadros
.venv/bin/python -m app.cli quadros <id> [mp4]           # folha de quadros (abra o .jpg com Read para revisar)
.venv/bin/python -m app.cli exportar <id>
.venv/bin/python -m app.cli formatos                     # formatos criados a partir de vídeos de referência
.venv/bin/python -m app.cli usar-formato <id> <slug>
.venv/bin/python -m app.cli formato-notas <slug> "<texto>"
.venv/bin/python -m app.cli refs [busca]                 # links de referência salvos (perfil, reel, post…)
.venv/bin/python -m app.cli ref-add "<links>" ["nota"] ["etiquetas"]
```

O servidor (`./iniciar.sh`, http://localhost:8765) lê sempre do disco: o que você fizer pela CLI
aparece no editor ao recarregar a página.

## Fluxo padrão quando o usuário pede uma edição

1. `ver <id>` para ler o roteiro inteiro. **Revise a transcrição primeiro**: o reconhecimento de voz erra palavras
   de som parecido ("que eu creio de IA" → "criei"); palavras marcadas com `(?)` têm baixa confiança.
   Corrija com `texto <id> <i0> <i1> "texto"` ou no campo `fixes` do `plano.json`. Nomes/marcas novos:
   `vocabulario "Nome"` (melhora as próximas transcrições).
2. Monte o plano seguindo a skill **editar-video** (`.claude/skills/editar-video/SKILL.md` — o "padrão Roberto",
   com tudo o que foi aprovado no V001; referência viva: projeto `5cdb9b27b3`):
   escreva `projects/<id>/plano.json` no esquema de `para_claude_code.md` (rode `pedido-claude-code` para gerá-lo)
   e aplique com `aplicar-plano`. Ou faça ajustes pontuais com `cortar`/`inserir`/`config`.
3. `preencher <id>` para buscar os materiais dos B-rolls.
4. `amostra <id> 15` e **abra a folha de quadros com Read**. Revise: texto cortado? Elementos sobrepostos?
   Legenda tampando algo? Material errado? Corrija e gere outra amostra.
5. `exportar <id>` e diga ao usuário onde está o arquivo.

## Envio com vários arquivos

Na tela inicial o usuário arrasta a gravação principal + arquivos de apoio e clica **Editar**. Várias gravações são
juntadas em ordem natural de nome de arquivo (IMG_2 < IMG_10) num `source.mp4` (lista original em `project.takes`).
Prints/fotos/vídeos de apoio vão para `projects/<id>/assets/` e aparecem em "Seus arquivos" (aba Edição): clicar
insere um `media` na agulha (imagem = `card`, vídeo = `full`) — isso vale mesmo com `inserts=false`, porque foi o
usuário quem pediu. Pela CLI: `inserir <id> '{"type":"media","file":"<arquivo em assets>","layout":"card","w0":..,"w1":..}'`.

## Tipos de inserção (`inserir`)

Todas ancoradas em palavras (`w0`..`w1` = índices da transcrição); acompanham a fala mesmo se os cortes mudarem.

| type | campos | o que faz |
|---|---|---|
| `text` | `text`, `style`: `title` / `keyword` / `lower` | título no topo / palavra gigante no centro / faixa de nome |
| `media` | `file` (em assets/) ou `query`+`source` (pendente), `layout`: `full`/`card`/`card3d`/`pip` | B-roll, print, foto |
| `motion` | `template`, `params` | lettering, icone, lista, contador, comparacao, card3d, carrossel3d (ver `app/brain.py`) |
| `sfx` | `sfx` (nome do CATALOG em app/sfx.py, ex.: whoosh_ar_in, snap_suave, thump_curto, click_classico), `offset` | efeito sonoro no início de w0 |
| `zoom` | `scale` opcional | punch-in de ênfase |
| `flash` | — | flash branco de transição |
| `emphasis` | `key` (palavra dourada), `variant`: `bigend`/`stack` | FRASE DE DESTAQUE: a legenda do trecho vira tipografia grande em linhas, palavra-chave enorme e dourada |
| `behind` | `text` | texto gigante ATRÁS da pessoa (recorte de fundo) |
| `perspective` | `side`: left/right | a pessoa num plano 3D inclinado |

## Tipografia (padrão do usuário)

- REGRA MÁXIMA: NENHUM texto (legenda, destaque, frase especial, título, motion) pode tampar o rosto — e NUNCA os
  olhos. Textos grandes ficam do peito para baixo (~58%–87% da altura, acima da interface do Reels). Nada de
  palavras espalhadas pela tela em zigue-zague, longe umas das outras: blocos compactos, centralizados, linhas
  juntas, sempre legíveis. Na dúvida, desça e compacte. Valide na folha de quadros antes de entregar.

- Legenda padrão `captions: clean`: Montserrat Alternates, branca, minúsculas (`caption_case: lower`, siglas ficam
  maiúsculas), 2–3 palavras, na altura de ~62% da tela — como a referência "está rolando".
- NOMES PRÓPRIOS mantêm a maiúscula mesmo com `caption_case: lower`: tudo que está no vocabulário (Turbo, Terry Crews,
  Old Spice…) e toda palavra que o usuário corrigir começando com maiúscula (vira vocabulário sozinha). Novo nome →
  `vocabulario "Nome"`. Palavra de impacto dentro da legenda (ex.: "oportunidade DURA"): `destacar <id> <i0> [i1]`
  → CAIXA ALTA na cor de destaque (`modo nao` desfaz).
  Destaques que ele marca no ROTEIRO com Ctrl+B (`**trecho**`): `destaques-roteiro <id> [V0NN]` (automático no
  `aplicar-plano` e ao ligar roteiro ↔ projeto) — `roteiros.apply_highlights`, marca `hl: "roteiro"`.
- ~85–90% do vídeo fica com essa legenda limpa. Os ~10–15% mais fortes (tese, número marcante, revelação, frase de
  efeito) viram `emphasis`: linhas de tamanhos diferentes, palavra-chave enorme em dourado amarronzado
  (`accent`, padrão `#C29A5B`). Nunca cursiva, nunca rosa. Não use dois destaques seguidos.

Configurações úteis (`config`): `speed` (1.0, 1.1, 1.2… — acelera sem distorcer a voz), `format` (original, 9:16, 1:1, 16:9), `look` (none, cinema, quente, frio,
vivido, pb, vintage), `transition` (cut, zoom, fade), `captions` (clean, pop, classic, none), `caption_case`
(lower, original, upper), `accent` (cor das frases de destaque), `background`
(none, blur, escuro), `max_pause`, `pad`, `voice` (true/false), `music` (arquivo em assets/), `music_volume`, `sfx_volume`.

## Fundo trocado (cenário)

`fundo <id> biblioteca|gabinete|biblioteca_escura|none|file:<asset>` (ou aba Estilo → "Fundo (cenário)").
`app/background.py`: recorte você + cadeira (U²-Net local, `mask_fg.mp4`, ~0,15 s/quadro na 1ª vez), foto REAL de
cenário (Wikimedia, crédito no .creditos.txt) desfocada como lente de celular, cor puxada para a luz do rosto,
vinheta e granulação; entra ANTES dos cortes/zooms (o fundo aproxima junto). A prévia do editor vira
`preview_bg.mp4`. Padrão = "biblioteca" (Long Room). Próximos passos: bordas de cabelo (matting de vídeo) e
acompanhar o balanço da câmera.

## Aprendizados das referências (aplicados sozinhos em vídeo novo)

- @fernandomiranda777: som `reverse_expectativa` no fim do hook + transição `leak` no corte pós-hook.
- @tay.ldantas: `reframe: true` (enquadramento muda a cada corte: aberto/médio/fechado); LISTAS com zoom progressivo
  (`zoom` com `rel: true`, cada item fecha mais); FRASE ESPECIAL `emphasis` com `variant: "atras"` (hoje: bloco
  compacto embaixo, palavra-chave enorme dourada, linhas entrando animadas — o zigue-zague na altura da cabeça foi
  ABOLIDO pelo usuário: ilegível e tampava o rosto) — 1 por vídeo (2 se > 45 s); todo destaque entra
  saindo do desfoque. Novos aprendizados: registre com `refs.edit(id, {"learned": [...]})` e na skill editar-video.

## B-roll "modelo viral", emoji 3D e faixa de cima

- `media` com `layout: "viral"`: fundo ônix, o vídeo/foto num quadro quadrado de cantos arredondados no centro, a
  legenda cai dentro do quadro; enquadra a parte de cima do vídeo (deixa de fora legendas que o creator já tinha).
  Vídeos de apoio são sempre MUDOS. `clip_start` = de onde o vídeo começa. `chain: true` = sequência emendada (cada um
  fica até o próximo começar — ex.: "camisetas, suplementos, produtos de beleza"), com clique a cada troca.
- `motion` `emoji3d` (params icon/x/y/size) + `min_dur: 1.8`: emoji com espessura, giro 3D, brilho, partículas; som
  `whoosh_ar_in` + `pop_seco` (offset 0,34). Posicione ao lado da cabeça (x≈0.74, y≈0.2), nunca sobre o rosto.
- `motion` `emojifun` (params icon, mode `slide`|`drop`|`peek`, x, y, size): emoji ENGRAÇADO "meia-bomba" — `slide` vem da
  esquerda, fica mole balançando acima da cabeça e sai pela direita; `drop` (preferido ao `peek`) desce do teto com o cabinho verde para baixo, balança como pêndulo e é puxada de volta
  (use `min_dur` ≥ 3,4); `peek` só a cabecinha surge de baixo (o usuário não gostou). Sem
  brilhos/piscadas (o usuário não gosta). `end_w` + `end_offset` = termina logo depois de um ponto da fala (ex.: sair
  após o clique do flash do pós-hook).
- `motion` `paleta` ("criatividade"): paleta 🎨 vem da esquerda, pincel 🖌️ da direita, o pincel molha numa cor em
  cima da cabeça e cada um sai pelo seu lado. `emojifun` `pour` v2: saleiro GRANDE entra de lado, deita a 90°,
  balança despejando sal até o pé do vídeo, fica em pé e sai pela direita. `drop` + `exit: "up"`: recolhe direto
  (sem a descidinha antes de sair). Prints com dados de cliente: `prints_soma.hide` borra R$, marca/@/link e nomes.
- Durante um motion de tela inteira com `hide_captions` (ex.: AIDA), a legenda que entra desce para 85% da altura.
- Na tela verde: você colado no canto (um pouco para fora embaixo e na lateral, sem fresta clara); destaques ficam
  embaixo à direita, ao seu lado, num bloco só com painel sépia; dá para pôr a luz (`transition` leak) no corte de
  entrada — sem som.
- `emojifun` também tem `pop` (surge ao lado da cabeça e balança devagar — ex.: 🎨 em "criatividade"), `pour` (🧂 entra do
  alto, tomba e despeja grãos de sal QUADRADINHOS caindo retos — nada que pareça gota/rabo) e `rot` (giro do emoji
  pendurado no `drop`; 🍌 usa `rot: -150`, `hang: 0.05` — o 🍌 da Apple já é descascado). Pendurados: nunca na testa.
- `motion` `prints_soma` (hook "os dois somam 38"): `prints-soma <id> <print1> <print2> <w1> <w2> <w_zoom> <w_soma> <w_fim>`
  borra o R$ de cada print (OCR), acha a pílula de reações, cada print entra com clique, flutua, zoom DENTRO de cada
  print nas reações (aro dourado) e a soma "16 + 22 = 38" com o total em dourado.
- `motion` `acronimo` (AIDA etc.): `params.items=[{letter, word, w}]`, `final_w` (palavra do acrônimo), `title`;
  estilo EDITORIAL Kronos (o usuário achou o 3D/relevo "cara de IA, grosseiro"): inicial dourada + fio fino + palavra
  em versalete revelada por cortina, depois o acrônimo espaçado subindo de uma máscara sobre um fio dourado.
  Motions devem ser sóbrios e elegantes: sem quiques, badges 3D, brilhos ou halos. Use `hide_captions: true`.
- TÓPICOS: toda enumeração na fala vira `motion` `bullets` automático (itens sincronizados por `w`, legenda comum
  escondida no trecho) — pedido do usuário, vale mesmo com inserções em pausa.
- Itens de motion com `"w"` ganham `"t"` (s desde o início da animação) no compute — sincronia com a fala.
- B-roll em tela cheia (`layout: full`) para a 1ª citação forte de um tema (ex.: "criativos feitos por creators").
- Na timeline, B-roll (coral), animações (roxo) e tela verde (verde) ficam na faixa de cima, arrastáveis.
- Vídeos de creators do usuário ficam em `Ativos Turbo/UGC Creators/`.

## Observações na edição (ele marca problemas direto no vídeo)

Botão "✎ Observação" (ou tecla Q; Enter salva e volta a tocar) no editor (as já feitas ficam ESCONDIDAS na prévia; "📝 Ver observações"/tecla N mostra retângulos + marcadores, como o "Ver cortes"; a aba lista todas e clicar num card mostra só aquela): ele arrasta um retângulo sobre a cena e escreve. Fica em
`project["observacoes"]` ({t_src, t_out, rect, text, status}), marcador dourado na timeline, retângulo tracejado na
prévia e aba "📝 Observações" (abertas + histórico); corpus em `roteiros/observacoes_edicao.jsonl`. Quando ele disser
"implemente as observações do vídeo X": `observacoes <pid>` → corrija cada uma (no PLANO do roteiro, se for ensaio:
`roteiros/edicao/<código>.json` + `aplicar-edicao`) → `resolver-obs <pid> <id> "o que fiz"` → aprendizado geral na
skill editar-video / CLAUDE.md.

## Formato dos ativos (regra dele, vale para TODO vídeo — revisado em 18/10)

- Tela cheia (`full`) só com ativo VERTICAL (ou horizontal HD com `crop_ok` e `fx` conferido). Foto quase quadrada ou
  horizontal → `viral` (tvzinha na proporção dela, nunca cortada); vídeo horizontal → `meio`. Prefira VÍDEO a foto;
  toda foto tem zoom in lento (render e prévia).
- Tela dividida = SÓ o `meio` 45/55 (o `topo` com a cabeça invadindo foi abolido: cabeça fantasma): o ativo PREENCHE a
  faixa de cima (sem blur em cima/embaixo — o desfoque é só a linha da divisa), recortado do lado sem importância
  (`fx` 0..1); ele embaixo; legenda logo ACIMA da divisa na caixinha sépia (no terço de baixo caía na boca dele).
  `duo` = dois ativos (legenda normal). `tv` = TV de verdade numa sala (`backgrounds/tv_sala.mp4`, Mixkit 9612).
- NUNCA ele "solo" entre B-rolls/divididas (`SOLO_MIN_W`, timeline estende o ativo até o próximo); troca entre
  B-rolls de tela cheia/tvzinha leva desfoque rápido; vídeo de apoio segura o PLANO escolhido (`shot_end`).
- Frase de destaque ≤ 10 palavras (aplicar-edicao encurta terminando na palavra-chave); com plano de edição, os
  "tópicos" automáticos saem (o plano decide o que é lista; lista = estilo AIDA `acronimo` com `final: false`).
- Apresentador nunca dentro da tvzinha. Procure B-roll vertical primeiro.

## Tela verde (print de fundo, você no canto lendo)

Overlay `{"type":"greenscreen","file":<imagem em assets>,"w0","w1","corner":"bl|br","size":0.52}`. O print ocupa a tela
(rola devagar se for comprido) e você entra RECORTADO (mask_fg, com microfone/cadeira) no canto de baixo; legendas
continuam (o print vai de ponta a ponta e termina colado no pé da tela; você fica PARADO no canto, sem zoom, e a tela
verde começa exatamente numa troca de plano) — SUBINDO para ~47% (acima da sua cabeça recortada) com caixinha sépia (legível no print branco); frases
de destaque também sobem (`timeline._lift_over_greenscreen`). AUTOMÁTICO: ao processar um vídeo com prints de apoio, `greenscreen.auto_detect` lê o print (OCR Apple
Vision local, app/ocr.py) e acha o trecho em que a fala bate com o texto. `greenscreen.enrich` completa SOZINHO
(detecção, editor e `tela-verde`): print com R$/participantes borrados (cópia `_oculto`), luz `leak` no corte de entrada
(sem som) e CLIQUE na palavra em que você começa a ler cada tópico ✅/• do print. Marca/@/link do cliente: borre à mão. Manual: "Seus arquivos" → 🟩 Tela verde,
palavras selecionadas → 🟩 Tela verde, ou `tela-verde <id> <arquivo> [w0 w1]`. Na timeline, a tela verde é a
barra verde de cima (puxar as pontas = duração). Ao aplicar, o editor recorta você sozinho (`/cutout` →
`fg_alpha.webm`, vídeo transparente) e a PRÉVIA já mostra você recortado no canto. Prints de terceiros ficam em `prints/`
(fora do git — repositório público).

## Timeline estilo CapCut e música

- A timeline mostra o VÍDEO FINAL (pedaços encostados); "Ver cortes" (V) mostra o original com o que saiu.
- Dividir = `project.splits` (instantes no original, S/B/X na agulha); dois cortes = um pedaço. Excluir pedaço =
  `/range` com `ripple: true` (corta e remove sons/transições/destaques presos a ele; o resto anda para a esquerda).
- Música = `project.music`: clipes `{file: "lib:<slug>"|asset, start, in, dur, vol, fade}` no tempo do vídeo editado
  (app/music.py: grupos "🔥 Em alta (estilo Reels)" e "🧠 Evergreen — psicologia, marketing, vendas" com faixas Mixkit
  (licença livre, uso comercial) + Kevin MacLeod CC BY 4.0 em "Outras" e "🎻 Suspense com cordas (retenção)" —
  Volatile Reaction, Hitman, Investigations, Sneaky Snitch, Long Note Four; CC BY pede crédito na legenda do post). Músicas em alta do Instagram têm direitos:
  só dentro do app — oriente exportar sem música e adicionar o áudio em alta ao postar. A música NUNCA acelera com `speed`: com speed ≠ 1 ela é mixada
  depois da voz acelerada, em 1x. Volume constante, igual à prévia (sem ducking).
- Identidade visual (Kronos) é aplicada por trás; a seção fica escondida na interface (pedido do usuário).

## Trechos, ordem e transições entre cortes

- Cada trecho mantido é um "pedaço" (trilha acima da timeline). `project.order` = um instante (s, no original) dentro
  de cada trecho, na ordem desejada; vazio = ordem gravada. Trechos novos (de cortes) seguem o trecho anterior.
- Transição SÓ existe num corte real (nunca no meio de um bloco contínuo): `plan.place_cut_transitions` encaixa as
  automáticas no corte mais próximo (ou tira) e faz o som do pós-hook terminar exatamente no corte.
- CORTES DE RITMO (`rhythm_cuts`, padrão em vídeo novo): mesmo com fala fluida (nada a cortar), o vídeo vira
  planos de ~2–5 s nos finais de frase; cada plano alterna ABERTO aproximando devagar ↔ FECHADO afastando devagar
  (a cada 3º fechado, um mais fechado). O hook é um plano só, aproximando no rosto até o corte do hook.
- HOOK: sempre que houver o som de expectativa há corte + transição logo depois (o fim do hook vira corte mesmo sem
  pausa), com um CLIQUE (`click_classico`; antes era flash de câmera — trocado pelo usuário em 2026-10-13) exatamente
  no corte — sempre, mesmo se o usuário ajustou o som/transição à mão; o hook vai até o fim da frase.
- PÓS-HOOK SEMPRE ABERTO (regra do usuário, 100% das vezes): o hook termina aproximado no rosto; o plano seguinte
  entra DESAPROXIMADO (enquadramento aberto, 1.0) — o contraste é o impacto (`timeline.split_pieces`, `hook_first`).
- FRASE ESPECIAL: todo vídeo tem 1 (se nenhuma frase se qualificar, a de mais impacto); valores em dinheiro
  sobem (entrada "rise"). Fica na parte de baixo, NA FRENTE da pessoa (atrás do corpo sumiria) — nunca no rosto. O recorte (mask.mp4) também servirá para fundos de IA no futuro.
- Padrão de vídeo novo: `scene_transition: "leak"` (Luz só nos cortes grandes/troca de cena, ≥ 6 s entre elas),
  `smooth_zoom: true` (cada trecho aproxima ou afasta devagar, ~6%) e `reframe: true` (de vez em quando um zoom seco
  maior). O usuário prefere zoom suave contínuo, principalmente em vídeo gravado sentado.
- Transição num corte = overlay `{"type":"transition","style":"leak|branco|escuro|desfoque","w0":<1ª palavra do trecho>}`;
  ela gruda no início do trecho. Sem overlay = corte seco. Cores sempre da paleta (creme/ônix/coral/dourado).

## Roteiros: esteira de produção (em construção com o usuário)

Tela "✍ Roteiros" na home (`#roteiros`); `app/roteiros.py` (dados) + `app/roteirista.py` (geração); tudo em `roteiros/`
(FORA do git: conteúdo privado, repositório público). Cada vídeo tem um código `V001, V002…` (nunca reaproveitado).
Kanban de status: ideia → rascunho ("Para avaliar") → aprovado → gravado → editado → publicado (+ `archived` = descartado).

Processo de 3 etapas do usuário:
1. `roteiros/padroes_referencias.md`: engenharia reversa dos 4 criadores que ele admira (Fernando Miranda, Tay Dantas,
   Roni/Reserva, Guilherme Benchimol): copy, vídeo e edição. Vídeos/transcrições/folhas em `formatos/_refs/`
   (baixados pela página pública /embed do Instagram; o yt-dlp exige login).
2. `roteiros/padrao_roberto.md`: TOM DE VOZ dele (prioridade sobre as referências), aprendido com o V001 e com um
   **Histórico de aprendizado** que cresce a cada aprovação/descarte (com o comentário dele) via `roteiros.learn`.
   Periodicamente, incorpore o histórico às regras do arquivo (e suba a versão).
3. Big idea na tela → `roteiros/ideias.json` (`I001`…) → briefing em `roteiros/fila/<id>.md` (padrões + padrão Roberto
   + roteiros aprovados + inteligência). Motor padrão `claude_code` (grátis): quando o usuário disser "gera os
   roteiros", rode `fila-roteiros`, LEIA o briefing inteiro, escreva os N roteiros (ângulos/esqueletos diferentes, no
   tom dele, fatos incertos marcados [confirmar]) num JSON no esquema do briefing e salve com
   `salvar-roteiros <id> <arquivo.json>`: viram cards "Para avaliar". Motor `claude_api` (pago) só se ele pedir.
   Ideia só guardada = status `catalogada` (não gera); para gerar: `fila-roteiros I004`.
   REGRAS DE COPY (padrão Roberto v2, 2026-10-15): inspiração no V001 é de TOM, nunca de frase — `salvar-roteiros`
   RECUSA trecho de 6+ palavras igual a roteiro dele e as expressões-assinatura do V001 (`roteirista.SIGNATURES`);
   tamanho 180–260 palavras (cases ≤ ~330), um fio só, fim curto amarrado ao gancho, ≤ 3 números marcantes.
   MÉTODO (v4, após a reprovação do V009): os tópicos dele são INGREDIENTES de UMA big idea (declare `big_idea` e
   `espelho` no JSON), espelho na vida do espectador cedo, loop aberto, dobradiça, payoff que fecha o gancho; citação
   real pesquisada em inglês (nunca desmentir o próprio gancho); exemplos do dia a dia, não laboratório nem métricas
   de rede social; `salvar-roteiros` também recusa vícios de IA (`roteirista.AI_TELLS`).
   v5 (2026-10-18, a partir dos 3 roteiros que ele AMOU: V001, V008, V010): o roteiro É uma HISTÓRIA REAL (case com
   nomes, suspense "o esperado × o que aconteceu"), nunca ensaio; moral só depois ("Agora repara…"), de vendas, sutil
   — seção "O QUE ELE AMA" no `padrao_roberto.md`; o JSON ganhou o campo `historia`.
   v6: "REGRAS DE ESPINHA" — cada parte do hook acontece na história, resultado sem ambiguidade, nada de repetir a
   moral do roteiro anterior, CTA sempre (pergunta aberta fácil de comentar > compartilhar > salvar só em consulta).
- FORMATOS de vídeo do usuário: `roteiros/formatos/<slug>.md` (aparecem na Inteligência, editáveis, e no seletor
  "Formato" da nova ideia). Ideia com formato → o briefing inclui o arquivo do formato e cada roteiro traz `ativos`
  (momento → ativo ESPECÍFICO e original → onde achar → status pendente/achado; a tela marca "achado").
  1º formato: **cases** (Cases de sucesso, ref. Matheus Beirão): espinha com tempos, "é aqui que a história fica
  interessante", tela dividida com a cabeça recortada invadindo o ativo, e CURADORIA DE ATIVOS da própria história
  (perfis do fundador/marca, o post viral, varejo, imprensa) — nada de banco genérico. É o diferencial que o usuário
  mais valoriza: capriche na busca. Novo formato = novo .md nessa pasta (título na 1ª linha "# Formato: …").
- SALVAR NO DOCS (editor → Google Docs): via Apps Script do PRÓPRIO usuário (código gerado em `roteiros.google_status`,
  com senha em `roteiros/google.json`, só mexe dentro da pasta Instagram Pessoal; cria o Docs na pasta do vídeo se
  não houver). Toda substituição de texto guarda a versão anterior (`snapshot`, "versões anteriores" na tela).
  NUNCA rode `import_gdoc` para testar: ele sobrescreve o que o usuário escreveu.
- COMENTÁRIOS NO ROTEIRO (estilo Google Docs): ele seleciona um trecho → "💬 Comentar" (copy) ou "🎬 Sugerir edição"
  (como o trecho deve aparecer no vídeo). Ficam em `r["comments"]` (coluna à direita, trecho marcado no texto) e em
  `roteiros/comentarios.jsonl` (corpus das broncas, entra no briefing dos próximos roteiros). Quando ele disser
  "implemente o que eu falei no card V0NN": `comentarios V0NN` → aplique CADA um 💬 (edite o texto com snapshot) →
  `resolver V0NN <id> "o que fiz"` → registre o aprendizado geral em `roteiros.learn` (e no padrão, se for regra).
  Os 🎬 ficam abertos até a edição do vídeo: o montador/edição os segue e resolve.
  A gaveta sempre busca a versão do disco ao abrir, e o servidor recusa (409) salvar texto a partir de versão velha.
- Importar texto de um Google Docs que está na pasta do vídeo: botão na tela / `roteiros.import_gdoc` (doc
  compartilhado por link). V001 já importado.

- **Google Drive** (conectado): pasta "Instagram Pessoal" (id `1jl3UpCcWyPY0CxFHYmaSvSCKDzFi713a`), local em
  `~/Library/CloudStorage/GoogleDrive-…/Meu Drive/Projetos/Instagram Pessoal` (streaming, sem backup do Mac — o
  usuário NÃO quer nada do Mac subindo). Uma pasta por vídeo `V001 — título/` com `bruto/`, `apoio/`, `final/`
  (`roteiros.ensure_folder`; renomeia junto com o título). Ao exportar um projeto ligado a um roteiro, o MP4 + créditos
  vão para `final/` e o roteiro vira "editado" (`deliver_export`, na API e na CLI). NUNCA mexer fora dessa pasta.
  V001 = Impotência (projeto 8a85f9a1e2).

## Roteiro aprovado → vídeo quase pronto (antes da gravação dele)

Objetivo dele: produtividade. O vídeo fica MONTADO (B-rolls, tvzinha, prints, motions, destaques, sons, música) antes
de ele gravar; quando chega o MP4 dele, o mesmo plano entra com um comando ("low-touch").
- `roteiros/edicao/<código>.json` = o PLANO DE EDIÇÃO do roteiro, com inserções ancoradas em FRASES do texto
  (`em`/`ate`), ativos em `roteiros/edicao/<código>/`. Esquema no topo de `app/montar_roteiro.py`. Todo media/motion
  ganha clique ao brotar; `emphasis` do plano substitui os destaques automáticos; o negrito do roteiro vira destaque.
- `montar-roteiro V0NN` → prévia: voz RÁPIDA de IA (edge-tts, segundos — só para o tempo/ritmo) + apresentador
  provisório (Mixkit 41272, trecho limpo 0–6,5 s, vai-e-volta) → projeto no editor → aplica o plano. A voz
  CLONADA dele (Chatterbox, `.venv-voz`, `tools/voz_tts.py`, ~8× o tempo real) só se ele pedir (`montar-roteiro V0NN clonada`).
- Gravação real chegou: crie o projeto normal (upload) e rode `aplicar-edicao <projeto> V0NN` — corrige a transcrição
  pelo texto do roteiro, acha cada frase na fala (tolerante) e cria tudo. Revise com `amostra`/`quadros`.
- NÃO ligue o projeto de ensaio ao roteiro (`project`): exportar um projeto ligado entrega no Drive e muda o status.
- NAVEGAÇÃO roteiro ↔ edição: `project.roteiro = "V0NN"` (montar/aplicar-edicao já marcam; à mão: botão "✍ Ligar roteiro"
  no topo do editor). Editor: "✍ V0NN · roteiro" abre a gaveta; gaveta: "🎬 Abrir edição" (lista se houver várias).
- CÓDIGOS = pastas do Drive dele (renumerados em 19/10) — GRAVAÇÕES REAIS: V002 Joshie 0723e4babe, V003 Liquid Death
  8a8468fdc6, V004 Jung ac581e28dc, V005 Epicteto 73fcead65f (ensaios antigos: 4d8b7361e4, a898a8a1cb, 8de2ec28c1,
  c38a0bbb7d; planos do ensaio guardados em `roteiros/edicao/V00N.ensaio.json`). A pasta que
  ele criou no Drive é respeitada (`ensure_folder` não renomeia). Entrega no Drive só quando ele pedir.
- GRAVAÇÃO REAL chegou (bruto HD na pasta do Drive): `criar_projeto(<mov>, "V0NN · <nome> · gravação")` → leia a
  transcrição INTEIRA contra o roteiro (regravações, palavras inventadas em pausas com duração zero, nomes perdidos;
  corrija com `texto`, que fica protegido da correção automática) → `aplicar-edicao <pid> V0NN` → leia o relatório
  (⚠ âncora duvidosa = confira; ✗ = ele falou diferente → ajuste a âncora no plano para servir ao ensaio E à gravação,
  de preferência UMA palavra que só aparece ali) → lista de blocos sem buraco → exportar → folha de quadros de tudo.
  Frases de destaque e motions de texto (inclusive os cards do gancho) medem o queixo dele (Vision) e começam abaixo
  do rosto (+5% de folga pela barba). O GANCHO vai até o fim da frase do 1º elemento do plano (som/luz/clique do
  pós-hook vão para lá). O casamento de frases ignora o que foi cortado (regravações). CORTE PRIMEIRO, sincronize
  depois (pedido dele): compare a fala com o roteiro (regravações, palavras inventadas em pausas, "nada, nada" que o
  corte automático tira por engano) antes de aplicar o plano. Exporte UM vídeo por vez (o Mac pede para forçar
  fechar apps com vários) e nunca apague `*.tmp.*` com exportação rodando.

## Montador de vídeo sem apresentador (formato cases)

`app/montagem.py`: narração (voz de IA: `edge-tts`, voz pt-BR-AntonioNeural, rate +42% ≈ ritmo do Matheus; tempos
exatos por palavra via WordBoundary) + lista de cenas ancoradas em palavras (`spec.json`: src, ss, mode full/band,
zoom in/out, punch, click) → 1080x1920 com zoom contínuo (perspective), punch-ins nos números, legenda Kronos em
~62% com palavras-chave douradas, luz + flash + som de expectativa nos cortes do hook/dobradiça, música com ducking.
Cenas renderizadas com cache. Ativos: YouTube via yt-dlp (cliente `android` = 360p sempre funciona;
`android_vr` = HD, às vezes 403 no meio); escolher o trecho EXATO conferindo quadros (folha por cena) — a folha
fps=1/6 erra ±3 s. 1º teste: `prints/liquid_death/` (V008). Próximo passo: layout de tela dividida com o
apresentador recortado embaixo quando houver gravação dele.

## Estalo (estalou os dedos → o fundo vira outro cenário)

`estalo <id|arquivo.mp4> [cenario] [segundo]` (`app/estalo.py`, 100% local): acha o estalo no áudio (transiente curto e
agudo; entre os candidatos fica o que tem polegar e médio encostados logo antes — pose da mão do Apple Vision), recorta
você + cadeira (máscara de instância do Vision refinada com filtro guiado e suavização no tempo; descontaminação da
borda contra a placa da parede = sem pedaços brancos no cabelo), põe o cenário (foto real desfocada como lente de
celular, exposição puxada para a sua luz, light wrap) e revela com uma onda de luz quente nascendo da mão + punch.
Som: `riser_curto` antes e `whoosh_impacto_grave` no estalo. Cenários: `alexandria` (padrão), `alexandria2`,
`alexandria3` (Bibliotheca Alexandrina moderna, CC BY-SA — da antiga não existe foto). Errou o instante? passe `segundo`. No projeto, o vídeo com o estalo VIRA a gravação (`source`; original em `source_orig`, `estalo <id> desfazer` volta) e o trecho do estalo fica protegido (`manual` keep) — senão o corte de pausas o tira (não tem fala). Duas passadas com a máscara em disco + `objc.autorelease_pool` por quadro (vídeo de 25 s estourava a memória e o Vision/Metal quebrava). Limite: o cenário não acompanha o celular mexendo.

## Remover legenda "queimada" de um vídeo

`remover-legenda <arquivo.mp4> [saida.mp4]` (`app/delegenda.py`, 100% local, sem modelo baixado — carregar o LaMa
.pt do GitHub foi bloqueado pela proteção do Claude Code). Acha a faixa da legenda com OCR, alinha os quadros
(homografia pela parede acima da legenda + fluxo óptico DIS com fluxo completado por trás do texto, para objetos com
paralaxe como uma luminária), e reconstrói cada quadro com os vizinhos que MAIS mostram o fundo limpo (pausas sem
legenda achadas até ±10 s), dono único por pixel, costura estreita, luz casada localmente e granulação igual; o que
nunca aparece vem da placa do plano (também alinhada). Confere com OCR no fim. Lento em 4K (~1 min de proc. por s).
Vídeos de terceiros ficam em `prints/` (fora do git).

## Banco de referências (links)

Links de Instagram/TikTok/YouTube que o usuário quer guardar ficam em `referencias/links.json` (sem banco de dados;
`referencias/links.md` é a cópia legível, regerada sozinha). Tela "📌 Referências" na home ou `refs`/`ref-add` na CLI.
Quando ele pedir para "salvar esse link", use `ref-add`. O @, a legenda e a miniatura vêm dos oEmbed públicos.
Cada alteração faz commit SÓ de `referencias/` e push sozinho (o repositório é público).

## Referências → formato

Quando o usuário mandar vídeos de referência, eles ficam em `formatos/<slug>/refs/` com métricas (`.json`)
e uma folha de quadros (`.sheet.jpg`). Abra as folhas com Read, descreva o estilo visual (tipos de inserção,
legendas, cores, molduras, ritmo) e salve com `formato-notas` — o planejador passa a seguir essas observações.

## Estado atual do produto (pedido do usuário)

- B-roll, motions e títulos estão **em pausa** (`settings.inserts=false`): o foco é corte impecável,
  legenda e frases de destaque, sons e cor. Não adicione inserções visuais sem o usuário pedir.
- Corte com bom senso: além de regravações, tire muletas ("o que eu posso dizer", "deixa eu ver"), frases
  abandonadas e falas de bastidor. Na dúvida sobre conteúdo real, mantenha.
- Voz de fundo: cada palavra tem `db` (volume) e `bg` (muito abaixo da voz principal = outra pessoa longe do
  microfone, ex.: alguém soprando o texto). Frases de fundo são cortadas; nunca use a versão de fundo de uma frase.
- GRAVAÇÃO PEQUENA (lado maior < 1280, ex.: vídeo do WhatsApp 576x1024): sai em 1080x1920 (lanczos, legenda nítida),
  planos PARADOS (sem zoom suave contínuo — a compressão "ferve" e parece câmera tremendo) e saltos de
  enquadramento ≤ 10% (aproximar mais borra). Reclamação do usuário: "o bruto parecia muito mais profissional".
- PADRÕES DE VÍDEO NOVO (config.json, aprovados no V001): luz do bruto (`grade: off`, `look: none`), `speed: 1.2`,
  `voice: false`. Velocidade/look/grade que o usuário escolher no editor viram o novo padrão (`presets.STICKY`).
- Cor: se o bruto já está bom, `config <id> grade='"off"' look='"none"'` (o usuário prefere a luz do bruto à
  correção). `grade: auto` corrige o insumo (HDR do iPhone vira SDR automaticamente). Intensidade em `grade_strength`.
- Sons (pedido do usuário): vídeo falado contínuo NÃO leva sons aleatórios — nada de thump em número, whoosh em
  destaque ou impacto em frase forte. Só entram: (1) o som de expectativa do hook; (2) um CLIQUE (click_classico /
  click_mouse) quando uma imagem/print/vídeo/motion BROTA na tela. Biblioteca em `app/sfx.py` (CATALOG); PROIBIDO:
  ding, notificação, ka-ching, buzzer, boing, vine boom. Cada som tem `lead` (começa adiantado para o pico cair
  no momento) e `gain`; o momento exato = palavra `w0` + `offset` (s) — o usuário arrasta a bolinha roxa na timeline.
- CLIQUE também a cada bullet lido de um print (tela verde) e a cada item de acrônimo (AIDA), na palavra exata.
- PÓS-HOOK (padrão, da referência instagram.com/p/Dd4qhPrBCgr): `reverse_expectativa` (sino ao contrário, sintetizado
  em app/sfx.py, cresce 2,3 s e para seco) ancorado na 1ª palavra depois do hook + transição `transition`/`leak`
  (luz quente → creme → cena nova, ~0,3 s). Escolhas em `hook_sfx` / `hook_transition` (aba "Sons e transições";
  ficam salvas em config.json para os próximos vídeos). Inserir à mão:
  `inserir <id> '{"type":"transition","style":"leak","w0":N,"w1":N}'`.

## Identidade visual (padrão do usuário: KRONOS)

Definida em `app/presets/kronos.json` (paleta + regras) e aplicada com `POST /api/projects/<id>/style`
ou na aba Estilo. É o padrão dos vídeos novos (`config.json`). Escopo: SÓ cor e tratamento — nunca inserir
logo nem trocar a fonte do projeto. Ao escolher QUALQUER cor (legenda, destaque, painel, barra), use só a paleta:
Creme #F5EFE6 texto · Dourado Kronos #E0BB6A destaque (único dourado) · Ônix #150C06 sombra/contorno ·
Sépia #2E2017 painéis/caixas (~78%) · Areia #A89070 linhas · acentos Coral #F0916B, Verde #3ECF8E, Azul #A8BAD0
com parcimônia. Grading `look: kronos` (quente, pretos levantados quentes, saturação média-baixa).
Transições suaves (cortes limpos/fades) — sem flash. Proibido azul/ciano frio dominante e preto frio esmagado.

## Exportação = prévia (regra do usuário: "a versão que vejo na prévia é a correta")

Tudo que a prévia mostra a exportação tem que reproduzir IGUAL; nada de efeito que só exista no render. Já corrigido
(2026-10-14): legenda com o MESMO tamanho (5% da altura; o libass mede a fonte pela célula = 1,379 em → `FONT_K`) e a
mesma sombra suave (`halo`), posição vertical corrigida; B-rolls/prints/tela verde com troca SECA (sem esmaecer e com
sobra no fim — antes aparecia 1–3 quadros de você entre eles); cache de motion inclui o conteúdo do template (antes
reaproveitava quadros antigos); voz SEM tratamento (`voice: false`: o denoise deixava metálica), acelerada com
`atempo` (WSOLA, como o navegador) e volume por UM ganho fixo que nunca passa de -1 dBTP (sem limitador/loudnorm);
música e efeitos nos MESMOS volumes da prévia (×1,6) e sem ducking; MÚSICA SEMPRE JUNTO (regra do usuário): se o
projeto tem música e o arquivo falta, a exportação dá erro, e `render.check_music` mede no MP4 pronto que ela está lá
(senão apaga e dá erro) — volume de música em Reels: ~12% no editor (≈ 15–16 dB abaixo da voz; 6% some no celular);
legenda comum SAI quando entra um destaque/motion e nunca fica por cima da seguinte; entrega no Drive: apaga a versão antiga, copia
limpo e espera o Drive registrar (xattr item-id) — sobrescrever no lugar fazia sumir e nome temporário+rename não subia; o vídeo termina ~0,6 s depois da última
palavra (antes cortava o fim de "trabalho?").
SINCRONIA (medida com vídeo sintético flash+bipe pelo render real): o filtro `fps` descartava o último quadro de cada
trecho e a imagem ia se adiantando ao som (até ~0,6 s). Agora: cortes caem em quadro exato do original (timeline),
cada trecho tem EXATAMENTE N quadros (`tpad`+`trim=end_frame`+`setpts=N/…`) e a aceleração usa `fps=…:round=near` →
desvio de −18 a +23 ms. Mexeu no render? `teste-sincronia <id>` (app/synctest.py) — tem que dar OK.
B-ROLL/MOTION TRAVANDO (corrigido 2026-10-14): o vídeo principal chega às junções com tempo em ms e a camada em 1/30 s;
a cada 3 quadros a junção repetia o anterior. Toda camada usa `settb=AVTB` + início no grid de quadros meio quadro
adiantado (`ovt`). Ao escolher trecho de vídeo de apoio, confira se o PRÓPRIO arquivo não tem quadros congelados
(diferença entre quadros ~0) — a Lara tinha em 6–12 s; vídeos a 24 fps (cr_creamy, comerciais) têm cadência natural. Ao mexer em render.py ou na
prévia, confira os dois lados (meça largura/altura do texto na prévia via JS e no MP4 pelos pixels).

## Backup (o usuário NÃO pode perder nada)

- Código → repo PÚBLICO `editor-de-videos` (commit + push a cada mudança).
- Conteúdo dele → repo PRIVADO `filosofiaempreendedora00/editor-de-videos-privado`, via `app/backup.py` (clone em
  `.backup-privado/`, fora do git público): roteiros/ inteiro (padrão de tom, versões, comentários, ideias), formatos
  (só .md/.json), config.json, vocabulario.txt e o project.json/plano.json de cada projeto. Automático a cada 10 min
  com o servidor aberto; à mão: `backup`. NÃO entram: vídeos/áudios (bruto fica no Drive/Mac), `.env`,
  `roteiros/google.json` (senha do Apps Script) nem a amostra da voz dele (`voz/`).

## Regras

- Custo: o padrão é 100% gratuito. Só use a API paga (`plano <id> claude_api`) se o usuário pedir.
- Materiais de terceiros: prefira as fontes com licença clara; a exportação gera um `.creditos.txt`.
- Código: Python 3.9 (`.venv`), sem build no front (`app/static`). Teste com `amostra` antes de dizer que terminou.

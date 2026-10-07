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
2. Monte o plano seguindo a skill **editar-video** (`.claude/skills/editar-video/SKILL.md`):
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

- Legenda padrão `captions: clean`: Montserrat Alternates, branca, minúsculas (`caption_case: lower`, siglas ficam
  maiúsculas), 2–3 palavras, na altura de ~62% da tela — como a referência "está rolando".
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
  (`zoom` com `rel: true`, cada item fecha mais); FRASE ESPECIAL `emphasis` com `variant: "atras"` (palavra gigante
  atrás da cabeça, linhas em zigue-zague entrando animadas) — 1 por vídeo (2 se > 45 s); todo destaque entra
  saindo do desfoque. Novos aprendizados: registre com `refs.edit(id, {"learned": [...]})` e na skill editar-video.

## B-roll "modelo viral", emoji 3D e faixa de cima

- `media` com `layout: "viral"`: fundo ônix, o vídeo/foto num quadro quadrado de cantos arredondados no centro, a
  legenda cai dentro do quadro; enquadra a parte de cima do vídeo (deixa de fora legendas que o creator já tinha).
  Vídeos de apoio são sempre MUDOS. `clip_start` = de onde o vídeo começa. `chain: true` = sequência emendada (cada um
  fica até o próximo começar — ex.: "camisetas, suplementos, produtos de beleza"), com clique a cada troca.
- `motion` `emoji3d` (params icon/x/y/size) + `min_dur: 1.8`: emoji com espessura, giro 3D, brilho, partículas; som
  `whoosh_ar_in` + `pop_seco` (offset 0,34). Posicione ao lado da cabeça (x≈0.74, y≈0.2), nunca sobre o rosto.
- `motion` `emojifun` (params icon, mode `slide`|`peek`, x, y, size): emoji ENGRAÇADO "meia-bomba" — `slide` vem da
  esquerda, fica mole balançando acima da cabeça e sai pela direita; `peek` só a cabecinha surge de baixo. Sem
  brilhos/piscadas (o usuário não gosta). `end_w` + `end_offset` = termina logo depois de um ponto da fala (ex.: sair
  após o clique do flash do pós-hook).
- `motion` `acronimo` (AIDA etc.): `params.items=[{letter, word, w}]`, `final_w` (palavra do acrônimo), `title`;
  letras em relevo dourado entram sincronizadas, depois o acrônimo gigante em 3D. Use `hide_captions: true`.
- TÓPICOS: toda enumeração na fala vira `motion` `bullets` automático (itens sincronizados por `w`, legenda comum
  escondida no trecho) — pedido do usuário, vale mesmo com inserções em pausa.
- Itens de motion com `"w"` ganham `"t"` (s desde o início da animação) no compute — sincronia com a fala.
- B-roll em tela cheia (`layout: full`) para a 1ª citação forte de um tema (ex.: "criativos feitos por creators").
- Na timeline, B-roll (coral), animações (roxo) e tela verde (verde) ficam na faixa de cima, arrastáveis.
- Vídeos de creators do usuário ficam em `Ativos Turbo/UGC Creators/`.

## Tela verde (print de fundo, você no canto lendo)

Overlay `{"type":"greenscreen","file":<imagem em assets>,"w0","w1","corner":"bl|br","size":0.52}`. O print ocupa a tela
(rola devagar se for comprido) e você entra RECORTADO (mask_fg, com microfone/cadeira) no canto de baixo; legendas
continuam. AUTOMÁTICO: ao processar um vídeo com prints de apoio, `greenscreen.auto_detect` lê o print (OCR Apple
Vision local, app/ocr.py) e acha o trecho em que a fala bate com o texto. Manual: "Seus arquivos" → 🟩 Tela verde,
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
  (licença livre, uso comercial) + Kevin MacLeod CC BY 4.0 em "Outras"). Músicas em alta do Instagram têm direitos:
  só dentro do app — oriente exportar sem música e adicionar o áudio em alta ao postar. A música NUNCA acelera com `speed`: com speed ≠ 1 ela é mixada
  depois da voz acelerada, em 1x. A música abaixa sozinha quando há fala.
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
  pausa), com FLASH DE CÂMERA (`flash_camera`, sintetizado: obturador + "pshh" do flash) exatamente no corte —
  sempre, mesmo se o usuário ajustou o som/transição à mão; o hook vai até o fim da frase.
- FRASE ATRÁS DA CABEÇA: todo vídeo tem 1 (se nenhuma frase se qualificar, a de mais impacto); valores em dinheiro
  sobem por trás da cabeça. O recorte (mask.mp4) também servirá para fundos de IA no futuro.
- Padrão de vídeo novo: `scene_transition: "leak"` (Luz só nos cortes grandes/troca de cena, ≥ 6 s entre elas),
  `smooth_zoom: true` (cada trecho aproxima ou afasta devagar, ~6%) e `reframe: true` (de vez em quando um zoom seco
  maior). O usuário prefere zoom suave contínuo, principalmente em vídeo gravado sentado.
- Transição num corte = overlay `{"type":"transition","style":"leak|branco|escuro|desfoque","w0":<1ª palavra do trecho>}`;
  ela gruda no início do trecho. Sem overlay = corte seco. Cores sempre da paleta (creme/ônix/coral/dourado).

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
- Cor: `grade: auto` corrige o insumo (HDR do iPhone vira SDR automaticamente). Intensidade em `grade_strength`.
- Sons (pedido do usuário): vídeo falado contínuo NÃO leva sons aleatórios — nada de thump em número, whoosh em
  destaque ou impacto em frase forte. Só entram: (1) o som de expectativa do hook; (2) um CLIQUE (click_classico /
  click_mouse) quando uma imagem/print/vídeo/motion BROTA na tela. Biblioteca em `app/sfx.py` (CATALOG); PROIBIDO:
  ding, notificação, ka-ching, buzzer, boing, vine boom. Cada som tem `lead` (começa adiantado para o pico cair
  no momento) e `gain`; o momento exato = palavra `w0` + `offset` (s) — o usuário arrasta a bolinha roxa na timeline.
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

## Regras

- Custo: o padrão é 100% gratuito. Só use a API paga (`plano <id> claude_api`) se o usuário pedir.
- Materiais de terceiros: prefira as fontes com licença clara; a exportação gera um `.creditos.txt`.
- Código: Python 3.9 (`.venv`), sem build no front (`app/static`). Teste com `amostra` antes de dizer que terminou.

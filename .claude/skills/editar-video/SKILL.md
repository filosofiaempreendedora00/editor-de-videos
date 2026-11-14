---
name: editar-video
description: Direção de edição para vídeos falados (Reels, YouTube, anúncios) neste editor — estilo, ritmo, legendas, movimento e composição. Use sempre que o usuário pedir para editar, melhorar, deixar dinâmico/profissional, criar plano de edição ou inserir elementos num projeto do editor.
---

# Direção de edição (padrão Roberto)

Você é o editor. O objetivo é um vídeo **autoral e nada genérico**, com o mínimo de trabalho do usuário.
Opere a ferramenta pela CLI descrita em `CLAUDE.md`. Feche sempre o ciclo: plano → amostra → revisar quadros →
ajustar → exportar → conferir o MP4 (não só a prévia).

## §-0 PRIMEIRA ENTREGA PERFEITA (síntese de 475 observações dele, 18/10–03/11 — o que mais gerou retrabalho)
Meta dele (03/11): "que eu te envie um arquivo de vídeo e ele já venha perfeitamente pronto". Das 166 observações dos
5 vídeos de 29/10–02/11, ~90% caem em 11 famílias. Cada uma tem uma REGRA e um TESTE. As mensuráveis estão em
`app/auditoria.py` (`auditar <pid>`; roda sozinha no fim do `aplicar-edicao`): **entregar só com 0 ✗ e cada ⚠
conferido**.

1. **Ativo literal à AÇÃO da frase** (~30 obs, a maior fonte de retrabalho). Teste: "quem vê sem som entende o que eu
   tô dizendo?". O ativo mostra o SUJEITO fazendo o VERBO: "insistir só pra provar que tem razão" = reunião com um
   insistindo e os outros desaprovando (não uma porta trancada); "demitidas" = demissão caótica em vídeo (não um
   documento); "a dor piora" = pessoa na cama com dor; "do outro lado da tela" = pessoa rolando o feed entediada;
   "não se deu conta do problema" = comédia muda LITERAL (Keaton cortando lenha com o exército atrás, Chaplin na cabana
   tombando, Lloyd sonâmbula na beirada). Comportamento do DIA A DIA = vídeo de HOJE (discussão, estresse, reunião);
   pintura/arquivo antigo = só para história, conceito ou citação. Referência que ele não conhece = trocar pela mais
   famosa (Prefontaine → Tiger/Serena/LeBron). PROIBIDO: pessoa aleatória que não faz a ação ("menina aleatória"),
   metáfora distante (harém = riqueza, operário = estressado, diagrama = porco, "post vazio"), dragão de "gráfico
   baixo". Confira QUADRO A QUADRO: gente que não pode aparecer (a menina do Sintel), genitália de animal, faixas pretas
   no arquivo, texto/logo estranho. Fato tem que ser verdadeiro (é mesmo a Voyager?). Entra NA palavra (colchões só em
   "colchões") e sai quando a frase acaba (o quarto do Hammershøi até "raio de sol", não no "E no mesmo texto").
2. **Ritmo / densidade** (~18). Gancho: algo novo a cada ~1,5–2 s, nada parado > 3,5 s. Corpo: nunca > 5–7 s sem
   evento visual; um ativo ≤ ~4–5 s; um motion de explicação ≤ ~2,5–3 s antes de algo novo ("medo de perder o lead").
   Frase abstrata ("exprimir as ideias pra máquina", "boas ideias", "resultado genérico") = motion/visual, nunca só
   legenda. CTA e fecho SEMPRE com inserção (nunca "cru"). Itens numerados ("a primeira…", "a segunda…") começam com
   o ROSTO + o número gigante atrás.
3. **Gancho** (~12). Rosto em 100% (tela dividida com o fundo normal; nunca ele pequeno/recortado no canto).
   Energia desproporcional: 2–3 ativos do mesmo tema, número gigante atrás, CARIMBO das palavras-chave do gancho
   (DESCONTO dourado / IGNORAR coral). Movimento (zoom lento que não invade as bordas). Efeito de fundo (Lua, cenário)
   só DEPOIS do gancho, entrando com a onda do estalo. O pós-gancho MUDA de formato (dividida → ele aberto, ou o contrário).
4. **Transições** (~12). Só onde a cena muda — antes ≠ depois ("milhões de vezes"). Toda troca de TIPO de cena tem
   transição + som: de ele para a tela dividida = luz + obturador; voltar para ele = desfoque + clique; entrar numa
   foto de tela cheia = desfoque + som. A palavra que abre a cena nova ("Agora…") vem DEPOIS da transição. Nenhum
   quadro dele sozinho entre o corte do gancho e a tela dividida. Fecho muda de formato com transição + som.
5. **Sons** (~15). Só com evento na tela e SEMPRE como sfx (bolinha roxa — som sem bolinha ele estranha).
   Semânticos: escrita = teclas (baixas: −11 dB), régua do tempo = mostrador sincronizado, dinheiro = caixa
   registradora, aro desenhado = pop curto, cada item/perfil/degrau = clique. NUNCA vento/whoosh/riser. Pico no
   instante exato (o riser adiantado 2 s foi cobrado). Som de fundo longo (coro) entra do zero, cresce e não pode soar
   em loop. Música do gancho para seco no estalo; silêncio até a frase que ele pedir (`musica.entra_em`).
6. **Motions "artesanais, não IA"** (~18). Nada de retângulo geométrico cru: papel, serifa, textura, luz (o
   "jornalzinho" virou página impressa). Texto com ar (nunca grudado nos retângulos), nada vazio (feed com fotos,
   avatares com rostos reais, marca fictícia com logo). Destaque um item por vez, na palavra exata. Citação = aspas +
   maiúscula + recurso de citação (máquina de escrever; mármore com aspas de ouro). Traço orgânico (pincel, não
   "paint"); cabeças com proporção humana; nada de folha em branco > 0,5 s antes do texto.
7. **Número gigante atrás dele** (~15). GRANDE (ocupa costas e ombros), SEMPRE de baixo (`enter: up`), empilhado
   (número em cima + unidade MAIÚSCULA garrafal embaixo, Anton, grande o bastante para ver um pedaço do I ao lado da
   cabeça), cor só quando ele pedir (5 e 50 dourados; 2 branco), recorte HQ obrigatório.
8. **Recorte / fundo trocado** (~8). Tudo que vai ATRÁS dele usa o recorte HQ (Vision) — o comum pega coqueiro e
   parapeito. Fundo trocado parado, sem blocos de compressão (sem granulação parada no escuro), objeto redondo de
   verdade (a Terra amassada foi cobrada).
9. **Legendas** (~8). Toda palavra dita aparece (inclusive a 1ª depois de um corte — corrigido na timeline em 03/11).
   Nome próprio com maiúscula (automático). Palavra-espelho do gancho em CAIXA ALTA dourada ("REALIDADE"). Legenda
   acima da cabeça num momento de impacto. Nada de pontuação vinda da transcrição ("Schwartz?").
10. **Layout** (~8). Preferir TELA DIVIDIDA 45/55, inclusive motions ("senti falta de mais telas divididas"); tela
    cheia para vertical forte; tvzinha curta; o fim pode ficar em tela dividida até o último quadro (`fim: true`).
11. **Acabamento técnico** (~12). Faixas pretas do arquivo cortadas; nada de vai-e-volta nem congelado (plano tem que
    cobrir a janela, `shot_end` desacelera até 0,6×); nada por cima do rosto; sem zoom duplo; motion de tela cheia
    sai só esmaecendo (encolher mostrava a cena de trás); prévia = exportação.

**Processo de primeira entrega**: crivo + este §-0 → plano (cada frase-chave pelo teste do item 1; gancho com 3+
trocas; CTA com inserção) → `aplicar-edicao` → ler o relatório e a AUDITORIA (0 ✗) → render completo → quadros de cada
troca de cena + medir o áudio das trocas → só então entregar.

## §-1 ANTES DE TUDO: o crivo iterativo dele
Rode `.venv/bin/python -m app.cli crivo` e LEIA `roteiros/crivo_edicao.md` (gerado das observações que ele faz direto
nos vídeos, por tema, com as palavras dele e o que resolveu; peso ★★★ publicado / ★★ editado no kanban). Antes de
entregar QUALQUER vídeo, confira cada tema do topo da lista nele (não pode repetir erro já cobrado). As referências
aprovadas (editado/publicado) são modelo de boas práticas — não de identidade.

**✦ DESTAQUES (peso máximo, 25/10):** a seção do topo do crivo traz a RECEITA dos vídeos da coluna "Destaques" do
kanban (publicados e muito acima da média — 1º: V005 Epicteto, ~5× a média): hook visual (o ativo real mostrando o
gancho acontecendo, em câmera lenta, terminando no estalo/corte), sequência de ativos, motions e o que ele cobrou.
Em TODO vídeo novo, modele esses PRINCÍPIOS antes dos demais (hook visual tão forte quanto, mesmo ritmo de troca,
mesmo cuidado com o sentido de cada ativo) — sem copiar cena por cena.

**NUNCA RETRABALHO (puxada de orelha dele, 20/10 à noite: "terceira ou quarta vez que eu peço… não quero ter mais
retrabalho nunca mais com coisas que já te pedi")** — antes de dizer "pronto":
1. `observacoes <pid>` com as RESOLVIDAS também: para CADA uma daquele vídeo, abra o quadro do MP4 final naquele instante
   e confira que continua resolvida (um ajuste novo pode desfazer um antigo: o planeta voltou a cobrir o "Agora, repara").
2. A PRÉVIA tem que mostrar o mesmo que o MP4: o servidor roda com `--reload` (`iniciar.sh`); se ele foi aberto antes
   de uma mudança em `app/*.py`, a prévia calcula a timeline VELHA (20/10: carro, planeta e "travada" que só existiam
   na prévia). Confira `curl /api/projects/<id>` × `timeline.compute` local quando ele relatar algo que o MP4 não tem.
3. Sons: `tecla_maquina` e `datilografando` estão REPROVADOS ("péssimo barulho, não usar mais") — clique padrão.
4. Texto de motion NUNCA no rosto: na tela dividida ele se apoia na DIVISA (`divisa: true` no plano) com painel sépia;
   frase de destaque alinhada à ESQUERDA (ou direita), nunca centralizada; o destaque sai quando a cena troca.
5. Lista falada com entonação de lista (3 itens) = 3 B-rolls emendados com clique OU lista grande com clique —
   nunca legenda flat sobre fundo flat. Nada de emoji para "impressionar": efeito real (fundo esquentando, fumaça).
9. ENSAIO/PLANO DE EDIÇÃO (26/10, V011/V019): com plano, `scene_transition: "none"` (no `config` do plano e no projeto) — a luz
   automática dos cortes grandes não sabe onde o plano troca de cena e caía no meio de um B-roll ('essa'). A voz de IA
   do ensaio INVENTA frases nas pausas (palavras de duração ~0: 'Mas, não é o que você quer fazer') e o corte automático
   tira frases reais que começam igual ('E é aqui…', 'E você?'): confira `deleted` e as palavras de duração ~0 SEMPRE.
   Print de tela inteira na tvzinha fica minúsculo: recorte a parte que importa. Frase de destaque com `min_dur` 1,8.
8. LEGENDA NUNCA COM CAIXA (22/10: "só branca, com contraste, sem background — principalmente no arquivo final"): onde a
   timeline marcaria `box` (divisa, artigo, tela verde, fundo claro) vira `strong` (sombra maior/mais escura). Caixa só
   se ele ligar `caption_box`. TEXTO DATILOGRAFADO (`maquina`): escrito no ritmo da fala (items `line`/`end` ancorados),
   som de tecla macio por letra (`add_typing`, Mixkit 1119) — `tecla_maquina`/`datilografando` reprovados.
7. CRIATIVO COM NARRAÇÃO + APRESENTADOR (Eleveme 21/10): produto só quando é CITADO (ou numa característica dele:
   "mais alto" = salto da palmilha, "conforto" = a macia); no resto, o apresentador MUDO tirado dos intervalos entre
   tomadas — só trechos de frente para a lente (pose do Vision perto da da tomada boa) e compostos: nada de olho
   fechado, risada, olhar para cima/lado ou aceno ("ficou muito claro que são takes de erro"). Meio-termo ~4 dele : 6
   do produto; se faltar tomada boa, apele para o produto. Fim nunca nele olhando para o alto: feche no produto.
6. FALA TRUNCADA NO MP4 (21/10: "'mundo inteiro' ficou 'mundo intê…', 'sentir' ficou 'senti…'"): o fim de palavra do
   Whisper chega antes do fim do som e o MP4 corta no ponto exato (a prévia esconde, porque pula de pedaço com atraso).
   `timeline.extend_speech_tails` estende cada trecho até a voz morrer no áudio (env10ms.npy), os fins arredondam
   para CIMA no quadro e pedaços vizinhos nunca se sobrepõem. Toda exportação roda `timeline.audit_cuts` e imprime
   "⚠ cortes:" — se aparecer, conserte antes de entregar. Nunca corte "no fim da palavra" à mão sem folga.

10. GRAVAÇÃO REAL DEPOIS DO ENSAIO (V011/V014/V019, 01–02/11): ele fala mais devagar que a voz de IA, então as cenas do
   plano ESTICAM (porco 11 s, Sagan 8 s, morro 10 s). Depois do `aplicar-edicao`, liste as janelas no tempo de SAÍDA
   (`timeline.compute` está antes do `speed`: divida por ele) e quebre toda cena > ~4 s (tvzinha > ~2,5 s) com outro
   ativo REAL da frase (pintura que encena a ideia, o bicho de verdade, o documento); motion que se estica por cima de
   uma fala que é DELE (a virada, a tese) → `solo` explícito. Gancho sem o rosto dele (motion de tela cheia) = erro:
   vira `greenscreen` com o artefato (foto vertical com o detalhe marcado, rolando devagar). Tela verde precisa do
   `fg_alpha.webm` (`background.ensure_cutout`) para a PRÉVIA mostrar ele recortado. Cards do gancho começam abaixo da
   barra do Reels (8,5%). Comentários 🎬 abertos no roteiro (`comentarios V0NN`) entram NESTA edição e são resolvidos.

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
- **OBSERVAÇÕES DE 29/10 (V011 + V019) — valem para todo vídeo**: (1) MUITO mais tela dividida `meio` (o V005 tinha 22
  de 30 ativos assim) — inclusive motions: `layout: "meio"` num motion do plano → `aplicar-edicao` renderiza o motion na
  faixa de cima (`motion_<tpl>_<hash>.mp4`) e ele fica embaixo, legenda na divisa; templates com layout de faixa:
  `celular`, `anuncio`, `niveis`, `cliches`, `raro`, `perfis`, `dosdonts`; (2) tvzinha ≤ ~2,5 s ("durou muito tempo esse
  b-roll de tvzinha") e cena > ~3,5 s vira duas ("as cenas muito longas, monótono"); (3) o ativo entra NA palavra
  ("os colchões só quando for citada a palavra; antes precisa ser meu rosto introduzindo"); (4) mostrar o que é dito,
  nunca um diagrama no lugar ("não faz sentido mostrar algo diferente do porco quando eu cito ele"); (5) motion sem
  subtítulo que só repete a fala ("menos cara de IA"); (6) plano de arquivo + `speed` 1,3 acaba antes da janela e
  CONGELA ("ficou travado") → `shot_end` = duração do arquivo (desacelera, nunca congela); (7) celular/feed nunca com
  posts vazios ("muito espaço em branco"); (8) "resultado genérico" → os CLICHÊS de IA marcados (`cliches`), "boas
  ideias" → um motion (`raro`: a parede genérica e UM cartão dourado); (9) às vezes ele quer SÓ ele falando ("prefiro
  só eu falando aqui") — `solo` explícito; (10) nunca terminar mostrando algo já mostrado.
- **SEM CARA DE BANCO (V014, 29/10: "achei meio palha… evitar ao máximo vídeos com cara de banco")**: Mixkit/Pexels
  é ÚLTIMO recurso. Para o "genérico" (comportamento, trabalho, discussão, gente comum) use ARQUIVO REAL: filmes de
  orientação de domínio público dos anos 1940–50 (Prelinger, archive.org — `advancedsearch.php` com
  `collection:prelinger`, arquivo `<id>.mp4` 640x480; ex.: *How to Keep a Job* 1949 = ficha de emprego + aviso de
  demissão, *The Bright Young Newcomer* 1958 = crítica vira ofensa, *Shy Guy* 1947 = aluno que não pergunta, *Control
  Your Emotions* 1950), cinema/filmagem de rua de 1900 (*A Trip Down Market Street*, 1906), pintura clássica que
  encena a ideia (Napoleão na retirada de Moscou = insistir no erro; Jan Steen, *Discussão num jogo de cartas*), NASA
  (Earthrise da Apollo 8 com zoom-out). Arquivo 480p → `viral` (tvzinha), nunca dividida esticada. Recorte o PLANO
  exato (sem pegar o corte seguinte) e tire marca d'água pelo crop.
  Revisão V011/V019 (29/10, "fugir do commodity e do clichê", 20 Mixkit trocados): (1) quando a fala é sobre o
  trabalho DELE, grave a tela REAL — o pedido dele em português virando o código que a IA escreveu, o arquivo de
  regras com marca-texto, o editor tocando um projeto (CDP no Chrome invisível: `Page.captureScreenshot` com `clip`,
  avançando `#video.currentTime`); (2) "uma pessoa que…" hipotética = UM personagem de um mesmo filme antigo em
  várias cenas (*Rest and Health* 1949: despertador, senta travado na cama, largado no sofá, acordado de madrugada;
  *Health: Your Posture* 1953: a régua na coluna torta = "problema que ela nem enxerga"); (3) o que acontece NO
  CELULAR dela vira o motion `celular` (enxurrada de anúncios de desconto / busca com marca-texto / comentários →
  comparar → Seguir), no universo da marca do anúncio — nunca mão segurando celular de banco; (4) ideia abstrata →
  o documento histórico que a encarna (Darwin "I think" = ideia saindo da cabeça; ENIAC = instruir a máquina com
  precisão; Ford 1913 = resultado igual para todos; Leonardo e os pássaros = repertório; mãos de Pettakere =
  criatividade antiga); (5) fotos de produto sem marca: os planos Technicolor de *American Look* (1958).
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

**5. Gancho**: o ROSTO DELE em 100% dos ganchos (29/10: "ou eu full ali ou eu com fundo verde") e SUPER CHAMATIVO
("cadê os hooks fodas como dos melhores vídeos?"): `greenscreen` (o ativo de fundo — ex.: o feed de descontos rolando —
e ele recortado no canto), `hook_cards` (artefatos reais em cards, odômetro com o número, carimbo) ou prints+soma do V001.
Nunca motion de tela inteira/tvzinha cobrindo a cara dele, nunca só ele falando sem nada na tela nos primeiros segundos.
Elementos NA TELA (como os prints+soma do V001; `hook_cards` com quadros reais, etiqueta, carimbo,
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

- (Liquid Death, 19/10) TRANSIÇÃO = TROCA DE CENA DE VERDADE: nunca luz/clique e voltar para o mesmo ativo ou para
  ele do mesmo jeito. Ativo casa com a FRASE exata ("latas de energético" → as latas). Marca citada → ativo FORTE da
  marca (varejo, comercial), não banco genérico. Sem PALAVRA VIÚVA (legenda e destaque). Sem plano isolado ~1 s.
  FIM (29/10, substitui a regra antiga do B-roll final): o vídeo termina NO ROSTO DELE, SEMPRE (`timeline.FIM_ROSTO`).
  Valores em dinheiro: contador subindo +
  `caixa_registradora`. Palavra de impacto sobre B-roll claro → motion `palavra` (faixa escura, letra por letra).
  Motions longos (> 3 s) nunca parados: algo se mexendo o tempo todo (`produto_oferta` v2 é o modelo).
- (20/10) LEGENDA: largura medida na fonte real ≤ 86% (nunca encosta nas bordas); nunca atravessa troca de cena
  (quebra no corte); divisão ótima por frase (timeline.caption_chunks). Texto dourado em DEGRADÊ = "cara de IA":
  prefira dourado chapado + versalete creme espaçado. Riscados: um item por vez, grande, traço de marcador + som.
  Fecho: a luz de entrada leva som; CTA "encaminha" → `aviaozinho`. Mídia no instante exato: `start_src` (ex.: estalo).
  TV de verdade: chroma key (comercial atrás da moldura). Música curta: loop com crossfade (automático).
- (Jung/Epicteto, 20/10) ELE SOZINHO = câmera viva: ciclo aberto+aproxima → fechado+afasta → aberto PARADO → médio+
  aproxima (automático) e, logo DEPOIS de B-roll, ele volta com zoom-in leve. Pediu a cara dele num trecho ("fiz cara
  legal") → `{"type":"solo","em":…,"ate":…}` no plano (nenhum ativo cobre, nem as regras de emendar). Legenda em cima
  dele SEMPRE abaixo do queixo medido no instante (`face_track`, +8% pela barba). Motion de texto embaixo (círculo,
  limiar…) → plano aberto e o trecho solo (no 50/50 o texto caía no rosto). Vídeo HORIZONTAL nunca em tvzinha
  (`viral` = bordas pretas): `meio`. Nada de ativo < 1,2 s (parece bug): numa lista, roube tempo do vizinho mais longo.
  Ativo tem que ter a ver com a FRASE ("crise" ≠ gráfico; "ecoou no tempo" ≠ Coliseu; balões aleatórios) e a pessoa
  citada tem que ser reconhecível (o retrato mais conhecido dela). Frase genial merece motion próprio (subliminar,
  dicotomia), não destaque padrão. Bandeiras/países: `bandeira`. Estudo citado: `artigo` (papel + marca-texto).
- (Joshie, 20/10 noite) Riscados = LISTA limpa (bullet, uma linha por item, risco fino e reto de ponta a ponta, um
  por um, clique só quando o item entra — nada de marcador grosso/swipe). Estalo NÃO mistura som (o estalo dele é o
  som). Ele sozinho → tela dividida = luz quente SEM som e ele já parado embaixo. Pós-hook é dele (`solo`). Sem
  microcorte (< 0,15 s). Prévia travando = vídeo pesado → cópia leve (automática > 18 Mbps). Lettering do gancho no
  topo fica ABAIXO da barra do Reels (8%) e acima da cabeça.

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

## 15. Observações de 02/11 (V014, V019, V018, V015 — gravações reais) — valem para TODO vídeo
- **GANCHO = TELA DIVIDIDA com ele no FUNDO NORMAL** (não a tela verde com ele recortado no canto: "fiquei pequeno demais
  no canto e mal cortado", "não queria eu sem fundo no canto, e sim modelo de tela dividida no hook"). O ativo do gancho
  vai na faixa de cima (`meio`, motion na faixa se for o caso: `pontinho`, `celular` enxurrada…). Tela verde só para
  PRINT sendo lido. O gancho ACABA na frase que ele indicar (`gancho_t`) e o plano seguinte é OUTRA disposição (outra
  tela dividida com outro ativo — V014: "depois de 'nele' tem que ter transição e acabar o hook").
- **NUMERO GIGANTE ATRÁS DELE** (`behind` + `big`, app/bignum.py) é um efeito que ele AMA: use em números marcantes da
  fala com ele em quadro cheio (V011 gancho, V015 "100 mi"); símbolos também (`+`/`−` no CTA do V015). Texto curto
  (`sup: "mi"` em vez de "milhões" — senão encolhe e perde a força).
- **NUNCA vai-e-volta** em vídeo de apoio ("ativos que vão forward e são rebobinados… parece que você bugou"): o plano
  escolhido (`clip_start`..`shot_end`) tem que cobrir a janela (até 0,6× de câmera lenta). Plano curto → outro ativo,
  ou CORRENTE de dois planos (`chain`). O render/prévia agora deixam o vídeo seguir em vez de rebobinar.
- **Ativo LITERAL à frase** (as reprovações do dia: harém para "riqueza", Fuseli para "medo do que não aconteceu",
  operário para "estressados", Colosso para "a mente preenche as lacunas", Monet para "clareza", menina com régua para
  "não enxerga", rapaz acordado para "a dor piora", Prefontaine que ele não conhece, veado em vez de potro). O que
  passou: moedas de ouro romanas, "Esperando o veredito", homem atolado no telefone, a SOMBRA do Nosferatu, névoa se
  dissipando, Keaton sem ver o exército atrás, mulher com dor na cama, Keaton tranquilo na moto sem piloto, Tiger/
  Serena/LeBron com o swoosh, Apple Watch Nike+ (duas marcas juntas), potro levantando com a mãe. Pessoa famosa só se
  ELE conhece.
- **"Jornalzinho" (motion `artigo`) = página IMPRESSA de verdade** (v3): mesa de madeira com luz de luminária, serifa de
  revista, borda irregular, fita crepe, parágrafo em volta fora de foco e marca-texto feito à mão. Nada de retângulo
  geométrico ("parece IA"). Em tela dividida. Some na frase seguinte ("quando cito os pesquisadores já era pra ir pra
  próxima cena").
- **5 níveis (motion `niveis`) na faixa**: texto centralizado com ar em cima, escada embaixo (nada encostado nos
  degraus) e SOM a cada aparição: `snap_suave` quando o ponto pousa no nível (offset 1,1 s) e um `click_mouse` por
  degrau que sobe.
- **Final SEMPRE com inserção** ("final cru" reprovado 3×): o CTA ganha algo — o mapa do vídeo de volta (V019: a escada
  dos 5 níveis no "cinco níveis de consciência"), número/símbolo atrás dele (V015), ou um EFEITO análogo ao do Epicteto
  (V018: `calor` com `image` — o cenário do gancho surgindo ATRÁS dele no "só existe na sua imaginação"). Termina no rosto.
- **Sons**: o riser tem `lead` de 2,1 s — ancorado na palavra ele começa ANTES da cena ("apareceu antes"): para subir
  junto com a animação use `offset` = lead. Texto se escrevendo = som de ESCRITA (`datilografando`), nunca riser/whoosh
  ("parece vento"). Obturador de troca de cena onde não há troca de cena = ruim (V014 CTA; V015 'outra marca').
- **Música só no gancho** (`musica_gancho` no plano: toca até o `gancho_t` e PARA SECO; a trilha entra no corte) —
  V018: coro infernal ("Land of the Dead", Kevin MacLeod, CC BY — crédito na legenda do post).
- Legenda: nomes como "Terra" (o planeta) no vocabulário; citação datilografada começa com MAIÚSCULA e entre aspas.

## 16. Observações de 02/11 no V011 (2 habilidades) — valem para TODO vídeo
- **Número gigante atrás dele: GRANDE de verdade** ("preencha minhas costas e ombros, não só o topo da cabeça"): um
  algarismo sozinho com `cap: 0.52, top: 0.06` (o "2" envolve a cabeça, a diagonal e a base aparecem dos lados). Número
  + unidade = EMPILHADO: o número em cima (`cap ≈ 0.255, top 0.05`, quase todo acima da cabeça — senão a cabeça "come"
  a barriga do 5) e a unidade MAIÚSCULA embaixo (`under: "mil"`, `under_spread: true` = letras de ponta a ponta, o M e o
  L INTEIROS dos dois lados da cabeça; `under_top: 0.38` = na altura do pescoço, mais estreito que a cabeça — junto da
  cabeça o M virava "n" quando o gancho aproxima). Teste o layout com a folha de quadros no fim do zoom do gancho.
- **Itens numerados começam com o ROSTO dele + o número atrás** ("quando falo de itens de números é bom começar com
  meu rosto pra padronizar"): "A primeira delas…" → `1` atrás; "A segunda habilidade…" → `2` atrás; o ativo entra na
  frase seguinte. O número do gancho pode VOLTAR atrás dele no loop ("unir aquelas duas habilidades").
- **Tela dividida do pós-hook entra JÁ no corte do gancho** (nem 1 quadro dele sozinho). A luz do pós-hook vale pela
  troca de cena (aplicar-edicao tira a duplicada).
- **Motion que destaca o que ele CITA = um elemento por vez** (perfis): o citado cresce com o aro e a etiqueta, os
  outros encolhem, apagam e perdem a cor; a troca cai na palavra exata. Palavra da transcrição grudada ("do outro, um")
  → item com `off` (s) depois da âncora.
- **Mais de ~6 s só ele com legenda comum = reprovado** ("sem nada dinâmico", "algo mais chamativo"): na explicação
  abstrata, VISUALIZE o argumento — o pedido VAGO × o pedido PRECISO na conversa com a IA (`cliches` com `who`,
  `mark: "gold"`, item `type`), pianola tocando sozinha para "a IA faz sozinha", o número de volta atrás dele.
- **Som que combina com a cena**: o "rebobinar" foi reprovado na régua do tempo → mostrador girando (tique por marco,
  "clac" ao travar; automático no motion `tempo`). Texto sendo digitado = teclado (automático em `cliches`/`maquina`,
  inclusive na faixa da tela dividida). Dinheiro dito ("valem muito hoje") = `caixa_registradora`.
- **Emoji só quando ele pede, e com sentido**: 🤮 ao lado da resposta genérica (`cliches` `emoji`).
- **Desenho de pessoa = proporção humana** (as cabeças "pareciam 2 feijões"): perfil com testa, nariz, lábios, queixo e
  pescoço.
- **Fecho com troca de formato**: sem corte real não há transição — no plano, `corte` + `transition` + som no início do
  CTA, e o CTA muda de formato (V011: o fundo atrás dele vira a parede das mãos de Pettakere, `calor` com `image`).
- **Legenda em outra altura num trecho** (`{"type": "legenda", "em", "ate", "y": 0.155}` no plano — V019 "pode soar meio
  contraditório" acima da cabeça, "pra dar um tchan"). Toda palavra falada TEM legenda: a frase de destaque não estica
  além da próxima palavra (antes o `min_dur` engolia "de compra"), e o fim de frase dito baixo (`bg`) colado na palavra
  anterior aparece ("acontecido").
- **Nunca transição entre duas cenas iguais** (ele → luz → ele): a tela dividida do gancho vai até o fim do gancho.
- **Foto com movimento**: `kb` no media = quanto a foto aproxima na janela (0,22 no logo do gancho do V015; negativo
  afasta). Marcar marcas num vídeo (V015 Apple × Nike): aros dourados desenhados à mão + o nome, acompanhando o
  deslize da câmera, gravados por cima do próprio arquivo (`applewatch_nike_marcado.mp4`).
- **Animação em vez de imagem fraca**: "o anúncio que funciona em um nível não funciona em outro" = a escada `niveis`
  continua com o selo do anúncio (items `ok`/`no`: ✓ no nível 4, desce para o 1 com ✗ coral).
- **Fundo trocado que não casa com a luz dele = tela dividida**: o fecho da imaginação do V018 virou o Goya (sépia
  escuro) na faixa de cima e ele embaixo — recorte falhava no cabelo e o papel claro não combinava com a noite. Som do
  fecho = o coro do gancho voltando baixinho (`sfx/coro_imaginacao.wav`), nunca whoosh.
- **Banco de vídeo liberado quando ele pede** ("evitando clichês, mas com mais fit"): Pexels/Mixkit com gente real e
  natural (porta trancada para "insistir no erro", caixa FIRED, casal discutindo em casa, bebê andando segurando a
  mão da mãe, notebook com os selos Intel/NVIDIA para "quem está do lado dela"). Comédia muda em domínio público para
  "não percebe o problema" (Harold Lloyd sonâmbula, Chaplin na cabana à beira do abismo). Sintel: só planos SEM a menina.
- **Potro/animais**: conferir quadro a quadro se não aparece genitália (o plano do potro levantando foi reprovado).
- **Música**: varie a trilha entre vídeos usando o 🏆 Hall da fama (a do destaque + candidatas com a mesma energia; ele pediu 'pelo menos umas 3'). Nunca a mesma faixa em todos os vídeos.
- **Gancho sem monotonia** (V015 02/11: 'mais dopamina, como o do Epicteto'): troca visual a cada ~1 s — logo → o símbolo num produto real → ele com o NOME gigante atrás (behind big `NIKE`) até o corte.

## 17. Segunda leva de observações de 02/11 (V014, V018, V015) — valem para TODO vídeo
- **Número gigante SEMPRE de baixo** (`enter: "up"` em todo `behind` `big`); unidade embaixo (`under`) com as letras
  PERTO da cabeça (`under_w ≈ 0.62`, não de ponta a ponta) — "achei o M e o I muito separados".
- **Pós-gancho muda de FORMATO** ("milhões de vezes": tela dividida → tela dividida não serve): se o gancho é tela
  dividida, o pós-gancho é ele em tela cheia/aberto (ou o contrário). V014: ele GRAVANDO DA LUA com a Terra no alto
  (fundo trocado no vídeo inteiro, foto real da NASA, recorte HQ do vídeo todo, fundo parado e quase sem desfoque).
- **Citação dita = recurso visual de citação**, nunca só legenda: a máxima "contratadas pelas habilidades e demitidas
  pelo comportamento" datilografada ENTRE ASPAS (`maquina` com `lines`); frase do Sêneca no mármore com ASPAS grandes
  em folha de ouro (template `inscricao`) — e o mármore entra logo antes da 1ª linha (nada de "folha em branco" parada).
- **Toda entrada numa cena de tela cheia tem transição + som** (o pontinho entrando "seco" foi reprovado): `corte` +
  `transition` (desfoque) + `whoosh_ar_in` no início da frase.
- **Algo sendo desenhado/marcado na tela = som com bolinha roxa** (pop curto `pop_seco` em cada aro), nunca efeito sem
  marcador na timeline.
- **Ativo literal ao que ele diz** (porta trancada ≠ "insistir só pra provar que tem razão" → reunião em que um insiste
  e os outros desaprovam). Dragão escuro da caverna do Sintel (cristais azuis, olho vermelho) — o dragão amarelado no
  céu foi reprovado ("gráfico baixo, amador"). CTA "falar mais alto" = o dragão abrindo a boca e rugindo fogo.
- **Tela dividida pode ir até o FIM** ("não precisa acabar comigo"): `fim: true` no último ativo.
- **Fecho com o cenário do gancho se CONSTRUINDO atrás dele** (V018): `calor` com `image` = vídeo (folha lisa → manchas
  da gravura surgem desfocadas e ganham foco → todos os morcegos nítidos no fim), mesmo recorte/cor do gancho.
- **Palavra-espelho do gancho também destacada** ("imaginação" × "realidade"): a segunda em CAIXA ALTA dourada
  (`destacar`).
- **Nome próprio sempre com maiúscula** (nome E sobrenome): agora automático para maiúscula no meio da frase.

## 18. V023 (09/11, tapa-olho da Hathaway — 1ª edição direto da gravação, sem ensaio) — valem para TODO vídeo
- **Busca de ativos de uma história de marca antiga**: o acervo da própria empresa costuma estar num MUSEU (Maine State
  Museum: a fábrica da Hathaway em 1937, o anúncio original em alta, a charge da New Yorker de 1952) — procure o museu
  da cidade/estado da marca antes do banco. Concorrentes da época: Commons (Arrow 1949). Filmes de época: Prelinger
  (archive.org) via subagente com folhas de contato — e ele tem que dizer quando NÃO achou (a "olhada dupla" não existe
  em domínio público).
- **Não achou o arquivo da AÇÃO? Faça a ação com os artefatos reais**: "o cérebro não consegue passar reto… para, olha de
  novo" = animação própria (PIL → mp4 1080x806, a faixa da dividida): a câmera passa reto por uma fileira de anúncios dos
  anos 50, passa do homem do tapa-olho, freia, VOLTA e aproxima no rosto, no ritmo da fala (`olha_de_novo_revista.mp4`).
- **Arquivo 480p 4:3 = tvzinha**: o limite de "vídeo largo → meio" agora é ar > 1,4 (antes 1,35: um 4:3 com a borda preta
  aparada, 638x472 = 1,352, virava tela dividida esticada). Ao trocar um arquivo que o projeto já copiou, APAGUE a cópia em
  `projects/<id>/assets/` (o `aplicar-edicao` não recopia o que já existe).
- **Citação longa (3+ linhas) datilografada vai para a FAIXA de cima** (`maquina` com `layout: "meio"` +
  `hide_captions_meio`): papel na mesa com luz de luminária, ele embaixo. Em cima dele, o papel de 3 linhas descia até a
  interface do Reels (a `maquina` agora tem modo faixa).
- **Frase de destaque = plano ABERTO e quase parado** (automático em `timeline.split_pieces`): num plano fechado o queixo
  desce para ~73% e o bloco ia até ~94% (embaixo da interface do Reels). Confira na folha que a última linha fica ≤ ~88%.
- **Palavra com hífen** ("tapa-olho", "aceitá-lo"): o Whisper partia em duas e a legenda mostrava "tapa -olho" e até um
  "-olho" sozinho na linha — agora junta na transcrição; em projeto antigo, `texto <id> i i+1 "tapa-olho"`.
- **Destaque terminando na palavra-chave pode engolir uma palavra**: "o que será que aconteceu [com] aquele homem?" com
  key "aconteceu" deixou o "com" sem legenda (auditoria ✗) — use a ÚLTIMA palavra forte da frase como key ("homem").
- **Ativo de 316 px numa tvzinha = cortado e sem a marca**: na dúvida, um ativo bom só (a Arrow de 1949) > dois fracos.
- **Rodada 2 do V023 (09/11, "de longe o que você mais acertou")**: (1) FUNDO TROCADO a pedido dele ("pareça que estou num
  ambiente mais profissional do que a sala da minha casa"): parede de estantes da Ante Library de Chatsworth recortada
  9:16 SÓ nas estantes (o piano atrás dele distraía) → `fundo <pid> file:<plate>`, recorte HQ do vídeo inteiro
  (`recorte-hq`), `bg_blur` 1 e `smooth_zoom` off; teste em 16 quadros espalhados ANTES de aplicar (cabelo, ombros,
  vão entre braço e corpo, cantos de baixo). Para testar composições com `-ss`, busque 2 s antes e corte na saída (`-ss`
  de entrada na máscara e no .mov dá carimbos diferentes e ele "some" do quadro — falso alarme). (2) NÚMERO/SÍMBOLO
  ATRÁS DELE com HALO ônix suave (bignum v3, automático): na parede branca o creme não tinha contraste. (3) Negrito do
  roteiro com número por extenso ("**trinta mil dólares**") casava "trinta" com o "tinha" falado antes do "30" —
  `match_highlights` agora troca número por extenso por algarismo. Negrito de palavra que se repete na fala (o
  "**tapa-olho**" só no "só que de tapa-olho"): o casamento por ordem pega a 1ª ocorrência — marque à mão com
  `destacar <pid> <i>` (o `hl` manual sobrevive ao reaplicar).
- **FUNDO TROCADO QUE NÃO DENUNCIA (10/11, "a biblioteca ficou forçada… com os meus movimentos fica evidente que é falso;
  quero praticamente irreconhecível")**: o que entregava não era o recorte, era a FOTO: biblioteca escura e quente com luz
  de cima, lombadas 100% nítidas e foto de baixo para cima, atrás de alguém com luz de dia, fria e frontal. Regra: o
  cenário tem a MESMA luz dele (dia, clara, parede clara como a da sala dele — aí qualquer sobra de borda some), foi
  fotografado na ALTURA DOS OLHOS, a uma distância de cômodo, e leva o desfoque de lente de celular a ~1 m (`bg_blur` 7
  no quadro 1080 — "sem desfoque" do Jung valia para o estalo; fundo nítido atrás de gente = papel de parede). Parado
  (`smooth_zoom` off). Padrão atual: `backgrounds/fundo_escritorio.jpg` (escritório claro com janela, Unsplash CC0) — o
  MESMO cômodo em todos os vídeos dele. Números atrás: creme com o halo ônix (o escuro se misturava ao cabelo dele).

## 19. V022, V021, V020, V017 (10/11 — os 4 vídeos editados em sequência depois do V023) — valem para TODO vídeo
- **MÚSICA BAIXA**: no V023 ele mesmo baixou a trilha de 0,12 (−14 dB no slider) para **0,0166 (−31,5 dB)**; o ★ V005
  está em 0,01. É o nível padrão do plano (`musica.vol`). Continua indo SEMPRE no MP4.
- **Pergunta com duas metades** (🎬 do V017, "tornar isso em legenda mais marcante"): duas frases de destaque SEGUIDAS, uma
  por metade, cada uma com a sua palavra-chave dourada ("a PROFISSÃO que mudou…" / "ou quem NASCE com…") — exceção
  consciente ao "nunca dois destaques seguidos". Frase de destaque: no máximo 7 palavras (`EMPH_MAX`).
- **Motion pedido em 🎬 = animação própria sobre o artefato real** (o modelo 3D BodyParts3D da cabeça com o hipocampo
  recolorido de vermelho para dourado; a folha timbrada da N.W. Ayer escrita à mão; o bilhete; a conversa no celular).
  Na faixa de cima (1080x806): nada importante nos 10% de cima (a faixa corta ~5%) e nada nos 12% de baixo (a legenda
  fica na divisa); etiquetas em versalete ≥ 30 px. Animação longa (> ~6,5 s) vira 2 arquivos emendados (a auditoria mede
  cada ativo) e precisa de um evento visual novo a cada ≤ 7 s também DEPOIS dela.
- **Gancho com slogan/texto impresso**: o `pontinho` aproxima no texto — escolha o artefato com a letra GRANDE (o "A
  diamond is forever" pintado de 1959 em vez do de 1957, miúdo e espaçado, que saía cortado nas pontas) e confira que a
  frase inteira cabe no fim do zoom.
- **Folhas de revisão pegam o que a auditoria não vê**: borda branca/preta de foto de arquivo (HABS), faixa preta de
  recorte maior que a imagem (recorte calculado no tamanho do original, aplicado na miniatura), ativo que aparece < 0,5 s
  (Marilyn espremida entre dois ativos — tirar o do meio), palavra dourada do negrito cortada na borda (era medida em
  minúscula e sai em CAIXA ALTA — corrigido no `timeline`).
- **Símbolo atrás dele**: "=" e "×2" sobem (cap ~0,30, top 0–0,03) para as duas barras/os dois sinais ficarem ACIMA da
  cabeça; número por extenso composto no negrito ("vinte e cinco mil") agora casa o algarismo falado.
- **Aviãozinho do CTA "manda esse vídeo"**: som de PAPEL (`papel_slide`), nunca sopro de ar; longe do clique da volta.
- **Transcrição**: palavra com tempo errado (o "Ela" que o Whisper pôs antes de "artificial") fazia o corte automático
  comer o meio da palavra — reouça com o large-v3, acerte o tempo e proteja o trecho com `trecho … restaurar`.

## 20. Revisão dele nos 5 vídeos (11/11: orelhas, legenda × fala, fim das falas) — valem para TODO vídeo
- **Orelhas no recorte** ("às vezes até as minhas orelhas ficam desaparecidas"): o contorno do Vision passa POR DENTRO
  da orelha e a borda fina dela fica meio transparente. `background.ear_fix` (já dentro do `recorte-hq`) devolve à
  máscara a pele que encosta no recorte nas laterais do rosto; projeto antigo: `recorte-orelhas <pid>` (parte sempre do
  `mask_fg_sem_orelhas.mp4`, pode rodar de novo). Confira com um recorte da `preview_bg.mp4` na altura das orelhas.
  UM vídeo por vez — dois em paralelo num Mac de 8 GB levaram 4× mais tempo.
- **Legenda = o que ele FALOU, não o roteiro**: a correção pelo roteiro trocava a TERMINAÇÃO ("turistas" → "turista",
  "encalhada" → "encalhado", "começou" → "começa") — não troca mais (`montar_roteiro._so_terminacao`). Ao revisar, reouça
  as palavras de baixa confiança e as que o roteiro mudou: Whisper large-v3 em trechos curtos de ±5 palavras, UM processo;
  palavra que 2 de 3 escutas não ouviram vira "" (`texto <pid> i i ""`). Artigo trocado (o/um) é o erro mais comum.
- **Palavra mantida fora da legenda**: confira que TODA palavra não cortada (fora destaques/motions) está numa legenda —
  o "E" do começo de frase depois de um corte caía fora (o reconhecimento marca o começo cedo) e blocos de < 0,2 s eram
  descartados com as palavras dentro ("E o"). Corrigido no `timeline.caption_chunks`.
- **"Cortes sutis no fim da fala"**: o áudio exportado estava limpo (Whisper no áudio final montado a partir dos trechos:
  toda palavra de emenda inteira); quem raspava era a PRÉVIA, que pulava 10–30 ms antes do fim do trecho — agora pula no
  fim exato (±4 ms). Teste de emendas = montar o áudio dos `segments` em ordem e transcrever (Whisper inventa repetições
  em áudio longo — confirme cada achado reouvindo o trecho curto).

## 21. Observações de 14/11 no V023 (Ogilvy) e no V017 (neuroplasticidade) — valem para TODO vídeo
- **Zona segura do Reels**: nada de texto abaixo de ~78% (legenda ≤ 72%, destaque com o pé ≤ 81%) — as bolinhas de quem
  recompartilhou e o @ tampam. A tvzinha sobe e foto vertical encolhe (`timeline.viral_geom`). Ver CLAUDE.md, Tipografia.
- **Rosto dele no NOME de quem ele apresenta** ("minhas expressões aqui importam"): retrato de personagem (Ogilvy, Maguire)
  = TELA DIVIDIDA (`meio`), nunca tela cheia nem tvzinha. Foto vertical na faixa: confira que o corte central pega o rosto
  (senão recorte o arquivo — a Maguire perdia a testa).
- **Vídeo de arquivo sem o rosto dele "retém menos"**: sequência de vídeos de apoio de arquivo → tela dividida (o vídeo
  preenche a faixa, ele embaixo), não a tvzinha flutuando sobre ele desfocado.
- **Retrato não fica na tela além do nome** (Maguire 5,5 s = "tempo excessivo"): o que vem depois ganha ativo próprio e
  literal (a ressonância de verdade no "resolveu olhar o cérebro").
- **Ativo científico tem que ser LEGÍTIMO e legível para leigo**: cite a fonte exata (o hipocampo é o `Hippocampus.gif` da
  Anatomography, o mesmo dos verbetes da Wikipédia); o resto da anatomia em cinza neutro e só a estrutura citada em cor
  (o tronco cerebral bege parecia destacado); comparação = diferença óbvia (cor + tamanho + etiqueta "+ massa cinzenta"),
  amarrada ao estudo (Woollett & Maguire 2011) e dita como ilustração exagerada.
- **Símbolo atrás dele que represente a ideia** ("um calendário em vez de um igual" para "o mesmo tempo"):
  `behind` com `icon: "calendario"` (desenhado no estilo dos números). Prefira pictograma a sinal matemático abstrato.
- **IA = tela de IA de verdade**: "treinar uma IA" pede alguém digitando com o ChatGPT/Claude na tela (foto real da série
  do Matheus Bertelli no Pexels), não máquina antiga.
- **Não repita o mesmo visual**: no fecho, outro cérebro (o cérebro inteiro acendendo, `Telencephalon.gif`) e sem a
  palavra "hipocampo" de novo.
- **Riscados**: o risco do último item termina antes da saída do motion (`riscados.html`); se a fala seguinte vem colada,
  `legenda_embaixo: true` deixa a legenda dela entrar a 75% enquanto a lista sai.
- **Tela dividida predomina** (V022 14/11): vídeos e fotos de apoio em `meio`; tvzinha só para o que é pontual ou precisa
  aparecer inteiro (página de anúncio, charge, tabela, moeda/jarro, sequência < 1 s por item). Retrato de quem ele nomeia
  = tela dividida (Ogilvy, Maguire, Cialdini, Taleb). Corte de foto vertical conferido (recorte `*_meio.jpg` se perder o
  rosto/assunto); anúncio de revista na faixa = a parte de cima (pintura + título + 1ªs linhas).
- **"Garantir que seja mesmo"**: confira a FONTE PRIMÁRIA antes de dizer que confere — o Harry Oppenheimer pela ficha do
  Nationaal Archief (Anefo 901-1717 "Harry Oppenheimer (links)" + a 901-1720 com pai e filho), o prédio pela ficha HABS
  ("N.W. Ayer and Company Building, 204-212 South Seventh Street"). Diga de onde veio na resposta.
- **Gancho fora de sincronia**: `gancho_t` caindo NO MEIO da última palavra (5,33 s com o "XX" terminando em 5,64 s) =
  expectativa e obturador antes da troca de cena. Meça o fim da voz no envelope e ponha o corte logo depois.
- **Ativo literal ao que ele fala**: "a De Beers" (a empresa) = algo com o NOME dela (a ação de 1902), não a mina; "os
  Estados Unidos" = a bandeira (a de 48 estrelas, da época); "atravessou o oceano" = avião, se ele pedir (anote que em
  1938 a travessia comercial ainda era de navio); "caiu na gargalhada" = alguém rindo de boca aberta; "mais de um
  caminho" = uma bifurcação óbvia.

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
- Sons (pesquisa out/2026, "minimalismo dinâmico"): biblioteca em `app/sfx.py` (CATALOG, sons CC0/Mixkit de ar,
  foley e UI discreta). Destaque entrando = whoosh_ar_in/snap_suave; número/revelação = thump_curto/sub_drop_suave;
  sequência rápida de prints/fotos = click_classico/click_mouse; troca de assunto = whoosh de ar (na maioria dos
  cortes, nada). PROIBIDO: ding, notificação, ka-ching, buzzer, boing, vine boom. ~6–12 sons/min no máximo.
  Cada som tem `lead` (começa adiantado para o pico cair no momento) e `gain` próprio.

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

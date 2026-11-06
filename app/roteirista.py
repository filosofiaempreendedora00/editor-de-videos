"""ROTEIRISTA: a esteira que transforma uma BIG IDEA em vários roteiros prontos para o Roberto avaliar.

Etapas (pedido do usuário):
  1) padrões das referências (roteiros/padroes_referencias.md): copy, vídeo e edição dos criadores que ele admira
  2) Padrão Roberto (roteiros/padrao_roberto.md): o tom de voz dele, que evolui a cada roteiro aprovado/descartado
  3) a ideia dele (texto corrido + direcionamentos) → N roteiros com ângulos diferentes, status "rascunho"

Motores:
  claude_code  (padrão, sem custo extra): a ideia entra na FILA; o Claude Code lê `roteiros/fila/<id>.md`, escreve os
               roteiros e salva com `salvar-roteiros <id> <json>`.
  claude_api   (pago, só se o usuário ligar): gera sozinho, na hora, pela API da Anthropic.
"""
import json
import os
import re
from pathlib import Path

from . import roteiros

FILA = roteiros.DIR / "fila"
CONFIG = roteiros.DIR / "config.json"

SCHEMA = """Responda APENAS com um JSON (lista), um objeto por roteiro:
[{"title": "título curto para o kanban",
  "big_idea": "a BIG IDEA em 1 frase com tensão (o que o vídeo prova) — todos os tópicos servem a ela",
  "historia": "a HISTÓRIA REAL (case verificável, com nomes) que prova a big idea — o roteiro É essa história",
  "espelho": "onde o espectador se reconhece (entra DEPOIS da história, na moral/aplicação — nunca no lugar dela)",
  "angle": "o ângulo/abordagem deste roteiro em poucas palavras (ex.: história pessoal, caso de marca, polêmica construtiva)",
  "structure": "qual esqueleto foi usado (ex.: História pessoal → princípio)",
  "moral": "a MORAL do vídeo em UMA frase (obrigatória: todo vídeo do Roberto tem uma moral)",
  "hook": "a frase de gancho (0–5 s) — sem negrito",
  "body": "o desenvolvimento, em parágrafos curtos (um por respiração), do jeito que ele vai FALAR",
  "cta": "OBRIGATÓRIO e de UM tipo: pergunta ABERTA que dá ao espectador uma resposta fácil de comentar (padrão) · ou compartilhar (encaminha praquele amigo que…) · salvar só em conteúdo de consulta (lista, passo a passo)",
  "caption": "legenda do post: tese em 1–2 frases + pergunta",
  "notes": "sugestões de B-roll, prova na tela e artefatos a mostrar; o que o Roberto precisa confirmar/levantar (dados, números)",
  "ativos": [{"momento": "trecho da fala", "o_que": "ativo ESPECÍFICO e original (ex.: o TikTok de 2023 do fundador batendo o chiclete na bancada)",
              "onde": "onde achar (perfil oficial, matéria, página do produto…) com link se souber", "status": "pendente"}]}]"""


def config():
    return roteiros._read(CONFIG, {"engine": "claude_code"})


def set_config(**kw):
    c = {**config(), **kw}
    roteiros._write(CONFIG, c)
    return c


def api_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _examples(limit=3):
    """Roteiros do Roberto já aprovados (os mais recentes primeiro): são a melhor referência de tom."""
    # os DESTAQUES entram inteiros em destaques_block (peso maior); aqui ficam os demais aprovados
    ok = [r for r in roteiros.load() if r["status"] in ("aprovado", "preeditado", "gravado", "editado", "publicado")
          and not r.get("archived") and (r.get("body") or r.get("hook"))]
    ok.sort(key=lambda r: r["code"], reverse=True)
    out = []
    for r in ok[:limit]:
        out.append(f"### {r['code']} — {r['title']}\nHOOK: {r.get('hook', '')}\n\nBODY:\n{r.get('body', '')}\n\nCTA: {r.get('cta', '')}"
                   + (f"\n\n(Comentário do Roberto ao aprovar: {r['feedback']})" if r.get("feedback") else ""))
    return "\n\n".join(out)


def destaques_block():
    """Os vídeos DESTAQUE (publicados e muito acima da média — coluna ✦ Destaques do kanban): o roteiro inteiro + a
    receita de edição (hook visual incluso). PESO MAIOR na modelagem de copy e de edição que os só publicados (pedido
    dele, 25/10: "não é fazer igual ao que viralizou, é dar maior peso na inteligência de modelagem")."""
    from . import crivo
    out = []
    for r in sorted(crivo.destaques(), key=lambda r: r["code"]):
        out.append(f"{crivo.destaque_resumo(r)}\n\n**Roteiro (como foi ao ar):**\nHOOK: {r.get('hook', '')}\n\n"
                   f"BODY:\n{r.get('body', '')}\n\nCTA: {r.get('cta', '')}")
    return "\n\n---\n\n".join(out)


def brief(idea):
    """O briefing completo que o roteirista (Claude Code ou API) recebe."""
    pad = roteiros.doc_read("padroes")["text"]
    rob = roteiros.doc_read("roberto")["text"]
    broncas = "\n".join(roteiros.comments_corpus("copy")) or "(ainda nenhum)"
    extra = roteiros.brain_markdown()
    n = idea.get("n", 3)
    fmt_block = ""
    if idea.get("formato"):
        fdoc = roteiros.doc_read("fmt:" + idea["formato"])["text"]
        fmt_block = (f"\n## FORMATO OBRIGATÓRIO: siga a espinha, a edição e a CURADORIA DE ATIVOS abaixo "
                     f"(preencha a lista \"ativos\" com ativos originais e específicos)\n{fdoc}\n")
    return f"""# Pedido de roteiros {idea['id']}

Você é o roteirista do Roberto (Reels/TikTok, vídeos falados de 60–90 s). Escreva {n} roteiros DIFERENTES entre si
para a ideia abaixo: cada um com um ângulo e um esqueleto distintos (use os esqueletos dos padrões), todos no TOM de voz
do Padrão Roberto. Escreva para ser FALADO: frases curtas, concretas, com números/nomes/fatos. Não invente dados
como se fossem verdade: quando um número ou fato precisar ser confirmado, marque com [confirmar] e liste em "notes".
ANTES DE ESCREVER, siga a skill `escrever-roteiro` (.claude/skills/escrever-roteiro/SKILL.md) e leia o RESUMO do
Padrão Roberto: big idea em 1 frase → MAPA dos insumos (cada um com UM papel; no máximo 3 protagonistas; o que precisa
de frase-ponte explicativa SAI) → UMA história/artefato real em que as ideias já estão ligadas → esqueleto em bullets →
texto em ESCORREGADOR (frases ligadas por conectivos, nada truncado) → passes anti-IA → CHECAGEM FINAL. A moral pode
ser de marketing/vendas ou de vida aplicada ao dia a dia; o fim volta ao gancho pela mesma imagem; CTA = UMA pergunta
curta que encaixa na última linha.
NEGRITO: marque no "body" os destaques com **assim**, no jeito dele (seção NEGRITO do Padrão Roberto: par do contraste,
números do resultado, pergunta-chave, agente da virada, frase-tese, palavra da escolha no fecho; ~1 por parágrafo).
IMPORTANTE: inspire-se no TOM dos roteiros dele, NUNCA nas frases — é proibido repetir frases/expressões dos roteiros
dele (o editor recusa trechos iguais de 6+ palavras). Antes de entregar, aplique a "LAPIDAÇÃO DA COPY" do Padrão
Roberto (tamanho, um fio só, fim curto e amarrado ao gancho).

## A IDEIA DO ROBERTO
{idea['text']}
{fmt_block}
## Comentários do Roberto nos roteiros (trecho → o que ele disse) — as broncas mais específicas; NÃO repita esses erros
{broncas}

## ✦ VÍDEOS DESTAQUE — o que MAIS funcionou com o público dele (PESO MÁXIMO, acima de tudo abaixo)
Estes vídeos performaram muito acima da média (comentários, seguidores, views). Antes de escrever, descubra POR QUE
funcionaram — a força do gancho (frase + o que aparece na tela), o tipo de história, o contraste, o ritmo, o fecho — e
aplique esses PRINCÍPIOS em cada roteiro novo com mais peso que os outros aprovados. NUNCA copie: nem frases, nem o mesmo
personagem, nem a mesma estrutura de cena por cena. Em cada roteiro, proponha em "ativos" um HOOK VISUAL tão forte
quanto o do destaque (uma imagem/vídeo real, concreto, que mostre o gancho acontecendo nos primeiros 3 s).
{destaques_block() or '(nenhum vídeo destaque ainda)'}

## 1) Padrões das referências
{pad}

## 2) Padrão Roberto — tom de voz (PRIORIDADE sobre os padrões das referências)
{rob}

## Roteiros que ele aprovou (imite o TOM e o ritmo — jamais as frases)
{_examples() or '(ainda nenhum além dos acima)'}

## Outras anotações da inteligência
{extra}

## Formato da resposta
{SCHEMA}
"""


def queue(idea):
    FILA.mkdir(parents=True, exist_ok=True)
    path = FILA / f"{idea['id']}.md"
    path.write_text(brief(idea), encoding="utf-8")
    return path


def parse(text):
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)
    if not m:
        raise ValueError("A resposta não trouxe a lista de roteiros em JSON.")
    data = json.loads(m.group(0))
    return [d for d in data if isinstance(d, dict) and (d.get("hook") or d.get("body"))]


def _norm_words(text):
    return re.findall(r"[a-zà-ÿ0-9]+", (text or "").lower())


# expressões-assinatura do V001: curtas demais para a checagem de 6 palavras, mas marcantes — não podem voltar
SIGNATURES = ["acontece que", "outra coisa completamente diferente", "sabendo disso", "sendo assim nós tratamos",
              "dosezinha", "repare bem", "a boa e velha", "uma boa pitada", "me conta e você", "caprichar na copy",
              "diferentões", "brincadeiras à parte"]


# vícios que ele chamou de "cara de IA" / "paia" — recusados ao salvar
AI_TELLS = ["a ciência confirma", "a ciência mostra", "estudos mostram", "pesquisas mostram", "estudos comprovam",
            "consciente muda", "inconsciente muda", "o outro muda", "um muda", "deu sorte", "olhando a planilha",
            # v11 (01/11) — as expressões que ele chamou de "cara de IA", "ninguém fala assim" ou "forçado" nos comentários
            "como ninguém", "uma parte de você", "eu gosto de pensar", "de um lugar de conforto", "cair em desgraça",
            "a ordem chegou", "guarda esse anúncio", "tem um número que prova", "é aí que entra", "isso é seu",
            "no banho", "reunião sem pauta", "pode me ligar quando puder",
            # 01/11: CTA com jogo hipotético montado ("ninguém falaria isso, muito forçado")
            "tivesse que completar", "completar a frase", "complete a frase"]

# conectivos com que ELE costura as frases (45–58% das frases das versões finais dele começam assim)
CONECTIVOS = ("e ", "mas ", "porque ", "então ", "até que ", "só que ", "a partir daí", "inclusive", "não à toa",
              "afinal", "pronto", "com isso", "assim", "aí ", "ou seja", "agora ", "por isso", "quando ", "repara",
              "é justamente", "foi justamente", "daí", "depois", "anos depois", "hoje")


def lint(d):
    """Avisos de fluidez (o "escorregador" dele) — não recusam, orientam a lapidação antes de entregar. Calibrado nos
    aprovados (V002, V005, V011, V014, V018, V019): ele aceita até ~2 frases curtas de efeito ("O hotel topou.")."""
    import re as _re
    raw = d.get("body", "")
    body = _re.sub(r"\*\*", "", raw)
    # "…" seguido de minúscula continua a mesma frase (pausa falada), não é frase nova
    sents = [x.strip() for x in _re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ\"“])|\n+", body) if x.strip()]
    out = []
    soltas = [x for x in sents if len(x.split()) <= 4 and not x.endswith("?")]
    if len(soltas) > 2:
        out.append(f"{len(soltas)} frases soltas de até 4 palavras (ele chama de truncado/jogado; aceita ~2 de efeito): {soltas[:5]}")
    if sents:
        con = sum(1 for x in sents if x.lower().startswith(CONECTIVOS)) / len(sents)
        if con < 0.38:
            out.append(f"só {round(con * 100)}% das frases começam com conectivo (nas versões dele: 45–58%) — encadeie")
    paras = [x for x in raw.split("\n") if x.strip()]
    longos = [x[:40] for x in paras if len(_re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", x.strip())) > 4]
    if longos:
        out.append(f"parágrafo com mais de 4 frases (blocão): {longos[:2]}")
    cta = _re.sub(r"^\s*E você\?\s*", "", d.get("cta", ""))
    if cta.count("?") > 1 or len(cta.split()) > 24:
        out.append("CTA com mais de uma pergunta ou longo demais (ele quer UMA pergunta, ~20 palavras)")
    hook = d.get("hook", "")
    if _re.match(r"\s*(uma|um) (pesquisa|estudo|consultoria)", hook.lower()):
        out.append("gancho abrindo com estudo/fonte (derrubou o V014 v1) — abra com curiosidade/imagem/paradoxo")
    # ABERTURA (regra dele, 05/11: o início inteiro tem que prender). Sem meta de tamanho de frase: encurtar até bater o
    # número virou telegrama (V023 v2). O que conta é o escorregador: skill escrever-roteiro §3.1, teste do teleprompter
    if len(hook.split()) > 16:
        out.append(f"gancho com {len(hook.split())} palavras (os que mais funcionaram têm 11–15; V023 v1: 'extenso demais')")
    inicio, soma = [], 0
    for x in sents:
        inicio.append(x)
        soma += len(x.split())
        if soma >= 70:
            break
    if _re.search(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", " ".join([hook] + inicio)):
        out.append("ano no gancho ou na abertura (tese dele: gasta os segundos mais caros do vídeo) — comece por gente em cena")
    n = len(_re.findall(r"\w+", " ".join([hook, body])))
    if not 250 <= n <= 470:
        out.append(f"{n} palavras (aprovados recentes: 300–460)")
    if raw.count("**") // 2 < 5:
        out.append("pouco negrito (~1 destaque por parágrafo, no jeito dele)")
    return out


def ai_tells(d):
    joined = " " + " ".join(_norm_words(" ".join(d.get(k, "") for k in ("hook", "body", "cta")))) + " "
    return [t for t in AI_TELLS if f" {' '.join(_norm_words(t))} " in joined]


def copied_passages(d, n=7):
    """Trechos de n+ palavras do roteiro novo que já existem, iguais, num roteiro do próprio Roberto (escrito por ele
    ou aprovado). Regra dele: inspiração é de TOM, nunca de frase."""
    # textos DELE: escritos por ele ou lapidados por ele (gravado/editado/publicado)
    refs = [r for r in roteiros.load() if not r.get("archived") and r is not d and r.get("code") != d.get("code")
            and (r["status"] in ("gravado", "editado", "publicado", "destaque") or (r["status"] in ("aprovado", "preeditado") and not r.get("idea")))]
    grams = set()
    for r in refs:
        w = _norm_words(" ".join(r.get(k, "") for k in ("hook", "body", "cta")))
        grams.update(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    w = _norm_words(" ".join(d.get(k, "") for k in ("hook", "body", "cta")))
    joined = " ".join(w)
    # construções-assinatura são a voz dele: UMA por roteiro, com conteúdo novo (ele mesmo usa: "uma coisa é o
    # PRODUTO… e outra coisa, completamente diferente, é a OFERTA"); duas ou mais = colagem do V001
    sigs = [sig for sig in SIGNATURES if f" {' '.join(_norm_words(sig))} " in f" {joined} "]
    hits = sigs if len(sigs) >= 2 else []
    i = 0
    while i <= len(w) - n:
        if tuple(w[i:i + n]) in grams:
            j = i + n
            while j < len(w) and tuple(w[j - n + 1:j + 1]) in grams:
                j += 1
            hits.append(" ".join(w[i:j]))
            i = j
        else:
            i += 1
    return hits


def save(idea_id, items):
    """Grava os roteiros gerados como RASCUNHOS (cada um com seu código V00X) ligados à ideia."""
    idea = next(x for x in roteiros.ideas() if x["id"] == idea_id)
    bad = {d.get("title", "?"): copied_passages(d) + [f"(cara de IA) {t}" for t in ai_tells(d)] for d in items}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        raise ValueError("Roteiro recusado — frase copiada do Roberto ou vício de IA (ver Padrão Roberto): "
                         + "; ".join(f"{k}: «{'», «'.join(v)}»" for k, v in bad.items()))
    codes = []
    for d in items:
        r = roteiros.add({"title": d.get("title") or idea["text"][:50], "status": "rascunho", "idea": idea_id,
                          "angle": d.get("angle", ""), "structure": d.get("structure", ""), "moral": d.get("moral", ""),
                          "hook": d.get("hook", ""), "body": d.get("body", ""), "cta": d.get("cta", ""),
                          "caption": d.get("caption", ""),
                          "notes": "".join(f"{lab}: {d[k]}\n" for k, lab in (("big_idea", "BIG IDEA"), ("historia", "HISTÓRIA"), ("espelho", "ESPELHO")) if d.get(k))
                                   + d.get("notes", ""),
                          "formato": idea.get("formato", ""), "ativos": d.get("ativos") or [],
                          "origem": idea.get("origem", "roberto")})
        codes.append(r["code"])
    roteiros.idea_edit(idea_id, status="pronto", codes=idea.get("codes", []) + codes, error="")
    (FILA / f"{idea_id}.md").unlink(missing_ok=True)
    return codes


def generate_api(idea):
    import anthropic
    from .brain import CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"].strip(), base_url="https://api.anthropic.com")
    msg = client.messages.create(model=CLAUDE_MODEL, max_tokens=8000,
                                 messages=[{"role": "user", "content": brief(idea)}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return save(idea["id"], parse(text))


def submit(text, n=3, formato=""):
    """Nova big idea: entra na fila (Claude Code) ou já gera pela API, se o usuário escolheu."""
    idea = roteiros.add_idea(text, n, formato)
    queue(idea)
    if config().get("engine") == "claude_api" and api_available():
        import threading
        roteiros.idea_edit(idea["id"], status="gerando")

        def run():
            try:
                generate_api(idea)
            except Exception as e:  # noqa: BLE001
                roteiros.idea_edit(idea["id"], status="na_fila", error=str(e)[:300])
        threading.Thread(target=run, daemon=True).start()
    return next(x for x in roteiros.ideas() if x["id"] == idea["id"])

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
  "angle": "o ângulo/abordagem deste roteiro em poucas palavras (ex.: história pessoal, caso de marca, polêmica construtiva)",
  "structure": "qual esqueleto foi usado (ex.: História pessoal → princípio)",
  "hook": "a frase de gancho (0–5 s)",
  "body": "o desenvolvimento, em parágrafos curtos (um por respiração), do jeito que ele vai FALAR",
  "cta": "a chamada final (pergunta ao espectador / comentar palavra / seguir)",
  "caption": "legenda do post: tese em 1–2 frases + pergunta",
  "notes": "sugestões de B-roll, prova na tela e artefatos a mostrar; o que o Roberto precisa confirmar/levantar (dados, números)"}]"""


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
    ok = [r for r in roteiros.load() if r["status"] in ("aprovado", "gravado", "editado", "publicado")
          and not r.get("archived") and (r.get("body") or r.get("hook"))]
    ok.sort(key=lambda r: r["code"], reverse=True)
    out = []
    for r in ok[:limit]:
        out.append(f"### {r['code']} — {r['title']}\nHOOK: {r.get('hook', '')}\n\nBODY:\n{r.get('body', '')}\n\nCTA: {r.get('cta', '')}"
                   + (f"\n\n(Comentário do Roberto ao aprovar: {r['feedback']})" if r.get("feedback") else ""))
    return "\n\n".join(out)


def brief(idea):
    """O briefing completo que o roteirista (Claude Code ou API) recebe."""
    pad = roteiros.doc_read("padroes")["text"]
    rob = roteiros.doc_read("roberto")["text"]
    extra = roteiros.brain_markdown()
    n = idea.get("n", 3)
    return f"""# Pedido de roteiros {idea['id']}

Você é o roteirista do Roberto (Reels/TikTok, vídeos falados de 60–90 s). Escreva {n} roteiros DIFERENTES entre si
para a ideia abaixo: cada um com um ângulo e um esqueleto distintos (use os esqueletos dos padrões), todos no tom de voz
do Padrão Roberto. Escreva para ser FALADO: frases curtas, concretas, com números/nomes/fatos. Não invente dados
como se fossem verdade: quando um número ou fato precisar ser confirmado, marque com [confirmar] e liste em "notes".

## A IDEIA DO ROBERTO
{idea['text']}

## 1) Padrões das referências
{pad}

## 2) Padrão Roberto — tom de voz (PRIORIDADE sobre os padrões das referências)
{rob}

## Roteiros que ele aprovou (imite o tom)
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


def save(idea_id, items):
    """Grava os roteiros gerados como RASCUNHOS (cada um com seu código V00X) ligados à ideia."""
    idea = next(x for x in roteiros.ideas() if x["id"] == idea_id)
    codes = []
    for d in items:
        r = roteiros.add({"title": d.get("title") or idea["text"][:50], "status": "rascunho", "idea": idea_id,
                          "angle": d.get("angle", ""), "structure": d.get("structure", ""),
                          "hook": d.get("hook", ""), "body": d.get("body", ""), "cta": d.get("cta", ""),
                          "caption": d.get("caption", ""), "notes": d.get("notes", "")})
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


def submit(text, n=3):
    """Nova big idea: entra na fila (Claude Code) ou já gera pela API, se o usuário escolheu."""
    idea = roteiros.add_idea(text, n)
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

"""Edição inteligente com Claude: limpa erros de gravação e sugere inserções."""
import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

_client = None


def api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def available():
    return bool(api_key())


def client():
    global _client
    if not available():
        raise RuntimeError("IA desligada: coloque ANTHROPIC_API_KEY no arquivo .env e reinicie.")
    if _client is None:
        _client = anthropic.Anthropic(api_key=api_key(), base_url="https://api.anthropic.com")
    return _client


def transcript_for_ai(words, deleted):
    """Formato compacto: `[índice]palavra`, com marcas de pausa longa."""
    deleted = set(deleted)
    out = []
    prev = None
    for w in words:
        if w["i"] in deleted:
            continue
        if prev is not None and w["start"] - prev["end"] > 0.7:
            out.append(f"<pausa {w['start'] - prev['end']:.1f}s>")
        out.append(f"[{w['i']}]{w['w']}")
        prev = w
    return " ".join(out)


def _ask(system, user, schema, effort="medium"):
    resp = client().beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": effort,
                       "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("O modelo recusou a solicitação.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Resposta da IA ficou longa demais; tente num vídeo menor.")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


CLEAN_SYSTEM = """Você é um editor de vídeo experiente que edita vídeos falados (YouTube, Reels, aulas) em português.
Você recebe a transcrição de uma gravação crua. Cada palavra vem com seu índice: [índice]palavra.
Sua tarefa é decidir quais trechos CORTAR para que o vídeo fique fluido, como se a pessoa tivesse falado tudo de primeira.

Corte:
- Repetições e regravações: quando a pessoa começa uma frase, erra e recomeça, mantenha somente a ÚLTIMA versão completa e corte as tentativas anteriores.
- Falsos começos e frases abandonadas no meio.
- Gaguejos e palavras repetidas sem intenção ("eu eu eu acho").
- Hesitações e muletas que não carregam sentido ("ahn", "é...", "hum", "tipo" quando é muleta).
- Falas de bastidor: "corta", "vou de novo", "deixa eu repetir", "tá gravando?", contagens ("3, 2, 1"), comentários para a equipe.

NÃO corte conteúdo real, piadas, exemplos ou ênfases intencionais. Na dúvida, mantenha.
Os intervalos são inclusivos (start e end são índices de palavras)."""

CLEAN_SCHEMA = {
    "type": "object",
    "properties": {
        "cuts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cuts"],
    "additionalProperties": False,
}


def clean(words, deleted):
    data = _ask(CLEAN_SYSTEM, "Transcrição:\n\n" + transcript_for_ai(words, deleted),
                CLEAN_SCHEMA, effort="high")
    n = len(words)
    cuts = []
    for c in data.get("cuts", []):
        a, b = int(c["start"]), int(c["end"])
        if 0 <= a <= b < n:
            cuts.append({"start": a, "end": b, "reason": c.get("reason", "")})
    return cuts


SUGGEST_SYSTEM = """Você é um editor de vídeos para redes sociais que deixa vídeos falados mais dinâmicos e retentivos.
Você recebe a transcrição (palavras com índice [i]) de um vídeo já cortado.
Sugira inserções visuais ancoradas em trechos de fala (índices start..end inclusivos):

- "text": um título curto na tela (no máximo 6 palavras, forte e direto) para destacar uma ideia-chave, número, lista ou frase de efeito.
- "broll": uma imagem/vídeo de apoio que ilustre o que está sendo dito. Em "text" descreva a cena de forma visual e específica, e em "query" dê um termo de busca curto em inglês para bancos de imagem (ex.: "person typing laptop").

Ritmo: aproximadamente uma inserção a cada 10–20 segundos de vídeo, sem sobrepor uma na outra.
Cada inserção deve cobrir de 1 a 4 segundos de fala (geralmente 3 a 12 palavras). Priorize momentos de maior impacto."""

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["text", "broll"]},
                    "text": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["start", "end", "kind", "text", "query"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def suggest(words, deleted, duration):
    user = (f"Duração final aproximada: {duration:.0f}s.\n\nTranscrição:\n\n"
            + transcript_for_ai(words, deleted))
    data = _ask(SUGGEST_SYSTEM, user, SUGGEST_SCHEMA)
    n = len(words)
    items = []
    for it in data.get("items", []):
        a, b = int(it["start"]), int(it["end"])
        if 0 <= a <= b < n:
            items.append({"w0": a, "w1": b, "kind": it["kind"], "text": it["text"].strip(),
                          "query": it.get("query", "")})
    return items

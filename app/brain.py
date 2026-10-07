"""O "cérebro" do editor: lê o roteiro e propõe o plano de edição.

Motores (todos devolvem o MESMO formato):
  regras      grátis, local, sempre disponível (app/rules.py)
  ollama      grátis, IA local (precisa do app Ollama instalado)
  claude_code grátis com sua assinatura: o Claude Code lê `para_claude_code.md`
              e escreve `plano.json` na pasta do projeto (veja CLAUDE.md)
  claude_api  pago por uso (ANTHROPIC_API_KEY no .env)
"""
import json
import os
from pathlib import Path

import httpx

from . import rules

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

from .sfx import CATALOG as _SFX_CATALOG
SFX_NAMES = [c["name"] for c in _SFX_CATALOG] + ["whoosh", "swish", "pop", "ding", "impacto", "click", "digitando",
                                                "riser", "camera"]
MOTION_TEMPLATES = {
    "lettering": "frase curta animada palavra por palavra, grande, no centro (params.text)",
    "icone": "ícone/emoji animado com um rótulo (params.icon = emoji, params.label = texto curto)",
    "lista": "motion explicativo: lista de até 4 itens surgindo em sequência (params.title, params.items)",
    "contador": "número contando até o valor, com legenda (params.value numérico, params.prefix, params.suffix, params.label)",
    "comparacao": "duas colunas ANTES x DEPOIS ou A x B (params.left, params.right, params.left_label, params.right_label)",
    "card3d": "a imagem do B-roll girando em perspectiva 3D (usar em kind=broll com layout=card3d)",
    "carrossel3d": "carrossel 3D de várias imagens do projeto (params.files = lista de arquivos já existentes)",
    "emoji3d": "EMOJI 3D profissional (espessura, giro em perspectiva, brilho, partículas douradas) — params.icon, x, y (0..1), size (vmin); use min_dur 1.8",
}
SOURCES = ["wikipedia", "commons", "arquivo", "nasa", "noticias", "site", "proprio"]


def engines():
    return {
        "regras": True,
        "ollama": ollama_available(),
        "claude_code": True,
        "claude_api": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
    }


# ------------------------------------------------------------------ esquema

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["text", "sfx", "zoom", "transition", "broll", "motion", "behind", "perspective", "emphasis"]},
        "start": {"type": "integer"},
        "end": {"type": "integer"},
        "text": {"type": "string"},
        "style": {"type": "string", "enum": ["title", "keyword", "lower", "none"]},
        "sfx": {"type": "string", "enum": SFX_NAMES + ["none"]},
        "transition": {"type": "string", "enum": ["leak", "branco", "escuro", "desfoque", "flash", "none"]},
        "variant": {"type": "string", "enum": ["bigend", "stack", "atras", "none"]},
        "query": {"type": "string"},
        "source": {"type": "string", "enum": SOURCES},
        "layout": {"type": "string", "enum": ["full", "pip", "card", "card3d", "none"]},
        "template": {"type": "string", "enum": list(MOTION_TEMPLATES) + ["none"]},
        "params_json": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["kind", "start", "end", "text", "style", "sfx", "transition", "variant", "query", "source",
                 "layout", "template", "params_json", "reason"],
    "additionalProperties": False,
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "hook": {"type": "string"},
                "sections": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "start": {"type": "integer"},
                                   "end": {"type": "integer"}},
                    "required": ["title", "start", "end"], "additionalProperties": False}},
                "key_points": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "hook", "sections", "key_points"],
            "additionalProperties": False,
        },
        "fixes": {"type": "array", "items": {
            "type": "object",
            "properties": {"start": {"type": "integer"}, "end": {"type": "integer"}, "text": {"type": "string"},
                           "reason": {"type": "string"}},
            "required": ["start", "end", "text", "reason"], "additionalProperties": False}},
        "cuts": {"type": "array", "items": {
            "type": "object",
            "properties": {"start": {"type": "integer"}, "end": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["start", "end", "reason"], "additionalProperties": False}},
        "items": {"type": "array", "items": ITEM_SCHEMA},
    },
    "required": ["analysis", "fixes", "cuts", "items"],
    "additionalProperties": False,
}


SYSTEM = """Você é um editor de vídeo sênior que edita vídeos falados para YouTube, Reels e anúncios, em português.
Seu trabalho é transformar uma gravação crua num vídeo dinâmico, autoral e NADA genérico.

Você recebe a transcrição: cada palavra vem com índice [i]. Marcas <pausa Xs> indicam silêncios.
Responda com:

1) analysis: resumo do roteiro, o gancho (primeira frase forte), as seções (com índices de início e fim) e os pontos-chave.

2) (cortes com bom senso) além de regravações, corte o que não acrescenta nada ao vídeo final: muletas
   ("o que eu posso dizer", "deixa eu ver", "sei lá", "tipo assim"), frases abandonadas no meio, comentários
   para quem está gravando, pedidos de desculpa por errar. Mantenha só o que um bom editor manteria.

2b) fixes: correções da TRANSCRIÇÃO automática (o reconhecimento de voz erra palavras parecidas no som).
   Use o contexto para corrigir só erros claros: ex. "a ferramenta que eu creio de IA" -> "criei";
   nomes de marcas/pessoas, siglas e termos técnicos com a grafia correta, pontuação que muda o sentido.
   start..end = palavras substituídas, text = texto correto (pode ter mais ou menos palavras). Não reescreva o estilo da fala.

3) cuts: intervalos de palavras a REMOVER — regravações (mantenha só a ÚLTIMA versão boa), falsos começos,
   gaguejos, muletas sem sentido, falas de bastidor ("corta", "vou de novo"). Nunca corte conteúdo real.

4) items: o plano de inserções, ancorado nos índices das palavras (start..end inclusivos):
   - text: style "title" (título curto no topo, até 6 palavras), "keyword" (palavra/número grande no centro,
     1-3 palavras, para dados e frases de efeito) ou "lower" (nome/identificação no canto inferior).
   - sfx: efeito sonoro pontual, no estilo 2026 ("minimalismo dinâmico"): poucos, discretos, de ar/foley real.
     Regras: destaque entrando = whoosh_ar_in ou snap_suave; troca de assunto = whoosh de ar (na maioria dos
     cortes, NADA); número/revelação = thump_curto/sub_drop_suave (riser antes, opcional); sequência rápida de
     prints/fotos = click_classico/click_mouse alternados; card/print entrando = papel_slide/swipe_rapido.
     Proibido: ding, notificação, ka-ching, buzzer, boing, vine boom (datados). ~6–12 sons por minuto no máximo.
     Biblioteca: {sfx}
   - zoom: punch-in de ênfase sobre a fala (2–4 s), em frases fortes, perguntas e viradas.
   - transition: "flash" na virada de seção.
   - broll: material visual de apoio. Seja ESPECÍFICO e fuja do clichê de banco de imagem:
       prefira fotos REAIS das pessoas/empresas/lugares citados (source "wikipedia"), documentos, mapas e fotos
       históricas (source "commons"), filmes antigos de arquivo para metáforas visuais (source "arquivo", query em
       inglês, ex.: "assembly line 1950s"), espaço/ciência (source "nasa"), manchetes que provam o que está sendo dito
       (source "noticias", query = assunto da notícia), ou print de um site específico (source "site", query = URL).
       Use source "proprio" quando o ideal for um print/vídeo que só a pessoa tem (tela do produto, depoimento, resultado).
       layout: "full" (tela cheia), "pip" (janela), "card" (imagem/print centralizado sobre fundo desfocado), "card3d" (em perspectiva 3D).
       Em text descreva a cena desejada.
   - motion: animação gráfica. template e params_json (um JSON em string) conforme a lista abaixo.
   - emphasis: FRASE DE DESTAQUE — a legenda daquele trecho vira tipografia grande em várias linhas,
     com a palavra-chave enorme em dourado. Use nas frases mais fortes do roteiro (tese, número marcante,
     revelação, frase de efeito), 3 a 8 palavras, cobrindo ~10–15% do vídeo no total (nunca seguidas).
     Em text, coloque a palavra-chave que deve ficar em destaque.
     O GANCHO (primeiros 3–7 s) deve quase sempre virar 1 ou 2 blocos de emphasis: é onde o vídeo prende a atenção.
     variant "atras" = FRASE ESPECIAL (ref. @tay.ldantas): linhas curtas em zigue-zague entrando animadas e a
     palavra-chave GIGANTE atrás da cabeça. É a mais bonita — use com moderação: 1 por vídeo (2 se passar de 45 s,
     bem separadas), na ideia central, com palavra-chave de 5+ letras. Nas outras use "bigend"/"stack"/"none".
   - zoom: os itens de LISTA ("sem X, sem Y, sem Z"; "público, promessa, posicionamento") ganham zoom progressivo
     automaticamente (cada item fecha mais) — não precisa marcar. Use zoom só em ênfases fora de listas.
   - behind: texto GIGANTE atrás da pessoa (recorte de fundo), 1-2 palavras, para o momento mais forte do vídeo
     (use no máximo 1–2 vezes).
   - perspective: a pessoa num plano 3D inclinado por 1,5–3 s, para uma virada ou revelação (use com moderação).

Ritmo: um estímulo visual a cada 3–6 s em vídeo curto (até 90 s) e a cada 6–12 s em vídeo longo.
Não sobreponha dois elementos visuais grandes ao mesmo tempo. Preencha com "none"/"" os campos que não se aplicam.

Templates de motion disponíveis:
{templates}
"""


def build_user_prompt(words, deleted, duration, formato=None):
    from .ai_text import transcript_for_ai
    fmt = ""
    if formato:
        fmt = ("\n\nFORMATO DE REFERÊNCIA (siga este estilo e ritmo):\n" + formato.get("brief", "")
               + "\n" + json.dumps(formato.get("metrics", {}), ensure_ascii=False))
    return (f"Duração do vídeo bruto: {duration:.0f}s.{fmt}\n\nTranscrição:\n\n"
            + transcript_for_ai(words, deleted))


def system_prompt():
    sfx = "; ".join(f"{c['name']} ({c['desc']})" for c in _SFX_CATALOG)
    return SYSTEM.format(templates="\n".join(f"- {k}: {v}" for k, v in MOTION_TEMPLATES.items()), sfx=sfx)


# ------------------------------------------------------------------ motores

def plan(engine, words, deleted, duration, formato=None, project_dir=None):
    if engine == "regras":
        cuts = rules.clean(words, deleted)
        cleaned = set(deleted)
        for c in cuts:
            cleaned.update(range(c["start"], c["end"] + 1))
        out = rules.analyze(words, sorted(cleaned), duration, formato=formato)
        out["cuts"] = cuts
        return out
    if engine == "ollama":
        return _validate(_ollama(words, deleted, duration, formato), len(words))
    if engine == "claude_api":
        return _validate(_claude(words, deleted, duration, formato), len(words))
    if engine == "claude_code":
        return read_claude_code_plan(project_dir, len(words))
    raise ValueError(f"motor desconhecido: {engine}")


def _validate(data, n):
    """Normaliza o JSON da IA: índices dentro do vídeo, params em dict, campos 'none' removidos."""
    def ok(a, b):
        return isinstance(a, int) and isinstance(b, int) and 0 <= a <= b < n

    fixes = [f for f in data.get("fixes", []) if ok(f.get("start"), f.get("end")) and isinstance(f.get("text"), str)]
    cuts = [c for c in data.get("cuts", []) if ok(c.get("start"), c.get("end"))]
    items = []
    for it in data.get("items", []):
        if not ok(it.get("start"), it.get("end")):
            continue
        it = {k: v for k, v in it.items() if v not in ("none", "", None)}
        if "params_json" in it:
            try:
                it["params"] = json.loads(it.pop("params_json"))
            except (TypeError, ValueError):
                it.pop("params_json", None)
        items.append(it)
    analysis = data.get("analysis") or {}
    analysis["sections"] = [s for s in analysis.get("sections", []) if ok(s.get("start"), s.get("end"))]
    return {"analysis": analysis, "fixes": fixes, "cuts": cuts, "items": items}


def _claude(words, deleted, duration, formato):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"].strip(),
                                 base_url="https://api.anthropic.com")
    with client.beta.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        system=system_prompt(),
        messages=[{"role": "user", "content": build_user_prompt(words, deleted, duration, formato)}],
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError("O modelo recusou a solicitação.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("A resposta da IA ficou longa demais.")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def ollama_available():
    try:
        return httpx.get(f"{OLLAMA_URL}/api/tags", timeout=1.5).status_code == 200
    except Exception:
        return False


def _ollama(words, deleted, duration, formato):
    r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=900, json={
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": PLAN_SCHEMA,
        "options": {"temperature": 0.3, "num_ctx": 32768},
        "messages": [{"role": "system", "content": system_prompt()},
                     {"role": "user", "content": build_user_prompt(words, deleted, duration, formato)}],
    })
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


# ------------------------------------------------------------------ Claude Code (arquivo)

def write_claude_code_brief(project, project_dir, formato=None):
    """Prepara o pedido para o Claude Code: roteiro + instruções + esquema de resposta."""
    pdir = Path(project_dir)
    brief = [
        f"# Pedido de plano de edição — projeto {project['id']} ({project['name']})",
        "",
        "Você é o editor. Leia as instruções e a transcrição abaixo e escreva o plano em",
        f"`projects/{project['id']}/plano.json`, seguindo exatamente o esquema JSON no fim deste arquivo.",
        "Depois avise o usuário para clicar em **Carregar plano do Claude Code** no editor",
        f"(ou rode `.venv/bin/python -m app.cli aplicar-plano {project['id']}`).",
        "",
        "## Instruções",
        system_prompt(),
        "## Transcrição e contexto",
        build_user_prompt(project["words"], project["deleted"], project["source"]["duration"], formato),
        "",
        "## Esquema da resposta (plano.json)",
        "Em `items`, o campo `params_json` pode ser substituído por `params` (objeto).",
        "```json",
        json.dumps(PLAN_SCHEMA, ensure_ascii=False, indent=1),
        "```",
    ]
    f = pdir / "para_claude_code.md"
    f.write_text("\n".join(brief), encoding="utf-8")
    return f


def read_claude_code_plan(project_dir, n):
    f = Path(project_dir) / "plano.json"
    if not f.exists():
        raise RuntimeError("Ainda não existe plano.json. Peça ao Claude Code: "
                           "\"faça o plano de edição do projeto\" (ele lê para_claude_code.md).")
    data = json.loads(f.read_text(encoding="utf-8"))
    for it in data.get("items", []):
        if isinstance(it.get("params"), dict):
            it["params_json"] = json.dumps(it.pop("params"), ensure_ascii=False)
    return _validate(data, n)

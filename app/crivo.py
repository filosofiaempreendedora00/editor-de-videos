"""CRIVO DE EDIÇÃO ITERATIVO — a inteligência que vem das observações que ele faz DIRETO nos vídeos.

Toda observação (botão "✎ Observação" no editor) vai para `roteiros/observacoes_edicao.jsonl` (texto dele + o que foi
feito ao resolver). Este módulo transforma esse corpus em `roteiros/crivo_edicao.md`, lido ANTES de editar qualquer
vídeo (skill editar-video §0):

- cada observação é classificada por tema (legenda, som, transição, tela dividida/TV, lettering, motion, ativo/B-roll,
  corte/ritmo, início/fim) e listada com as PALAVRAS DELE e a correção que funcionou;
- PESO pelo kanban do roteiro: vídeos "publicado" (peso 3) e "editado" (2) são as referências de boa prática — o que
  ele cobrou neles e foi aprovado no fim vale mais; os demais (ensaios, gravações em andamento) pesam 1;
- temas que se REPETEM em vários vídeos sobem para o topo ("ele já falou N vezes") — é o que não pode voltar a errar;
- as referências aprovadas (editado/publicado) entram com o resumo do que o plano final usou (layouts, motions),
  como modelo — não para copiar a identidade, e sim para dar peso ao que ele aprovou.

Uso: `crivo` (CLI) regenera; também roda sozinho a cada `resolver-obs`.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "roteiros" / "observacoes_edicao.jsonl"
OUT = ROOT / "roteiros" / "crivo_edicao.md"

TEMAS = [
    ("Legenda", r"legenda|palavra vi[uú]va|vi[uú]va|extremidade|grudad|borda|sobrepost|tachad|risco na legenda|branco com fundo"),
    ("Som e efeitos sonoros", r"barulho|som\b|sons\b|clique|click|flash de foto|registradora|whoosh|rebobinar|m[uú]sica|volume"),
    ("Transição", r"transi[cç][aã]o|lampejo|luz quente|leak|voltar pra mesma|mesma cena|mesma tela"),
    ("Tela dividida e TV", r"tela dividid|50.?50|dividida|\btv\b|televis|moldura|retangulo da tv|bordinha"),
    ("Lettering, destaque e frases", r"lettering|destaque|letra|pequen|tamanho|caixa alta|contraste|leg[ií]vel|dif[ií]cil de ler|palavra .* (gigante|impact)"),
    ("Motion e animação", r"motion|anima|est[aá]tic|em movimento|mexendo|dopamina|parado|monoton|xox|sem gra[cç]a|emoji|card|polaroid|riscad|avi[aã]o"),
    ("Ativos e B-roll (escolha e sentido)", r"b-?roll|cena|ativo|imagem|foto|v[ií]deo d[eo]|comercial|banco de|sentido|pertinente|podre|amador|real\b|casar|combina"),
    ("Corte, ritmo e travadas", r"travou|trav|bug|tremid|tremul|milisegundo|frame|congel|ritmo|din[aâ]mic|tempo demais|muito tempo|corta|cortad"),
    ("Início, gancho e fim", r"come[cç]o|in[ií]cio|hook|gancho|final|fim\b|acabar|acabe|[uú]ltimo frame|cara de bunda|olhando pro nada"),
    ("Rosto e enquadramento", r"rosto|cara\b|cabe[cç]a|queixo|olhos|enquadr|zoom|mal posicionad"),
]
PESO = {"publicado": 3, "editado": 2}


def _classifica(texto):
    t = (texto or "").lower()
    achou = [nome for nome, rx in TEMAS if re.search(rx, t)]
    return achou or ["Outros"]


def _carrega():
    if not CORPUS.exists():
        return []
    novas, res = {}, {}
    for ln in CORPUS.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        k = (e.get("project"), e.get("id"))
        if e.get("event") in ("nova", "restaurada"):
            novas[k] = e
        elif e.get("event") == "apagada":       # ele se arrependeu e apagou: não vira aprendizado
            novas.pop(k, None)
            res.pop(k, None)
        elif e.get("event") == "editada" and k in novas and e.get("text"):
            novas[k] = {**novas[k], "text": e["text"]}
        elif e.get("event") in ("resolvido", "resolvida"):
            res[k] = e
    out = []
    for k, e in novas.items():
        r = res.get(k)
        out.append({**e, "resolution": (r or {}).get("resolution") or e.get("resolution"), "resolvida": bool(r)})
    return out


def _contexto_projetos():
    """projeto → (código do roteiro, status no kanban, nome)."""
    from . import roteiros
    from .store import load
    ctx = {}
    try:
        rs = roteiros.load()
    except Exception:  # noqa: BLE001
        rs = []
    by_pid = {r.get("project"): r for r in rs if r.get("project")}
    by_code = {r["code"]: r for r in rs}
    for pid in {e.get("project") for e in _carrega()}:
        try:
            p = load(pid)
        except Exception:  # noqa: BLE001
            ctx[pid] = (None, None, pid)
            continue
        r = by_pid.get(pid) or by_code.get(p.get("roteiro"))
        ctx[pid] = (r and r["code"], r and r["status"] if r and r.get("project") == pid else None, p.get("name", pid))
    return ctx, rs


def _resumo_plano(code):
    f = ROOT / "roteiros" / "edicao" / f"{code}.json"
    if not f.exists():
        return ""
    try:
        pl = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    ov = pl.get("overlays", [])
    lay = Counter((o.get("layout") or "full") for o in ov if o.get("type") == "media")
    mot = Counter(o.get("template") for o in ov if o.get("type") == "motion")
    emp = sum(1 for o in ov if o.get("type") == "emphasis")
    sfx = Counter(o.get("sfx") for o in ov if o.get("type") == "sfx")
    partes = [f"{sum(lay.values())} ativos ({', '.join(f'{k} {v}' for k, v in lay.most_common())})",
              f"motions: {', '.join(f'{k}' for k in mot) or '—'}", f"{emp} frase(s) de destaque",
              f"sons do plano: {', '.join(k for k in sfx) or '—'}"]
    if pl.get("musica"):
        partes.append(f"música {pl['musica'].get('file')} (vol {pl['musica'].get('vol')})")
    return "; ".join(partes)


def gerar():
    obs = _carrega()
    ctx, rs = _contexto_projetos()
    porta = defaultdict(list)
    projetos_por_tema = defaultdict(set)
    for e in obs:
        code, status, nome = ctx.get(e.get("project"), (None, None, e.get("project")))
        peso = PESO.get(status, 1)
        for tema in _classifica(e.get("text")):
            porta[tema].append((peso, e.get("created", ""), code or nome, status, e))
            projetos_por_tema[tema].add(e.get("project"))
    linhas = ["# Crivo de edição do Roberto (gerado das observações dele nos vídeos)", "",
              f"_{len(obs)} observações · gerado por `app/crivo.py` (`crivo`) — NÃO edite à mão; o que ele escreve nos vídeos "
              "atualiza isto._", "",
              "Leia ANTES de montar/ajustar qualquer vídeo. Peso: ★★★ vídeo publicado · ★★ editado · ★ ensaio/em andamento. "
              "Tema citado em vários vídeos = ele já cobrou mais de uma vez: NÃO PODE voltar a acontecer.", ""]
    # o que mais se repete (por nº de vídeos diferentes e peso)
    rank = sorted(porta, key=lambda t: (-len(projetos_por_tema[t]), -sum(p for p, *_ in porta[t])))
    linhas += ["## O que ele mais cobra (temas por nº de vídeos)", ""]
    for t in rank:
        linhas.append(f"- **{t}** — {len(porta[t])} observações em {len(projetos_por_tema[t])} vídeo(s)")
    linhas.append("")
    # referências aprovadas
    aprov = [r for r in rs if r.get("status") in PESO and r.get("project")]
    if aprov:
        linhas += ["## Referências aprovadas (kanban: editado/publicado) — boas práticas, não identidade", ""]
        for r in sorted(aprov, key=lambda r: r["code"]):
            linhas.append(f"- **{r['code']} — {r['title'][:70]}** ({r['status']}, projeto `{r['project']}`): {_resumo_plano(r['code'])}")
        linhas.append("")
    for t in rank:
        linhas += [f"## {t}", ""]
        itens = sorted(porta[t], key=lambda x: (-x[0], x[1]), reverse=False)
        itens = sorted(itens, key=lambda x: (-x[0], [-ord(c) for c in x[1]]))   # peso maior primeiro, mais recente antes
        for peso, created, onde, status, e in itens[:40]:
            estrela = "★" * peso
            txt = re.sub(r"\s+", " ", e.get("text") or "").strip()
            linha = f"- {estrela} [{onde}, {created[:10]}] “{txt}”"
            if e.get("resolution"):
                feito = re.sub(r"\s+", " ", e["resolution"]).strip()
                linha += f" → **feito:** {feito}"
            linhas.append(linha)
        linhas.append("")
    OUT.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return OUT, len(obs)

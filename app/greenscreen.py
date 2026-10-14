"""TELA VERDE (estilo nativo do TikTok/Reels): o print vira o fundo e você fica no cantinho, lendo.

Overlay: {"type": "greenscreen", "file": <imagem em assets/>, "w0", "w1", "corner": "bl"|"br", "size": 0.52}

UX sem retrabalho: você grava lendo a mensagem em voz alta e manda o print junto (arquivo de apoio).
O editor LÊ o print (OCR local) e acha sozinho o trecho em que a sua fala bate com o texto — ali entra a tela verde.
Também dá para aplicar à mão em qualquer trecho (aba Edição → Seus arquivos → "Tela verde").
"""
import json
from pathlib import Path

from . import ocr

STOP = {"de", "da", "do", "das", "dos", "a", "o", "as", "os", "e", "que", "um", "uma", "pra", "para", "com", "na",
        "no", "em", "se", "por", "mas", "eu", "voce", "nao", "sim", "ja", "isso", "esse", "essa", "ao", "aos"}


def ocr_tokens(img):
    """Palavras do print (com cache ao lado do arquivo)."""
    img = Path(img)
    cache = img.with_suffix(img.suffix + ".ocr.json")
    if cache.exists():
        return json.loads(cache.read_text())
    toks = ocr.tokens(img)
    cache.write_text(json.dumps(toks, ensure_ascii=False))
    return toks


def find_read_span(words, deleted, img, min_hits=6):
    """Trecho (w0, w1, acertos) em que a fala bate com o texto do print, ou None.
    Soma +1 para cada palavra falada que está no print (e +1 extra se o par de palavras também está),
    −0,45 para as que não estão; o maior trecho positivo (máxima subsequência) é a leitura."""
    toks = ocr_tokens(img)
    if not toks:
        return None
    vocab = set(toks)
    bigrams = set(zip(toks, toks[1:]))
    dl = set(deleted)
    kept = [w for w in words if w["i"] not in dl and w["w"].strip()]
    best, cur, start = (0.0, None, None, 0), 0.0, None
    hits = 0
    prev = None
    for k, w in enumerate(kept):
        t = ocr.norm(w["w"])
        hit = t in vocab and (len(t) >= 3 or t not in STOP)
        score = (1.0 if hit else -0.45) + (1.0 if prev and (prev, t) in bigrams else 0)
        prev = t
        if cur <= 0:
            cur, start, hits = 0.0, k, 0
        cur += score
        hits += 1 if hit else 0
        if cur > best[0]:
            best = (cur, start, k, hits)
    sc, a, b, hits = best
    if a is None or hits < min_hits:
        return None
    # pontas: começa e termina numa palavra FORTE do print (não em "que", "e", "o"…)
    strong = lambda k: (lambda t: t in vocab and len(t) >= 4 and t not in STOP)(ocr.norm(kept[k]["w"]))
    while a < b and not strong(a):
        a += 1
    while b > a and not strong(b):
        b -= 1
    return kept[a]["i"], kept[b]["i"], hits


def detect(project, pdir, file):
    """Overlay de tela verde para `file` no trecho em que você lê o print (ou None)."""
    img = Path(pdir) / "assets" / file
    if not img.exists():
        return None
    span = find_read_span(project.get("words", []), project.get("deleted", []), img)
    if not span:
        return None
    w0, w1, hits = span
    return {"type": "greenscreen", "file": file, "w0": w0, "w1": w1, "corner": "bl", "size": 0.52,
            "reason": f"você lendo o print ({hits} palavras batem)"}


def auto_detect(project, pdir):
    """Para cada print de apoio ainda sem tela verde: se você o lê no vídeo, coloca a tela verde ali."""
    from .media import kind_of
    from .plan import new_id
    have = {o.get("file") for o in project.get("overlays", []) if o.get("type") == "greenscreen"}
    credits = {c.get("file") for c in project.get("credits", [])}
    added = []
    for f in sorted((Path(pdir) / "assets").iterdir()):
        if f.name in have or f.name in credits or kind_of(f.name) != "image" or f.name.startswith("."):
            continue
        try:
            o = detect(project, pdir, f.name)
        except Exception:  # noqa: BLE001 (OCR indisponível: segue sem)
            o = None
        if o:
            o.update(id=new_id())          # não é "auto": um plano novo não apaga
            extra = enrich(project, pdir, o)
            project.setdefault("overlays", []).append(o)
            project["overlays"].extend(extra)
            added.append(o)
    return added


# ---------------------------------------------------------------- padrão aprovado pelo usuário (V001, out/2026)

def _bullet_lines(img):
    """Linhas do print que começam com marcador (✅ ☑ • - ou o ✅ que o OCR lê como "V"): os "tópicos" da mensagem."""
    from PIL import Image
    lines = ocr.read(img)
    if not lines:
        return []
    im = Image.open(img).convert("RGB")
    px = im.load()
    margin = int(min(l["box"][0] for l in lines if len(l["text"]) > 3))
    out = []
    for l in lines:
        x0, y0, x1, y1 = (int(v) for v in l["box"])
        txt = l["text"].strip()
        mark = txt[:2] in ("V ", "✅", "☑", "✔") or txt[:1] in "•-–✓"
        if not mark:      # ✅ verde à esquerda do texto (o OCR costuma pular o emoji)
            h = max(4, y1 - y0)
            greens = 0
            for x in range(max(0, min(x0, margin) - 6), min(im.width, max(x0, margin) + int(h * 1.4)), 2):
                for y in range(y0 + h // 4, y1 - h // 4, 2):
                    r, g, b = px[x, y]
                    greens += g > 150 and g > r + 40 and g > b + 40
            mark = greens > 12
        if mark:
            body = txt[2:] if txt[:2] in ("V ", "✅", "☑", "✔") else txt.lstrip("•-–✓ ")
            toks = [ocr.norm(t) for t in body.split() if ocr.norm(t)]
            if toks:
                out.append((y0, toks))
    return [t for _, t in sorted(out)]


def enrich(project, pdir, ov):
    """Completa uma tela verde com o padrão aprovado pelo usuário:
    1) borra dados sensíveis do print (R$, lista de participantes do grupo) numa cópia "_oculto";
    2) luz (`leak`) no corte de entrada, sem som;
    3) um CLIQUE na palavra em que você começa a ler cada tópico (✅/•) do print.
    Devolve os overlays novos (sons/transição); `ov` é alterado no lugar (arquivo borrado)."""
    from .plan import new_id
    from . import prints_soma
    assets = Path(pdir) / "assets"
    src = assets / ov["file"]
    extra = []
    try:
        if "_oculto" not in src.stem:
            dst = assets / f"{src.stem}_oculto.jpg"
            if prints_soma.hide(src, dst, prints_soma.HIDE_GENERIC) > 0:
                ov["file"] = dst.name
    except Exception:  # noqa: BLE001 (sem OCR: segue com o original)
        pass
    words, dl = project.get("words", []), set(project.get("deleted", []))
    have = project.get("overlays", [])
    if not any(o.get("type") == "transition" and o.get("w0") == ov["w0"] for o in have):
        extra.append({"id": new_id(), "type": "transition", "style": "leak", "w0": ov["w0"], "w1": ov["w0"],
                      "reason": "entrada da tela verde (sem som)"})
    try:
        bullets = _bullet_lines(src)
    except Exception:  # noqa: BLE001
        bullets = []
    k = ov["w0"]
    kept = [i for i in range(ov["w0"], min(ov["w1"], len(words) - 1) + 1) if i not in dl and words[i]["w"].strip()]
    for toks in bullets:
        lead = 0                                   # palavrinhas antes da 1ª palavra forte ("a", "o")
        while lead < len(toks) and len(toks[lead]) < 3:
            lead += 1
        if lead >= len(toks):
            continue
        key, rest = toks[lead], [t for t in toks[lead + 1:lead + 4] if len(t) >= 3]
        for n, i in enumerate(kept):
            if i < k or ocr.norm(words[i]["w"]) != key:
                continue
            ahead = {ocr.norm(words[j]["w"]) for j in kept[n + 1:n + 4]}
            if len(key) < 5 and rest and not ahead & set(rest):
                continue                           # palavra curta/comum: exige a seguinte também
            m = n                                  # volta para incluir o "a"/"o" do começo do tópico
            for t in reversed(toks[:lead]):
                if m > 0 and ocr.norm(words[kept[m - 1]]["w"]) == t:
                    m -= 1
            w = kept[m]
            if not any(o.get("type") == "sfx" and o.get("w0") == w for o in have + extra):
                extra.append({"id": new_id(), "type": "sfx", "sfx": "click_classico", "w0": w, "w1": w,
                              "reason": "tópico do print"})
            k = i + 1
            break
    return extra

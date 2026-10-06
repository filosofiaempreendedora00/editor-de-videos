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
            project.setdefault("overlays", []).append(o)
            added.append(o)
    return added

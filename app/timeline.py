"""Lógica central da edição: a partir das palavras mantidas, calcula os trechos
do vídeo original que entram no corte final, e mapeia tempos do original para
tempos do vídeo exportado. Tudo é derivado — o projeto só guarda quais palavras
foram apagadas, as configurações e as inserções."""
import re

# Hesitações puras — nunca carregam conteúdo, podem ser cortadas sem medo.
FILLERS = {
    "ahn", "ãh", "ã", "ah", "eh", "éh", "é...", "éé", "ééé", "hum", "humm", "hmm", "hm",
    "uhm", "umm", "uh", "er", "erm", "mm", "mhm", "ãã", "aaa", "aa", "ehh", "ahh",
}

DEFAULT_SETTINGS = {
    "max_pause": 0.45,       # pausas maiores que isso são cortadas (segundos)
    "pad": 0.08,             # respiro mantido antes/depois de cada fala
    "transition": "zoom",    # cut | zoom | fade
    "captions": "pop",       # none | pop | classic
    "uppercase": True,
    "format": "original",    # original | 9:16 | 1:1 | 16:9
    "music": None,           # arquivo em assets/
    "music_volume": 0.15,
    "fade_duration": 0.25,
    "look": "none",          # none | cinema | quente | frio | pb | vintage | vivido
    "voice": True,           # tratamento de voz (limpeza de ruído + compressão + presença)
    "background": "none",    # none | blur | escuro   (recorte de fundo)
    "sfx_volume": 0.55,
    "zoom_strength": 1.12,   # zoom alternado entre cortes
    "emphasis_zoom": 1.28,   # zoom de ênfase
}

# tipos de inserção ancoradas em palavras
VISUAL_TYPES = {"text", "media", "motion", "behind", "perspective"}
POINT_TYPES = {"sfx", "flash"}  # acontecem num instante (início da palavra w0)

FADE_MIN_SEGMENT = 0.6


def norm(word):
    return re.sub(r"[^\wãáàâéêíóôõúç.]", "", word.lower()).strip(".")


def is_filler(word):
    w = norm(word)
    return w in FILLERS or bool(re.fullmatch(r"(h+u+m+|u+m{2,}|u+|h?m{2,}|hm|a+h+m*|e+h+|ã{2,})", w or "x"))


def compute_segments(words, deleted, settings, duration):
    """Retorna [{start, end, w0, w1}] em tempo do vídeo original."""
    deleted = set(deleted)
    max_pause = float(settings.get("max_pause", 0.45))
    pad = float(settings.get("pad", 0.08))
    groups = []
    cur = None
    prev = None
    for w in words:
        if w["i"] in deleted:
            prev = w
            continue
        new_group = (
            cur is None
            or (prev is not None and prev["i"] in deleted)
            or (w["start"] - cur["last"]["end"] > max_pause)
        )
        if new_group:
            cur = {"first": w, "last": w}
            groups.append(cur)
        else:
            cur["last"] = w
        prev = w

    segs = []
    for g in groups:
        f, l = g["first"], g["last"]
        # o respiro nunca invade a palavra vizinha (apagada ou em outro trecho)
        lo = words[f["i"] - 1]["end"] if f["i"] > 0 else 0.0
        hi = words[l["i"] + 1]["start"] if l["i"] + 1 < len(words) else duration
        start = max(f["start"] - pad, min(lo, f["start"]), 0.0)
        end = min(l["end"] + pad, max(hi, l["end"]), duration)
        if end - start < 0.12:
            continue
        segs.append({"start": round(start, 3), "end": round(end, 3), "w0": f["i"], "w1": l["i"]})

    # junta trechos que se sobrepõem ou quase se encostam
    merged = []
    for s in segs:
        if merged and s["start"] - merged[-1]["end"] < 0.05:
            merged[-1]["end"] = max(merged[-1]["end"], s["end"])
            merged[-1]["w1"] = s["w1"]
        else:
            merged.append(dict(s))
    return merged


def split_pieces(segs, words, overlays, settings):
    """Subdivide os trechos onde há zoom de ênfase. Peças da mesma `g` são contínuas
    no vídeo original (sem corte entre elas)."""
    zooms = []
    for o in overlays:
        if o.get("type") == "zoom" and words:
            w0 = max(0, min(o["w0"], len(words) - 1))
            w1 = max(w0, min(o["w1"], len(words) - 1))
            zooms.append((words[w0]["start"] - 0.05, words[w1]["end"] + 0.15, float(o.get("scale") or 0)))
    base_z = float(settings.get("zoom_strength", 1.12))
    emph = float(settings.get("emphasis_zoom", 1.28))
    pieces = []
    for g, s in enumerate(segs):
        base = base_z if (settings.get("transition") == "zoom" and g % 2 == 1) else 1.0
        cuts = {s["start"], s["end"]}
        for a, b, _ in zooms:
            if s["start"] < a < s["end"]:
                cuts.add(a)
            if s["start"] < b < s["end"]:
                cuts.add(b)
        pts = sorted(cuts)
        for a, b in zip(pts, pts[1:]):
            if b - a < 0.04:
                continue
            mid = (a + b) / 2
            z = base
            for za, zb, zs in zooms:
                if za <= mid <= zb:
                    z = zs or (emph if base == 1.0 else max(emph, base + 0.14))
            pieces.append({"start": round(a, 3), "end": round(b, 3), "g": g, "zoom": round(z, 3)})
    # funde peças vizinhas com o mesmo zoom
    out = []
    for p in pieces:
        if out and out[-1]["g"] == p["g"] and out[-1]["zoom"] == p["zoom"] and abs(out[-1]["end"] - p["start"]) < 0.005:
            out[-1]["end"] = p["end"]
        else:
            out.append(p)
    return out


def assign_output_times(pieces, segs, settings):
    """Acrescenta `out` (início no vídeo final) a peças e trechos."""
    td = transition_duration(segs, settings)
    t = 0.0
    for k, p in enumerate(pieces):
        p["out"] = round(t, 3)
        new_group_next = k + 1 < len(pieces) and pieces[k + 1]["g"] != p["g"]
        t += (p["end"] - p["start"]) - (td if new_group_next else 0)
    for g, s in enumerate(segs):
        first = next(p for p in pieces if p["g"] == g)
        s["out"] = first["out"] + (first["start"] - s["start"])
    return (round(t, 3) if pieces else 0.0), td


def transition_duration(segs, settings):
    if settings.get("transition") != "fade" or len(segs) < 2:
        return 0.0
    shortest = min(s["end"] - s["start"] for s in segs)
    return round(min(float(settings.get("fade_duration", 0.25)), shortest / 2.5), 3)


def to_output(pieces, t):
    """Tempo original -> tempo final. Se cair num corte, devolve o início do próximo trecho."""
    for s in pieces:
        if t < s["start"]:
            return s["out"]
        if t <= s["end"]:
            return s["out"] + (t - s["start"])
    if pieces:
        last = pieces[-1]
        return last["out"] + last["end"] - last["start"]
    return 0.0


def overlay_window(pieces, words, ov):
    """Janela [ini, fim] no vídeo final de uma inserção ancorada nas palavras w0..w1."""
    w0 = max(0, min(ov["w0"], len(words) - 1))
    w1 = max(w0, min(ov.get("w1", w0), len(words) - 1))
    a = to_output(pieces, words[w0]["start"])
    if ov.get("type") in POINT_TYPES:
        return round(max(0.0, a + float(ov.get("offset", 0))), 3), round(a + 0.5, 3)
    b = to_output(pieces, words[w1]["end"])
    if ov.get("duration"):
        b = a + float(ov["duration"])
    if b - a < 0.8:
        b = a + max(0.8, float(ov.get("min_duration", 1.5)))
    return round(a, 3), round(b, 3)


def caption_chunks(pieces, segs, words, deleted, max_words=3, max_chars=20):
    """Agrupa as palavras mantidas em blocos curtos de legenda, com tempo de cada palavra."""
    deleted = set(deleted)
    chunks = []
    for s in segs:
        cur = []
        for i in range(s["w0"], s["w1"] + 1):
            if i in deleted:
                continue
            w = words[i]
            item = {"w": w["w"], "a": round(to_output(pieces, max(w["start"], s["start"])), 3),
                    "b": round(to_output(pieces, min(w["end"], s["end"])), 3)}
            chars = sum(len(x["w"]) + 1 for x in cur) + len(w["w"])
            gap = (w["start"] - words[i - 1]["end"]) if cur else 0
            if cur and (len(cur) >= max_words or chars > max_chars or gap > 0.6
                        or re.search(r"[.?!:;]$", cur[-1]["w"])):
                chunks.append(cur)
                cur = []
            cur.append(item)
        if cur:
            chunks.append(cur)
    out = []
    for k, c in enumerate(chunks):
        a = c[0]["a"]
        b = c[-1]["b"] + 0.25
        if k + 1 < len(chunks):
            b = min(b, chunks[k + 1][0]["a"])
        out.append({"a": a, "b": round(max(b, c[-1]["b"]), 3), "words": c})
    return out


def compute(project):
    """Tudo que o editor e o render precisam, derivado do estado salvo."""
    settings = {**DEFAULT_SETTINGS, **project.get("settings", {})}
    words = project.get("words", [])
    deleted = project.get("deleted", [])
    duration = project["source"]["duration"]
    overlays_in = project.get("overlays", [])
    if words:
        segs = compute_segments(words, deleted, settings, duration)
    else:
        segs = [{"start": 0.0, "end": duration, "w0": 0, "w1": -1}]
    pieces = split_pieces(segs, words, overlays_in, settings)
    total, td = assign_output_times(pieces, segs, settings)
    overlays = []
    for ov in overlays_in:
        if not words or ov.get("type") == "zoom" or "w0" not in ov:
            continue
        a, b = overlay_window(pieces, words, ov)
        if a >= total:
            continue
        overlays.append({**ov, "a": a, "b": min(b, total)})
    caps = caption_chunks(pieces, segs, words, deleted) if words else []
    removed = duration - sum(s["end"] - s["start"] for s in segs)
    return {"segments": pieces, "cuts": segs, "duration": total, "transition_duration": td,
            "overlays": overlays, "captions": caps, "settings": settings,
            "removed_seconds": round(removed, 2)}

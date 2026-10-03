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
}

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


def assign_output_times(segs, settings):
    """Acrescenta `out` (início no vídeo final) a cada trecho."""
    td = transition_duration(segs, settings)
    t = 0.0
    for k, s in enumerate(segs):
        s["out"] = round(t, 3)
        t += (s["end"] - s["start"]) - (td if k < len(segs) - 1 else 0)
    total = round(t, 3) if segs else 0.0
    return total, td


def transition_duration(segs, settings):
    if settings.get("transition") != "fade" or len(segs) < 2:
        return 0.0
    shortest = min(s["end"] - s["start"] for s in segs)
    return round(min(float(settings.get("fade_duration", 0.25)), shortest / 2.5), 3)


def to_output(segs, t):
    """Tempo original -> tempo final. Se cair num corte, devolve o início do próximo trecho."""
    for s in segs:
        if t < s["start"]:
            return s["out"]
        if t <= s["end"]:
            return s["out"] + (t - s["start"])
    if segs:
        last = segs[-1]
        return last["out"] + last["end"] - last["start"]
    return 0.0


def overlay_window(segs, words, ov):
    """Janela [ini, fim] no vídeo final de uma inserção ancorada nas palavras w0..w1."""
    w0 = max(0, min(ov["w0"], len(words) - 1))
    w1 = max(w0, min(ov["w1"], len(words) - 1))
    a = to_output(segs, words[w0]["start"])
    b = to_output(segs, words[w1]["end"])
    if b - a < 0.8:
        b = a + max(0.8, float(ov.get("min_duration", 1.5)))
    return round(a, 3), round(b, 3)


def caption_chunks(segs, words, deleted, settings, max_words=3, max_chars=20):
    """Agrupa as palavras mantidas em blocos curtos de legenda, com tempo de cada palavra."""
    deleted = set(deleted)
    chunks = []
    for s in segs:
        cur = []
        for i in range(s["w0"], s["w1"] + 1):
            if i in deleted:
                continue
            w = words[i]
            item = {"w": w["w"], "a": round(to_output(segs, max(w["start"], s["start"])), 3),
                    "b": round(to_output(segs, min(w["end"], s["end"])), 3)}
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
    if words:
        segs = compute_segments(words, deleted, settings, duration)
    else:
        segs = [{"start": 0.0, "end": duration, "w0": 0, "w1": -1}]
    total, td = assign_output_times(segs, settings)
    overlays = []
    for ov in project.get("overlays", []):
        if not words:
            continue
        a, b = overlay_window(segs, words, ov)
        overlays.append({**ov, "a": a, "b": min(b, total)})
    caps = caption_chunks(segs, words, deleted, settings) if words else []
    removed = duration - sum(s["end"] - s["start"] for s in segs)
    return {"segments": segs, "duration": total, "transition_duration": td,
            "overlays": overlays, "captions": caps, "settings": settings,
            "removed_seconds": round(removed, 2)}

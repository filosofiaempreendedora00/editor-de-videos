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
    "captions": "clean",     # clean (padrão, estilo "está rolando") | pop | classic | none
    "caption_case": "lower", # lower | original | upper
    "uppercase": False,      # (legado) usado pelos títulos
    "accent": "#C29A5B",     # cor da palavra-chave das frases de destaque
    "style": "padrao",       # identidade visual (app/presets)
    "caption_color": "#FFFFFF",
    "caption_outline": "#000000",
    "caption_box": False,
    "caption_box_color": "#000000",
    "caption_box_opacity": 0.6,
    "panel_color": "#FFFFFF",
    "panel_line": "#C29A5B",
    "panel_text": "#111111",
    "progress_bar": False,
    "progress_color": "#C29A5B",
    "flashes": True,
    "format": "original",    # original | 9:16 | 1:1 | 16:9
    "music": None,           # arquivo em assets/
    "music_volume": 0.15,
    "fade_duration": 0.25,
    "speed": 1.0,            # velocidade final do vídeo (1.1 = 10% mais rápido), voz sem distorção
    "hook_sfx": "reverse_expectativa",   # som de expectativa por baixo do fim do hook ("none" = sem)
    "hook_transition": "leak",           # transição no corte pós-hook ("none" = corte seco)
    "inserts": False,        # B-roll, motions e textos extras (em pausa por enquanto)
    "grade": "auto",         # auto | off — color grading automático do insumo
    "grade_strength": 1.0,
    "look": "none",          # none | cinema | quente | frio | pb | vintage | vivido
    "voice": True,           # tratamento de voz (limpeza de ruído + compressão + presença)
    "background": "none",    # none | blur | escuro   (recorte de fundo)
    "sfx_volume": 0.9,       # volume geral dos efeitos (cada som já tem seu nível próprio)
    "zoom_strength": 1.12,   # zoom alternado entre cortes
    "emphasis_zoom": 1.28,   # zoom de ênfase
    "smooth_zoom": False,    # (vídeos novos: True) zoom suave contínuo em cada trecho, aproximando/afastando
    "scene_transition": "none",  # (vídeos novos: "leak") transição nos cortes grandes (troca de cena)
    "bg_scene": "none",      # cenário no fundo (você + cadeira ficam): biblioteca | gabinete | ... | file:<asset>
    "rhythm_cuts": False,    # (vídeos novos: True) planos de 2–5 s mesmo sem nada a cortar (fala fluida)
    "reframe": False,        # (vídeos novos: True) a cada corte o enquadramento muda (aberto/médio/fechado) — ref. @tay.ldantas
}

# tipos de inserção ancoradas em palavras
VISUAL_TYPES = {"text", "media", "motion", "behind", "perspective", "emphasis"}
POINT_TYPES = {"sfx", "flash", "transition"}  # acontecem num instante (início da palavra w0)

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
        # respiro: um pouco antes do ataque e mais depois do fim (o Whisper marca o fim cedo).
        # Só respeita a palavra vizinha se ela começa claramente depois (timestamps encostados
        # costumam ser imprecisos e cortavam o fim da palavra).
        # pausa/hesitação entre duas falas que ficam -> corte justo; ao lado de fala removida
        # ou no fim do vídeo -> respiro maior (é aí que o fim das palavras era comido)
        prev_kept = f["i"] > 0 and f["i"] - 1 not in deleted
        next_kept = l["i"] + 1 < len(words) and l["i"] + 1 not in deleted
        pad_a = pad if prev_kept else max(pad, 0.1)
        pad_b = max(pad, 0.1) if next_kept else max(pad * 2, 0.2)
        lo = words[f["i"] - 1]["end"] if f["i"] > 0 else 0.0
        hi = words[l["i"] + 1]["start"] if l["i"] + 1 < len(words) else duration
        start = max(f["start"] - pad_a, 0.0)
        if lo < f["start"] - 0.12:
            start = max(start, lo)
        end = min(l["end"] + pad_b, duration)
        if hi > l["end"] + 0.12:
            end = min(end, hi)
        if end - start < 0.12:
            continue
        segs.append({"start": round(start, 3), "end": round(end, 3), "w0": f["i"], "w1": l["i"],
                     "ext_a": not prev_kept, "ext_b": not next_kept})

    # junta trechos que se sobrepõem ou quase se encostam
    merged = []
    for s in segs:
        if merged and s["start"] - merged[-1]["end"] < 0.05:
            merged[-1]["end"] = max(merged[-1]["end"], s["end"])
            merged[-1]["w1"] = s["w1"]
            merged[-1]["ext_b"] = s.get("ext_b")
        else:
            merged.append(dict(s))
    return merged


def _subtract(intervals, cut):
    a, b = cut
    out = []
    for s0, s1 in intervals:
        if b <= s0 or a >= s1:
            out.append((s0, s1))
            continue
        if a > s0:
            out.append((s0, a))
        if b < s1:
            out.append((b, s1))
    return out


def _union(intervals, add):
    allv = sorted(intervals + [add])
    out = []
    for s0, s1 in allv:
        if out and s0 <= out[-1][1] + 0.01:
            out[-1] = (out[-1][0], max(out[-1][1], s1))
        else:
            out.append((s0, s1))
    return out


def refine_segments(segs, words, deleted, settings, duration, silences=(), manual=()):
    """Ajustes finos por TEMPO (não por palavra):
    1) corta silêncios detectados no áudio que ficaram "escondidos" dentro de palavras esticadas;
    2) aplica seus cortes/restaurações manuais da timeline (o que você decide vence a IA)."""
    max_pause = float(settings.get("max_pause", 0.45))
    pad = float(settings.get("pad", 0.08))
    iv = [(s["start"], s["end"]) for s in segs]
    ext = {(s["start"], s["end"]): (s.get("ext_a", True), s.get("ext_b", True)) for s in segs}
    spans = [(w["start"], w["end"]) for w in words if w.get("w")]
    # bordas seguem o som: o trecho termina quando a voz realmente acaba (até +0,35 s)
    # e começa no ataque da primeira palavra (até -0,25 s), sem invadir fala cortada
    if silences:
        sil = sorted(tuple(x) for x in silences)
        dl = [(w["start"], w["end"]) for w in words if w["i"] in set(deleted) and w.get("w")]
        def next_silence(t):
            return next((a for a, b in sil if b > t), duration)
        def prev_silence_end(t):
            ends = [b for a, b in sil if b <= t + 0.02]
            return ends[-1] if ends else 0.0
        def in_silence(t):
            return any(a - 0.01 <= t <= b + 0.01 for a, b in sil)
        out_iv = []
        for s0, s1 in iv:
            ea, eb = ext.get((s0, s1), (True, True))
            nxt_w = min([a for a, b in spans if a >= s1 - 0.02] or [duration])
            prv_w = max([b for a, b in spans if b <= s0 + 0.02] or [0.0])
            # FIM: se a voz acaba logo depois (≤ 0,3 s), o corte acompanha esse "rabo" da palavra;
            # se o som continua, é hesitação ("ééé") e o corte fica justo (ou +0,15 s perto de fala removida)
            s1b = s1
            if not in_silence(s1):
                ns = next_silence(s1)
                if ns - s1 <= 0.45:
                    s1b = ns + 0.03
                elif eb:
                    s1b = s1 + 0.15
                s1b = min(s1b, nxt_w - 0.12) if nxt_w > s1 else s1b
                s1b = max(s1, s1b)
            # COMEÇO: mesmo raciocínio para o ataque da primeira palavra
            s0b = s0
            if not in_silence(s0):
                ps = prev_silence_end(s0)
                if s0 - ps <= 0.3:
                    s0b = ps - 0.02
                elif ea:
                    s0b = s0 - 0.12
                s0b = max(s0b, prv_w + 0.08) if prv_w < s0 else s0b
                s0b = min(s0, s0b)
            out_iv.append((max(0.0, s0b), min(duration, s1b)))
        if out_iv:                            # fim do vídeo: deixa a última palavra "respirar"
            a, b = out_iv[-1]
            dset = set(deleted)
            kept_ends = [w["end"] for w in words if w.get("w") and w["i"] not in dset and w["start"] < b]
            last_word_end = max(kept_ends or [b])
            nxt = min([w["start"] for w in words if w.get("w") and w["start"] > last_word_end + 0.05] or [duration + 1])
            # +0,4 s depois da última palavra mantida, sem entrar numa fala removida logo em seguida
            out_iv[-1] = (a, min(duration, max(b, min(last_word_end + 0.4, nxt + 0.05 if nxt > last_word_end + 0.3 else b))))
        iv = []
        for a, b in sorted(out_iv):           # bordas estendidas não podem se sobrepor
            iv = _union(iv, (a, b))
    for a, b in silences or []:
        if b - a <= max_pause:
            continue
        # nunca corta dentro de uma palavra (o começo suave de "Hoje" parece silêncio para o medidor)
        free = [(a + pad, b - pad)]
        for ws, we in spans:
            if we > a and ws < b:
                free = _subtract(free, (ws - 0.04, we + 0.04))
        for ca, cb in free:
            if cb - ca > 0.15:
                iv = _subtract(iv, (ca, cb))
    for m in manual or []:
        a, b = max(0.0, float(m["a"])), min(duration, float(m["b"]))
        if b - a < 0.02:
            continue
        iv = _union(iv, (a, b)) if m.get("mode") == "keep" else _subtract(iv, (a, b))
    deleted = set(deleted)
    out = []
    for s0, s1 in iv:
        if s1 - s0 < 0.1:
            continue
        inside = [w["i"] for w in words if s0 <= (w["start"] + w["end"]) / 2 <= s1]
        out.append({"start": round(s0, 3), "end": round(s1, 3),
                    "w0": inside[0] if inside else 0, "w1": inside[-1] if inside else -1})
    return out


# enquadramentos que se alternam a cada corte (1.0 = como foi gravado). Nunca repete o anterior; o mais fechado
# aparece de vez em quando, como na referência (aberto → médio → aberto → fechado…)
REFRAME = [1.0, 1.0, 1.12, 1.0, 1.0, 1.22, 1.0, 1.0, 1.1]   # "uma ou outra" troca seca de enquadramento
KB_AMP = 0.06          # zoom suave contínuo: 6% ao longo do trecho (aproxima / afasta, alternando)


def hook_time(words, overlays):
    """Instante (no original) do corte pós-hook, pela transição/som do pós-hook."""
    for reason in ("pós-hook", "expectativa pós-hook"):
        for o in overlays:
            if o.get("reason") == reason and words and 0 <= o.get("w0", -1) < len(words):
                return words[o["w0"]]["start"] + (float(o.get("offset") or 0) if o.get("type") == "sfx" else 0)
    return None


def rhythm_bounds(a, b, words, deleted, start_after=None):
    """CORTES DE RITMO dentro de um trecho contínuo (fala fluida, sem nada para tirar): divide em planos de
    ~2,2–5 s nos finais de frase/vírgula/respiro, para o enquadramento poder mudar (aproxima/afasta)."""
    cands = []
    prev = None
    for w in words:
        if w["i"] in deleted or not w["w"].strip():
            continue
        if prev is not None and a + 0.5 < w["start"] < b - 0.5:
            gap = w["start"] - prev["end"]
            score = 3 if re.search(r"[.?!]$", prev["w"]) else 2 if re.search(r"[,;:]$", prev["w"]) else (1 if gap >= 0.2 else 0)
            cands.append((max(prev["end"], w["start"] - 0.04), score))
        prev = w
    out, cur = [], start_after if start_after is not None else a
    while b - cur > 4.2:
        win = [(t, sc) for t, sc in cands if cur + 2.2 <= t <= cur + 5.0]
        if not win:
            win = [(t, sc) for t, sc in cands if cur + 1.6 <= t <= cur + 6.5]
        if not win:
            break
        t = max(win, key=lambda c: (c[1] * 1.0 - abs(c[0] - (cur + 3.5)) * 0.6))[0]
        if b - t < 1.8:
            break
        out.append(round(t, 3))
        cur = t
    return out


# planos alternados (vídeos novos): ABERTO aproximando devagar ↔ FECHADO afastando devagar; a cada 3º fechado,
# um mais fechado ("quebra de padrão"). Cada corte tem um salto visível de enquadramento.
SHOT_CLOSE = [1.18, 1.18, 1.3]


def split_pieces(segs, words, overlays, settings, deleted=()):
    """Subdivide os trechos em PLANOS (cortes reais, corte do hook e cortes de ritmo) e onde há zoom de ênfase.
    Peças da mesma `g` são contínuas no vídeo original (sem corte de áudio entre elas)."""
    zooms = []
    for o in overlays:
        if o.get("type") == "zoom" and words:
            w0 = max(0, min(o["w0"], len(words) - 1))
            w1 = max(w0, min(o["w1"], len(words) - 1))
            sc = float(o.get("scale") or 0)
            if o.get("rel"):          # relativo ao enquadramento (zoom progressivo de lista)
                sc = -sc
            # peças de lista emendam exatamente na próxima palavra (sem sobra que "pula" o zoom)
            end = words[w1]["end"] + 0.15
            if o.get("rel") and w1 + 1 < len(words):
                end = max(words[w1]["end"], words[w1 + 1]["start"] - 0.05)
            zooms.append((words[w0]["start"] - 0.05, end, sc))
    base_z = float(settings.get("zoom_strength", 1.12))
    emph = float(settings.get("emphasis_zoom", 1.28))
    rhythm = settings.get("rhythm_cuts") and words
    deleted = set(deleted)
    ht = hook_time(words, overlays) if rhythm else None

    # 1) planos: (início, fim, g, tipo do corte que abre o plano)
    shots = []
    for g, s in enumerate(segs):
        bounds = []
        kind0 = "start" if g == 0 else "cut"
        if rhythm:
            hook_here = ht is not None and s["start"] - 0.8 <= ht < s["end"] - 0.5
            if hook_here and abs(ht - s["start"]) <= 0.8:
                kind0 = "hook"                       # o corte real já é o pós-hook
                bounds = [(t, "rhythm") for t in rhythm_bounds(s["start"], s["end"], words, deleted)]
            elif hook_here:
                bounds = [(round(ht - 0.03, 3), "hook")]
                bounds += [(t, "rhythm") for t in rhythm_bounds(s["start"], s["end"], words, deleted, start_after=ht)
                           if t > ht + 1.5]
            elif ht is not None and s["end"] <= ht + 0.5:
                bounds = []                          # dentro do hook: um plano só (aproximando no rosto)
            else:
                bounds = [(t, "rhythm") for t in rhythm_bounds(s["start"], s["end"], words, deleted)]
        pts = [(s["start"], kind0)] + sorted(bounds) + [(s["end"], None)]
        for (t0, k), (t1, _) in zip(pts, pts[1:]):
            if t1 - t0 > 0.05:
                shots.append({"start": t0, "end": t1, "g": g, "kind": k})

    # 2) enquadramento e zoom suave de cada plano
    nclose = 0
    for n, sh in enumerate(shots):
        dur = sh["end"] - sh["start"]
        if rhythm:
            in_hook = ht is not None and sh["end"] <= ht + 0.05 and sh["g"] == 0 and n == 0
            if in_hook:                              # começo do vídeo: aproxima devagar no rosto até o som
                sh["base"], sh["kb"] = 1.0, (1.0, 1.0 + min(0.16, 0.035 * dur))
            elif n % 2 == 1:                         # FECHADO, afastando devagar
                sh["base"] = SHOT_CLOSE[nclose % len(SHOT_CLOSE)]
                nclose += 1
                sh["kb"] = (1.0 + 0.045 * min(1, dur / 3), 1.0)
            else:                                    # ABERTO, aproximando devagar
                sh["base"], sh["kb"] = 1.0, (1.0, 1.0 + 0.05 * min(1, dur / 3))
        else:
            base = base_z if (settings.get("transition") == "zoom" and sh["g"] % 2 == 1) else 1.0
            if settings.get("reframe", True) and len(segs) > 1:
                base = REFRAME[sh["g"] % len(REFRAME)]
            sh["base"], sh["kb"] = base, None

    # 3) peças (cortes de zoom de ênfase/lista dentro dos planos)
    pieces = []
    for n, sh in enumerate(shots):
        cuts = {sh["start"], sh["end"]}
        for a, b, _ in zooms:
            if sh["start"] < a < sh["end"]:
                cuts.add(a)
            if sh["start"] < b < sh["end"]:
                cuts.add(b)
        pts = sorted(cuts)
        first = True
        for a, b in zip(pts, pts[1:]):
            if b - a < 0.04:
                continue
            mid = (a + b) / 2
            base = sh["base"]
            z = base
            for za, zb, zs in zooms:
                if za <= mid <= zb:
                    # zoom de lista (zs < 0) é relativo ao enquadramento: cada item fecha um pouco mais
                    z = base * -zs if zs < 0 else (zs or (emph if base == 1.0 else max(emph, base + 0.14)))
            p = {"start": round(a, 3), "end": round(b, 3), "g": sh["g"], "shot": n, "zoom": round(z, 3)}
            if first and sh["kind"] in ("cut", "hook"):
                p["join"] = sh["kind"]
            first = False
            pieces.append(p)
    # funde peças vizinhas do mesmo plano com o mesmo zoom
    out = []
    for p in pieces:
        if out and out[-1]["shot"] == p["shot"] and out[-1]["zoom"] == p["zoom"] and abs(out[-1]["end"] - p["start"]) < 0.005:
            out[-1]["end"] = p["end"]
        else:
            out.append(p)

    # 4) zoom suave contínuo por plano (ou por trecho, nos projetos sem planos de ritmo)
    if rhythm:
        for n, sh in enumerate(shots):
            k0, k1 = sh["kb"]
            dur = sh["end"] - sh["start"]
            for p in (q for q in out if q["shot"] == n):
                p["kb0"] = round(k0 + (k1 - k0) * (p["start"] - sh["start"]) / dur, 4)
                p["kb1"] = round(k0 + (k1 - k0) * (p["end"] - sh["start"]) / dur, 4)
    elif settings.get("smooth_zoom"):
        n = 0
        for g, s in enumerate(segs):
            dur = s["end"] - s["start"]
            grp = [p for p in out if p["g"] == g]
            if dur < 1.6 or not grp:
                continue
            amp = KB_AMP * min(1.0, dur / 4)            # trecho curto mexe menos
            k0, k1 = (1.0, 1 + amp) if n % 2 == 0 else (1 + amp, 1.0)
            n += 1
            for p in grp:
                p["kb0"] = round(k0 + (k1 - k0) * (p["start"] - s["start"]) / dur, 4)
                p["kb1"] = round(k0 + (k1 - k0) * (p["end"] - s["start"]) / dur, 4)
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
    """Tempo original -> tempo final. Se cair num corte, devolve o início do próximo trecho (no original).
    Funciona também com trechos reordenados (a lista está na ordem do vídeo final)."""
    for s in pieces:
        if s["start"] <= t <= s["end"]:
            return s["out"] + (t - s["start"])
    later = [s for s in pieces if s["start"] > t]
    if later:
        return min(later, key=lambda s: s["start"])["out"]
    if pieces:
        last = max(pieces, key=lambda s: s["end"])
        return last["out"] + last["end"] - last["start"]
    return 0.0


def apply_order(segs, order):
    """Reordena os trechos (estilo CapCut). `order` = um instante do original dentro de cada trecho, na ordem
    desejada. Trechos sem âncora (surgiram de um corte novo) seguem logo depois do trecho que vinha antes
    deles no original — então cortar depois de reordenar não bagunça nada."""
    if not order or len(segs) < 2:
        return segs
    keyed, last, n = [], (-1, 0), 0
    for s in segs:
        k = next((i for i, t in enumerate(order) if s["start"] - 0.01 <= t <= s["end"] + 0.01), None)
        if k is None:
            n += 1
            key = (last[0], n)
        else:
            key, n = (k, 0), 0
        last = key
        keyed.append((key, s))
    return [s for _, s in sorted(keyed, key=lambda x: x[0])]


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


def caption_chunks(pieces, segs, words, deleted, skip=frozenset(), max_words=3, max_chars=18):
    """Agrupa as palavras mantidas em blocos curtos de legenda, com tempo de cada palavra.
    Palavras em `skip` (frases de destaque) não entram na legenda comum."""
    deleted = set(deleted)
    chunks = []
    for s in segs:
        cur = []
        for i in range(s["w0"], s["w1"] + 1):
            w = words[i]
            if i in deleted or not w["w"].strip():
                continue
            if i in skip:
                if cur:
                    chunks.append(cur)
                    cur = []
                continue
            item = {"w": w["w"], "i": i, "a": round(to_output(pieces, max(w["start"], s["start"])), 3),
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


# bigend: palavra-chave enorme e dourada no fim ("o maior número da HISTÓRIA.")
# stack: bloco alinhado à direita, palavra-chave maior ("deixa as pessoas DOENTES.")
EMPHASIS_VARIANTS = ["bigend", "stack"]
SMALL = {"o", "a", "os", "as", "e", "é", "de", "da", "do", "um", "uma", "que", "no", "na", "em", "pra", "para", "se"}


def _width(text, size):
    """Largura aproximada (px) de um texto na Montserrat Alternates com espaçamento apertado."""
    return sum(0.33 if c in "il.,;:!'|" else 0.95 if c in "mwMW" else 0.62 for c in text) * size


def emphasis_layout(ov, pieces, words, deleted, W, H, index=0):
    """Monta a frase de destaque: linhas com tamanhos diferentes e a palavra-chave em dourado.
    Usado igual pelo render (ASS) e pela prévia (HTML)."""
    deleted = set(deleted)
    toks = [{"w": words[i]["w"].rstrip(",;:"), "i": i, "a": round(to_output(pieces, words[i]["start"]), 3)}
            for i in range(ov["w0"], min(ov["w1"], len(words) - 1) + 1)
            if i not in deleted and words[i]["w"].strip()]
    if not toks:
        return None
    variant = ov.get("variant") or EMPHASIS_VARIANTS[index % len(EMPHASIS_VARIANTS)]
    clean = lambda t: re.sub(r"[^\wÀ-ÿ]", "", t.lower())
    key_txt = clean(ov.get("key") or "")
    ki = next((n for n, t in enumerate(toks) if key_txt and clean(t["w"]) == key_txt), None)
    if ki is None:   # palavra mais "forte": a mais longa entre as de conteúdo, preferindo o fim da frase
        cands = [(len(clean(t["w"])) + n * 0.6, n) for n, t in enumerate(toks) if clean(t["w"]) not in SMALL]
        ki = max(cands)[1] if cands else len(toks) - 1
    vertical = H > W
    base = (W * 0.105) if vertical else (H * 0.1)
    maxw = W * (0.88 if vertical else 0.7)

    def group(seq, limit=13):
        lines, cur = [], []
        for t in seq:
            if cur and len(" ".join(x["w"] for x in cur + [t])) > limit:
                lines.append(cur)
                cur = []
            cur.append(t)
        if cur:
            lines.append(cur)
        return lines

    before, key, after = toks[:ki], toks[ki], toks[ki + 1:]
    if variant == "atras":
        return _layout_behind(before, key, after, W, H, base, ov)
    lines = []
    for ln in group(before):
        small = len(ln) == 1 and clean(ln[0]["w"]) in SMALL and variant != "stack"
        lines.append({"words": ln, "scale": 0.7 if small else 1.0, "gold": False})
    key_scale = {"bigend": 1.9, "stack": 1.45}.get(variant, 1.9)
    lines.append({"words": [key], "scale": key_scale, "gold": True})
    for ln in group(after):
        lines.append({"words": ln, "scale": 1.0, "gold": False})
    target = W * (0.66 if vertical else 0.42)   # largura comum das linhas (tipografia justificada)
    for ln in lines:
        text = " ".join(t["w"] for t in ln["words"])
        natural = max(1.0, _width(text, 1))
        if variant == "bigend":
            if ln["scale"] < 1:            # palavrinha solta ("o", "a") fica pequena, como na referência
                size = base * 0.75
            else:                          # cada linha cresce/encolhe até a largura comum
                size = min(max(target / natural, base * 0.8), base * (2.6 if ln["gold"] else 1.7))
        else:
            size = base * ln["scale"]
        size = min(size, maxw / natural)
        ln["size"] = round(size)
        ln["text"] = text
    key_size = max(ln["size"] for ln in lines if ln["gold"])
    for ln in lines:   # a palavra dourada é sempre a maior do bloco
        if not ln["gold"]:
            ln["size"] = min(ln["size"], round(key_size * 0.72))
    # bloco centrado na altura do peito (não tampa o rosto)
    y = H * (0.60 if vertical else 0.55)
    return {"variant": variant, "align": "right" if variant == "stack" else "center", "y": round(y),
            "x": round(W * (0.92 if variant == "stack" else 0.5)), "lines": lines}


def _layout_behind(before, key, after, W, H, base, ov):
    """FRASE ESPECIAL (ref. @tay.ldantas): linhas curtas em zigue-zague no alto (esquerda, centro, direita),
    e a palavra-chave ENORME cruzando a altura da cabeça — no render ela fica atrás da pessoa (recorte).
    Cada linha entra com movimento (de cima / de lado) saindo do desfoque."""
    vertical = H > W
    head_y = float(ov.get("head_y") or (0.30 if vertical else 0.36)) * H   # centro da cabeça (o render ajusta)

    def group(seq, limit=11):
        out, cur = [], []
        for t in seq:
            if cur and len(" ".join(x["w"] for x in cur + [t])) > limit:
                out.append(cur)
                cur = []
            cur.append(t)
        if cur:
            out.append(cur)
        return out

    small = base * 0.62
    aligns = ["left", "right"]          # nunca no centro: ali a cabeça cobre a linha inteira
    lines = []
    for n, ln in enumerate(group(before)):
        text = " ".join(t["w"] for t in ln)
        tiny = len(ln) == 1 and re.sub(r"[^\wÀ-ÿ]", "", ln[0]["w"].lower()) in SMALL
        lines.append({"words": ln, "text": text, "gold": False, "size": round(small * (0.75 if tiny else 1.0)),
                      "align": aligns[n % 2], "enter": "top" if n == 0 else ("right" if n % 2 else "left")})
    ktxt = key["w"]
    ksize = min(W * 0.92 / max(1.0, _width(ktxt, 1)), base * 3.4)
    money = bool(re.search(r"\d", ktxt)) or any(re.search(r"(r\$|us\$|\$|reais|mil|milh|bilh)", t["w"].lower()) for t in before + after)
    lines.append({"words": [key], "text": ktxt, "gold": True, "size": round(ksize), "align": "center",
                  "enter": "rise" if money else "zoom"})
    for n, ln in enumerate(group(after, 14)):
        lines.append({"words": ln, "text": " ".join(t["w"] for t in ln), "gold": False, "size": round(small),
                      "align": "right" if n % 2 == 0 else "left", "enter": "right" if n % 2 == 0 else "left"})
    # posiciona: a palavra-chave centrada na altura da cabeça; o resto acima/abaixo dela
    margin = W * 0.08
    ki = next(n for n, ln in enumerate(lines) if ln["gold"])
    y = head_y - lines[ki]["size"] * 0.5 - sum(ln["size"] * 0.95 for ln in lines[:ki])
    y = max(H * 0.06, y)
    for ln in lines:
        ln["x"] = round({"left": margin, "center": W / 2, "right": W - margin}[ln["align"]])
        ln["top"] = round(y)
        y += ln["size"] * (0.82 if ln["gold"] else 0.95)
    return {"variant": "atras", "align": "center", "y": round(head_y), "x": round(W / 2), "lines": lines,
            "behind": True, "per_line": True}


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
    if project.get("silences") or project.get("manual"):
        segs = refine_segments(segs, words, deleted, settings, duration,
                               project.get("silences"), project.get("manual"))
    segs = apply_order(segs, project.get("order"))
    pieces = split_pieces(segs, words, overlays_in, settings, deleted)
    total, td = assign_output_times(pieces, segs, settings)
    dset = set(deleted)
    joins = []
    for p in pieces:
        if p.get("join"):
            w = next((i for i, x in enumerate(words) if i not in dset and x["w"].strip()
                      and x["start"] >= p["start"] - 0.06 and x["start"] < p["end"]), None)
            if w is not None:
                joins.append({"t": p["start"], "out": p["out"], "kind": p["join"], "w": w})
    overlays = []
    for ov in overlays_in:
        if not words or ov.get("type") == "zoom" or "w0" not in ov:
            continue
        a, b = overlay_window(pieces, words, ov)
        if a >= total:
            continue
        if ov.get("type") in ("transition", "flash"):
            # transição só vale num corte real (ou no corte do hook) — gruda exatamente nele
            t = words[min(ov["w0"], len(words) - 1)]["start"]
            j = min(joins, key=lambda j: abs(j["t"] - t), default=None)
            if not j or abs(j["t"] - t) > 0.8:
                continue
            a, b = j["out"], j["out"] + 0.5
        overlays.append({**ov, "a": a, "b": min(b, total)})
    skip = set()
    for ov in overlays:
        if ov.get("type") == "emphasis":
            skip.update(range(ov["w0"], ov.get("w1", ov["w0"]) + 1))
    caps = caption_chunks(pieces, segs, words, deleted, skip=frozenset(skip)) if words else []
    removed = duration - sum(s["end"] - s["start"] for s in segs)
    from .render import output_size  # import tardio (evita ciclo)
    W, H = output_size(project["source"], settings.get("format", "original"))
    n = 0
    for ov in overlays:
        if ov.get("type") == "emphasis":
            ov["layout"] = emphasis_layout(ov, pieces, words, deleted, W, H, n)
            n += 1
    return {"segments": pieces, "cuts": segs, "joins": joins, "frame": [W, H], "duration": total, "transition_duration": td,
            "overlays": overlays, "captions": caps, "settings": settings,
            "removed_seconds": round(removed, 2)}

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
    "voice": False,          # tratamento de voz (denoise+EQ+compressor) — DESLIGADO: deixava a voz metálica, diferente da prévia
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
    # REGRA DO USUÁRIO (100% das vezes): o hook termina aproximado no rosto; o plano seguinte (pós-hook) vem
    # ABERTO, desaproximado — o contraste é o impacto. A alternância aberto/fechado conta a partir dele.
    hook_first = bool(rhythm and shots and ht is not None and shots[0]["end"] <= ht + 0.05)
    for n, sh in enumerate(shots):
        dur = sh["end"] - sh["start"]
        if rhythm:
            in_hook = hook_first and n == 0
            if in_hook:                              # começo do vídeo: aproxima devagar no rosto até o som
                sh["base"], sh["kb"] = 1.0, (1.0, 1.0 + min(0.16, 0.035 * dur))
            elif (n - hook_first) % 2 == 1:          # FECHADO, afastando devagar
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
                    # (parte de no máximo 1.1: somado a um plano fechado passava de 1.6x e borrava)
                    z = min(base, 1.1) * -zs if zs < 0 else (zs or (emph if base == 1.0 else max(emph, base + 0.14)))
            z = min(z, 1.4)
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

    # TELA VERDE: durante a leitura do print você fica PARADO no canto (sem saltos de enquadramento nem zoom)
    gsr = [(words[o["w0"]]["start"] - 0.3, words[min(o["w1"], len(words) - 1)]["end"] + 0.3)
           for o in overlays if o.get("type") == "greenscreen" and words]
    if gsr:
        for p in out:
            if any(a <= (p["start"] + p["end"]) / 2 <= b for a, b in gsr):
                p["zoom"], p["_still"] = 1.0, True
        merged = []
        for p in out:
            if merged and p.get("_still") and merged[-1].get("_still") and abs(merged[-1]["end"] - p["start"]) < 0.005 \
                    and merged[-1]["g"] == p["g"]:
                merged[-1]["end"] = p["end"]
            else:
                merged.append(p)
        out = merged

    # GRAVAÇÃO EM BAIXA RESOLUÇÃO (ex.: vídeo do WhatsApp, 576x1024): aproximar muito borra, e o zoom contínuo
    # reamostra a imagem a cada quadro — a compressão "ferve" e o teto/cortina parecem tremer (câmera na mão).
    # Aqui os planos ficam PARADOS como no bruto e os saltos de enquadramento são pequenos (pedido do usuário).
    if settings.get("_lowres"):
        for p in out:
            p["zoom"] = round(1.0 + min(0.10, (p["zoom"] - 1.0) * 0.45), 3)
        return out

    # 4) zoom suave contínuo por plano (ou por trecho, nos projetos sem planos de ritmo)
    if rhythm:
        for n, sh in enumerate(shots):
            k0, k1 = sh["kb"]
            dur = sh["end"] - sh["start"]
            for p in (q for q in out if q["shot"] == n and not q.get("_still")):
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


def split_at(segs, splits, words):
    """DIVIDIR (lâmina do CapCut): parte um trecho em dois no instante escolhido, sem tirar nada da fala.
    Dois cortes = um pedaço que dá para selecionar, excluir ou mover."""
    if not splits:
        return segs
    out = []
    for s in segs:
        cuts = sorted(t for t in splits if s["start"] + 0.05 < t < s["end"] - 0.05)
        if not cuts:
            out.append(s)
            continue
        pts = [s["start"]] + cuts + [s["end"]]
        for a, b in zip(pts, pts[1:]):
            ws = [w["i"] for w in words if a <= (w["start"] + w["end"]) / 2 < b] if words else []
            out.append({**s, "start": round(a, 3), "end": round(b, 3),
                        "w0": ws[0] if ws else s.get("w0", 0), "w1": ws[-1] if ws else s.get("w0", 0) - 1,
                        "split": True})
    return out


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
    if b - a < 0.8 and not ov.get("chain"):
        b = a + max(0.8, float(ov.get("min_duration", 1.5)))
    return round(a, 3), round(b, 3)


_PROPER = {"t": 0, "set": set()}


def proper_nouns():
    """Nomes próprios do vocabulário (Turbo, Terry Crews, Old Spice…): a legenda em minúsculas não os rebaixa."""
    import time
    if time.time() - _PROPER["t"] > 5:
        from .transcribe import vocabulary
        _PROPER["set"] = {t for term in vocabulary() for t in re.split(r"\s+", term) if t[:1].isupper()}
        _PROPER["t"] = time.time()
    return _PROPER["set"]


def word_flags(w):
    core = re.sub(r"[^\wÀ-ÿ\-]", "", w["w"])
    flags = {}
    if core and core[0].isupper() and (core in proper_nouns() or w.get("edited")):
        flags["kc"] = True
    if w.get("hl"):
        flags["hl"] = True
    return flags


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
                    "b": round(to_output(pieces, min(w["end"], s["end"])), 3), **word_flags(w)}
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
    toks = [{"w": words[i]["w"].rstrip(",;:"), "i": i, "a": round(to_output(pieces, words[i]["start"]), 3), **word_flags(words[i])}
            for i in range(ov["w0"], min(ov["w1"], len(words) - 1) + 1)
            if i not in deleted and words[i]["w"].strip()]
    if not toks:
        return None
    variant = ov.get("variant") or EMPHASIS_VARIANTS[index % len(EMPHASIS_VARIANTS)]
    clean = lambda t: re.sub(r"[^\wÀ-ÿ]", "", t.lower())
    key_txt = clean(ov.get("key") or "")
    ki = next((n for n, t in enumerate(toks) if key_txt and clean(t["w"]) == key_txt), None)
    if ki is None and len(key_txt) >= 5:   # ele falou outra flexão ("sentir" × "sentiu"): mesma raiz, a última
        ki = next((n for n in range(len(toks) - 1, -1, -1) if clean(toks[n]["w"])[:5] == key_txt[:5]), None)
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
    def build(limit):
        lines = []
        for ln in group(before, limit):
            small = len(ln) == 1 and clean(ln[0]["w"]) in SMALL and variant != "stack"
            lines.append({"words": ln, "scale": 0.7 if small else 1.0, "gold": False})
        key_scale = {"bigend": 1.9, "stack": 1.45}.get(variant, 1.9)
        lines.append({"words": [key], "scale": key_scale, "gold": True})
        for ln in group(after, limit):
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
        return lines

    # bloco na parte de baixo (do peito para baixo): nunca tampa o rosto nem os olhos — e, se o queixo dele foi medido
    # (`chin`, no quadro original), o bloco começa abaixo dele já com o zoom daquele plano
    top_min = H * (0.58 if vertical else 0.55)
    cd = _chin_on_screen(ov, pieces, words)
    if cd is not None:
        top_min = max(top_min, H * min(0.74, cd + 0.025))
    # pouco espaço (rosto baixo) → menos linhas e mais largas, para a letra não ficar miúda: fica o arranjo em que a
    # MENOR linha sai maior
    best = None
    for limit in (13, 18, 24, 32):
        cand = build(limit)
        t = _fit_lower(cand, H, top_min, H * 0.87, gap=0.98, gold_gap=0.98)
        score = min(ln["size"] for ln in cand if ln["scale"] >= 1)
        if best is None or score > best[0] * 1.08:
            best = (score, cand, t)
    _, lines, top = best
    y = top + sum(ln["size"] * 0.98 for ln in lines) / 2      # o render usa y como o centro do bloco
    return {"variant": variant, "align": "right" if variant == "stack" else "center", "y": round(y),
            "x": round(W * (0.92 if variant == "stack" else 0.5)), "lines": lines}


def _chin_on_screen(ov, pieces, words):
    """Altura (0..1) do queixo dele NA TELA durante a frase de destaque (pior caso ao longo do plano)."""
    if ov.get("chin") is None or not pieces:
        return None
    t = words[ov["w0"]]["start"]
    p = next((q for q in pieces if q["start"] - 0.05 <= t < q["end"] + 0.05), None)
    if not p:
        return None
    return max(_display_y(float(ov["chin"]), p, r) for r in (0.0, 0.5, 1.0))


def _fit_lower(lines, H, top_min, bottom_max, gap=0.95, gold_gap=0.86):
    """Encaixa o bloco na parte de BAIXO da tela (regra do usuário: texto nunca tampa o rosto, muito menos os
    olhos). Se não couber entre top_min e bottom_max, diminui tudo por igual. Devolve o topo do bloco."""
    h = lambda: sum(ln["size"] * (gold_gap if ln["gold"] else gap) for ln in lines)
    room = bottom_max - top_min
    if h() > room:
        k = room / h()
        for ln in lines:
            ln["size"] = round(ln["size"] * k)
    return max(top_min, bottom_max - h() - H * 0.02)


def _layout_behind(before, key, after, W, H, base, ov):
    """FRASE ESPECIAL (ref. @tay.ldantas): bloco compacto e legível na parte de BAIXO da tela — linhas curtas
    centralizadas e bem juntas, a palavra-chave ENORME em dourado. Nunca espalhada em zigue-zague e nunca sobre o rosto/olhos (pedido do usuário).
    Cada linha entra saindo do desfoque, com um leve movimento."""
    vertical = H > W
    head_y = float(ov.get("head_y") or (0.30 if vertical else 0.36)) * H   # centro da cabeça (o render ajusta)

    def group(seq, limit=16):
        out, cur = [], []
        for t in seq:
            if cur and len(" ".join(x["w"] for x in cur + [t])) > limit:
                out.append(cur)
                cur = []
            cur.append(t)
        if cur:
            out.append(cur)
        return out

    small = base * 0.7
    lines = []
    for n, ln in enumerate(group(before)):
        lines.append({"words": ln, "text": " ".join(t["w"] for t in ln), "gold": False,
                      "size": round(min(small, W * 0.86 / max(1.0, _width(" ".join(t["w"] for t in ln), 1)))),
                      "align": "center", "enter": "top" if n == 0 else ("left" if n % 2 else "right")})
    ktxt = key["w"]
    ksize = min(W * 0.86 / max(1.0, _width(ktxt, 1)), base * 2.4)
    money = bool(re.search(r"\d", ktxt)) or any(re.search(r"(r\$|us\$|\$|reais|mil|milh|bilh)", t["w"].lower()) for t in before + after)
    lines.append({"words": [key], "text": ktxt, "gold": True, "size": round(ksize), "align": "center",
                  "enter": "rise" if money else "zoom"})
    for n, ln in enumerate(group(after)):
        text = " ".join(t["w"] for t in ln)
        lines.append({"words": ln, "text": text, "gold": False,
                      "size": round(min(small, W * 0.86 / max(1.0, _width(text, 1)))),
                      "align": "center", "enter": "left" if n % 2 == 0 else "right"})
    # abaixo do queixo (cabeça + ~16% da altura) e acima da borda de baixo
    top_min = max(H * (0.58 if vertical else 0.55), head_y + H * (0.17 if vertical else 0.2))
    cd = _chin_on_screen(ov, ov.get("_pieces") or [], ov.get("_words") or [])
    if cd is not None:
        top_min = max(top_min, H * min(0.74, cd + 0.025))
    y = _fit_lower(lines, H, min(top_min, H * 0.66), H * 0.87)
    for ln in lines:
        ln["x"] = round(W / 2)
        ln["top"] = round(y)
        y += ln["size"] * (0.86 if ln["gold"] else 0.95)
    # na frente da pessoa: embaixo, atrás do corpo, ela sumiria (e no alto tamparia o rosto)
    return {"variant": "atras", "align": "center", "y": round(head_y), "x": round(W / 2), "lines": lines,
            "behind": False, "per_line": True}


SPLIT = {"topo_h": 0.40, "overlap": 0.12, "meio_h": 0.45, "tv_h": 0.50, "meio_s": 1.0, "meio_gap": 0.015}


def _snap_to_cuts(overlays, pieces, gap=0.35):
    """B-roll/motion/tela verde que termina (ou começa) a menos de `gap` s de um corte encosta EXATAMENTE nele —
    senão aparecia uma fatia de 2–3 quadros do enquadramento anterior antes do salto de zoom ("zoom truncado/bugado")."""
    cuts = sorted({round(p["out"], 4) for p in pieces} | {round(p["out"] + p["end"] - p["start"], 4) for p in pieces})
    for o in overlays:
        if o.get("type") not in ("media", "motion", "greenscreen") or "a" not in o:
            continue
        nxt = next((c for c in cuts if o["b"] - 0.001 <= c < o["b"] + gap), None)
        if nxt is not None:
            o["b"] = nxt + 0.5 / 30
        prv = next((c for c in reversed(cuts) if o["a"] - gap < c <= o["a"] + 0.001), None)
        if prv is not None and o["a"] - prv > 0.001:
            o["a"] = prv


def _display_y(ys, p, t_rel=0.5):
    """Altura (0..1) na tela de um ponto que está em `ys` (0..1) no quadro ORIGINAL, dado o enquadramento do trecho
    (mesma conta do render: janela 1/zoom com apoio a 40% + zoom suave contínuo kb0→kb1)."""
    z = p.get("zoom", 1.0) or 1.0
    ch = 1 / z
    yd = (ys - (1 - ch) * 0.4) / ch
    kk = p.get("kb0", 1.0) + (p.get("kb1", 1.0) - p.get("kb0", 1.0)) * t_rel
    return (yd - (1 - 1 / kk) * 0.4) * kk


def _place_split_person(overlays, pieces):
    """Telas divididas: posiciona VOCÊ pela altura real da sua cabeça naquele trecho (`head`, medida no quadro original
    ao aplicar o plano). Estilo 1 (topo): o alto da cabeça SEMPRE invade ~7% o ativo de cima. Estilo 2 (meio, 50/50):
    a cabeça fica logo abaixo da divisa (mostra mais o corpo). Sem `head`, ficam os valores padrão."""
    # TV na sala: a câmera da sala continua passeando entre um trecho e outro do mesmo bloco (sem pular de volta)
    tvs = sorted([o for o in overlays if o.get("type") == "media" and o.get("layout") == "tv" and "a" in o], key=lambda o: o["a"])
    t0 = None
    for n, o in enumerate(tvs):
        if n == 0 or o["a"] - tvs[n - 1]["b"] > 0.1:
            t0 = o["a"]
        o["room_t"] = round(o["a"] - t0, 3)
        o["ht"] = SPLIT["tv_h"]
    for o in overlays:
        if o.get("type") == "media" and o.get("layout") == "meio":
            # 50/50 vira ~42/58 (regra dele): o ativo de cima PREENCHE a faixa (recorte, alinhado por `fx`), sem
            # desfoque em cima/embaixo — o desfoque é só a linha da divisa
            o["ht"] = float(o.get("ht_fix") or SPLIT["meio_h"])
        if o.get("type") != "media" or o.get("layout") not in ("topo", "meio", "tv") or o.get("head") is None or "a" not in o:
            continue
        p = next((q for q in pieces if q["out"] <= o["a"] < q["out"] + (q["end"] - q["start"])), None)
        if not p:
            continue
        hd = _display_y(float(o["head"]), p, 0.5)
        if o["layout"] == "topo":
            # a faixa de cima toma a altura EXATA do ativo (sem sobra desfocada em cima/embaixo — reprovado) e a
            # cabeça dele invade ~12% essa faixa (se precisar, ele SOBE: dy negativo)
            ht = SPLIT["topo_h"]
            if o.get("ar"):
                ht = round(min(SPLIT["topo_h"], max(0.22, (1080 / float(o["ar"])) / 1920)), 4)
            o["ht"] = ht
            o["dy"] = round(min(0.35, max(-0.15, ht - SPLIT["overlap"] - hd)), 4)
        else:
            o["yo"] = round(min(0.6, max(0.12, o["ht"] + SPLIT["meio_gap"] - hd * SPLIT["meio_s"])), 4)


def _lift_over_greenscreen(overlays, caps, W, H):
    """Na tela verde você fica recortado no canto de baixo (cabeça por volta de 58% da altura): a legenda e as
    frases de destaque sobem para cima da cabeça, sobre o print — texto nunca no rosto."""
    # legenda que entra enquanto um motion de tela inteira (ex.: AIDA) ainda está na tela: desce para baixo
    busy = [(o["a"], o["b"]) for o in overlays if o.get("type") == "motion" and o.get("hide_captions")]
    for c in caps:
        if any(a < c["b"] and c["a"] < b for a, b in busy):
            c["y"] = 0.85
    # REGRA DELE (100% das vezes): com a tvzinha (`viral`) a legenda DESCE para baixo do quadro (o quadro vai até
    # ~72% da altura); na tela dividida (`topo`) desce para baixo do seu rosto
    for c in caps:
        mid = (c["a"] + c["b"]) / 2
        for o in overlays:
            if o.get("type") == "media" and "a" in o and o["a"] <= mid < o["b"]:
                if o.get("layout") == "viral":
                    ar = min(1.8, max(0.75, float(o.get("ar") or 1)))
                    c["y"] = round(min(0.86, max(0.80, 0.47 + 0.44 * W / ar / H + 0.05)), 3)
                # telas divididas com ELE embaixo (45/55, TV na sala): a legenda no terço de baixo caía na boca dele, e
                # na divisa parecia "cortada" (reprovado no Joshie e no Epicteto, 18/10) → fica logo ACIMA da divisa,
                # dentro do ativo, na caixinha sépia (legível, longe do rosto). Duo (dois ativos): posição normal
                elif o.get("layout") == "duo":          # dois ativos: no terço de baixo cobria o rosto do 2º (Marco
                    c["y"], c["box"] = 0.44, True      # Aurélio) → logo acima da divisa, na caixinha
                elif o.get("layout") in ("meio", "tv"):
                    ht = float(o.get("ht") or (SPLIT["tv_h"] if o.get("layout") == "tv" else SPLIT["meio_h"]))
                    # `cap_y` no ativo: quando a parte de baixo dele tem texto que importa (nome, manchete), a legenda
                    # vai para o alto da faixa
                    c["y"], c["box"] = round(float(o.get("cap_y") or (ht - 0.06)), 3), True
    gss = [(o["a"], o["b"]) for o in overlays if o.get("type") == "greenscreen" and "a" in o]
    if not gss:
        return
    inside = lambda a, b: any(ga <= (a + b) / 2 < gb for ga, gb in gss)
    for c in caps:
        if inside(c["a"], c["b"]):
            c["y"], c["box"] = 0.47, True
    for ov in overlays:
        L = ov.get("layout") if ov.get("type") == "emphasis" else None
        if not L or not inside(ov["a"], ov["b"]):
            continue
        h = sum(ln["size"] * 0.98 for ln in L["lines"])
        if L.get("per_line"):
            top = min(ln["top"] for ln in L["lines"])
            dy = min(0.0, H * 0.52 - (top + h))
            for ln in L["lines"]:
                ln["top"] = round(ln["top"] + dy)
        else:
            # metade de BAIXO, à direita, ao lado de você (no canto esquerdo): bloco inteiro, alinhado à direita
            wmax = max(_width(ln.get("text") or " ".join(t["w"] for t in ln["words"]), ln["size"]) for ln in L["lines"])
            k = min(1.0, (W * 0.44) / max(1.0, wmax))
            for ln in L["lines"]:
                ln["size"] = round(ln["size"] * k)
            h = sum(ln["size"] * 0.98 for ln in L["lines"])
            L["align"], L["x"] = "right", round(W * 0.95)
            L["y"] = round(H * 0.86 - h / 2)
        # painel sépia por trás do bloco: sobre o print branco a frase de destaque ficava ilegível
        if L.get("per_line"):
            tops = [ln["top"] for ln in L["lines"]]
            y0, y1 = min(tops), max(ln["top"] + ln["size"] for ln in L["lines"])
        else:
            y0 = L["y"] - h / 2
            y1 = L["y"] + h / 2
        wmax = max(_width(ln.get("text") or " ".join(t["w"] for t in ln["words"]), ln["size"]) for ln in L["lines"])
        x0 = (L["x"] - wmax) if L.get("align") == "right" and not L.get("per_line") else L["x"] - wmax / 2
        pad = H * 0.018
        L["panel"] = [round(x0 - pad * 1.4), round(y0 - pad), round(x0 + wmax + pad * 1.4), round(y1 + pad)]


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
    segs = split_at(segs, project.get("splits"), words)
    segs = apply_order(segs, project.get("order"))
    # FIM DO VÍDEO: a última palavra termina de soar depois do "fim" que o Whisper marca (a vogal final e a
    # respiração) — o último trecho ganha ~0,6 s de sobra (antes "trabalho?" saía cortado)
    dset0 = set(deleted)
    kept = [w for w in words if w["i"] not in dset0 and w["w"].strip()]
    if kept and segs:
        lw = kept[-1]
        last = segs[-1]
        if last["start"] - 0.05 <= lw["start"] <= last["end"] + 0.05:
            last["end"] = round(min(duration, max(last["end"], lw["end"] + 0.6)), 3)
    src = project.get("source") or {}
    lowres = max(src.get("width") or 1920, src.get("height") or 1920) < 1280
    pieces = split_pieces(segs, words, overlays_in, {**settings, "_lowres": lowres}, deleted)
    # SINCRONIA: todo corte cai num QUADRO exato do original. Assim cada trecho tem a mesma duração no vídeo
    # (quadros inteiros) e no áudio — antes sobrava/faltava até 1 quadro por trecho e a boca dessincronizava
    # aos poucos ("ora lenta, ora correndo"), até ~0,1 s no fim
    sfps = float(src.get("fps") or 30.0)
    for q in pieces:
        q["start"] = round(round(q["start"] * sfps) / sfps, 6)
        q["end"] = round(max(q["start"] + 1 / sfps, round(q["end"] * sfps) / sfps), 6)
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
        if ov.get("type") == "transition" and ov.get("scene"):
            b = a + 0.5          # troca de CENA (você ↔ B-roll ↔ tvzinha ↔ tela dividida): vale onde a cena muda
        elif ov.get("type") in ("transition", "flash"):
            # transição só vale num corte real (ou no corte do hook) — gruda exatamente nele
            t = words[min(ov["w0"], len(words) - 1)]["start"]
            j = min(joins, key=lambda j: abs(j["t"] - t), default=None)
            if not j or abs(j["t"] - t) > 0.8:
                continue
            a, b = j["out"], j["out"] + 0.5
        if ov.get("min_dur") and b - a < float(ov["min_dur"]):    # ex.: animação que precisa de ~1,8 s
            b = a + float(ov["min_dur"])
        if ov.get("end_w") is not None and 0 <= ov["end_w"] < len(words):   # termina num ponto da fala
            b = to_output(pieces, words[ov["end_w"]]["start"]) + float(ov.get("end_offset", 0))
        ov2 = {**ov, "a": a, "b": min(b, total)}
        # motion sincronizado com a fala: itens com "w" (índice da palavra) ganham "t" (s desde o início)
        if ov.get("type") == "motion" and isinstance(ov.get("params"), dict):
            prm = dict(ov["params"])
            if isinstance(prm.get("items"), list):
                prm["items"] = [({**it, "t": round(max(0.0, to_output(pieces, words[it["w"]]["start"]) - a), 3)}
                                 if isinstance(it, dict) and it.get("w") is not None and 0 <= it["w"] < len(words) else it)
                                for it in prm["items"]]
            if prm.get("final_w") is not None and 0 <= prm["final_w"] < len(words):
                prm["final_t"] = round(max(0.0, to_output(pieces, words[prm["final_w"]]["start"]) - a), 3)
            # rosto medido (`chin`): o bloco de texto do motion começa abaixo do queixo, em TODOS os planos que ele
            # atravessa (num plano fechado o rosto desce — no Joshie "a diária / a cor do quarto" caía na barba)
            if ov.get("chin") is not None and ov.get("template") in ("riscados", "acronimo", "cerebro"):
                t0, t1 = words[ov["w0"]]["start"], words[min(ov["w1"], len(words) - 1)]["end"]
                ps = [q for q in pieces if q["end"] > t0 and q["start"] < t1]
                if ps:
                    cd = max(_display_y(float(ov["chin"]), q, r) for q in ps for r in (0.0, 0.5, 1.0))
                    prm["top"] = round(min(0.74, max(0.58, cd + 0.03)) * 100, 1)
            ov2["params"] = prm
        overlays.append(ov2)
    # TELA VERDE começa/termina EXATAMENTE numa troca de plano (senão, por um instante, você aparece no canto
    # ainda com o zoom do plano anterior: "zoom relâmpago" que parece bug)
    starts = [q["out"] for q in pieces]
    for o in overlays:
        if o.get("type") == "greenscreen" and starts:
            sa = min(starts, key=lambda x: abs(x - o["a"]))
            if abs(sa - o["a"]) <= 0.4:
                o["a"] = round(sa, 3)
            sb = min(starts, key=lambda x: abs(x - o["b"]))
            if abs(sb - o["b"]) <= 0.4 and sb > o["a"] + 1:
                o["b"] = round(sb, 3)
    # SEQUÊNCIA EMENDADA ("chain"): cada B-roll fica até o próximo da sequência começar (troca direta, com clique)
    # REGRA DELE ("broll broll broll, ou dividida dividida dividida, sem me enfiar no meio do nada"): o buraco entre
    # um ativo emendado e o próximo (qualquer um, emendado ou não) é coberto pelo ativo anterior
    media = sorted([o for o in overlays if o.get("type") == "media" and "a" in o], key=lambda o: o["a"])
    for o, nxt in zip(media, media[1:]):
        if o.get("chain") and 0 <= nxt["a"] - o["b"] <= 10:
            o["b"] = nxt["a"]
    # ...e nem 1–3 s sozinho colado numa frase de destaque: o ativo encosta nela (antes ou depois)
    vis = sorted([o for o in overlays if o.get("type") in ("media", "emphasis", "motion") and "a" in o], key=lambda o: o["a"])
    for x, y in zip(vis, vis[1:]):
        if 0 < y["a"] - x["b"] <= 3.6 and ({"emphasis", "motion"} & {x["type"], y["type"]}):
            if x["type"] == "media":
                x["b"] = y["a"]
            elif y["type"] == "media":
                y["a"] = x["b"]
    skip = set()
    for ov in overlays:
        if ov.get("type") == "emphasis" or ov.get("hide_captions"):
            skip.update(range(ov["w0"], ov.get("w1", ov["w0"]) + 1))
    caps = caption_chunks(pieces, segs, words, deleted, skip=frozenset(skip)) if words else []
    # a legenda comum SAI no instante em que entra um destaque/motion de tela cheia (antes as duas ficavam
    # ~0,25 s juntas e se atropelavam — ex.: "projeto viável, a" × "gente precisava de uma dose maior")
    starts = sorted(o["a"] for o in overlays if o.get("type") == "emphasis" or o.get("hide_captions"))
    for c in caps:
        nxt = next((t for t in starts if c["a"] < t < c["b"]), None)
        if nxt is not None:
            c["b"] = round(nxt, 3)
    caps.sort(key=lambda c: c["a"])
    for c, nx in zip(caps, caps[1:]):              # uma legenda nunca fica por cima da seguinte
        if nx["a"] < c["b"]:
            c["b"] = nx["a"]
    caps = [c for c in caps if c["b"] - c["a"] >= 0.12]
    removed = duration - sum(s["end"] - s["start"] for s in segs)
    from .render import output_size  # import tardio (evita ciclo)
    W, H = output_size(project["source"], settings.get("format", "original"))
    n = 0
    for ov in overlays:
        if ov.get("type") == "emphasis":
            ov["layout"] = emphasis_layout(ov, pieces, words, deleted, W, H, n)
            n += 1
            L = ov["layout"]
            if L and ov.get("align") == "right":       # pedido dele: bloco à direita, alinhado à direita
                L["align"], L["x"] = "right", round(W * 0.93)
                for ln in L.get("lines", []):           # variante linha a linha também (antes ficava centralizada)
                    ln["align"], ln["x"] = "right", round(W * 0.93)
    _snap_to_cuts(overlays, pieces)
    _lift_over_greenscreen(overlays, caps, W, H)
    _place_split_person(overlays, pieces)
    return {"segments": pieces, "cuts": segs, "joins": joins, "frame": [W, H], "duration": total, "transition_duration": td,
            "overlays": overlays, "captions": caps, "settings": settings,
            "removed_seconds": round(removed, 2)}

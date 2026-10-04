"""Análise gratuita e local (sem IA): limpeza de regravações e plano de edição
por regras. Serve de base sempre disponível; Ollama/Claude refinam por cima."""
import difflib
import re
import unicodedata

from .timeline import is_filler

# ------------------------------------------------------------------ utilidades


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(w):
    return strip_accents(re.sub(r"[^\w%$]", "", w.lower()))


def kept(words, deleted):
    d = set(deleted)
    return [w for w in words if w["i"] not in d and w["w"].strip()]


def phrases(words, deleted, gap=0.55):
    """Divide a fala (palavras mantidas) em frases por pontuação ou pausa."""
    out, cur = [], []
    prev = None
    for w in kept(words, deleted):
        # reticências ("e...", "do que...") são hesitação, não fim de frase
        end_mark = prev is not None and re.search(r"[.?!]$", prev["w"]) and not re.search(r"(\.\.\.|…)$", prev["w"])
        if cur and (w["start"] - prev["end"] > gap or end_mark):
            out.append(cur)
            cur = []
        cur.append(w)
        prev = w
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------ limpeza

def clean(words, deleted):
    """Encontra regravações, gaguejos e falsos começos. Retorna [{start,end,reason}]."""
    cuts = []
    ks = kept(words, deleted)
    toks = [norm(w["w"]) for w in ks]

    # 1) repetição imediata de 1–4 palavras ("a segunda, a segunda dica", "eu eu eu")
    i = 0
    while i < len(ks):
        hit = False
        for n in (8, 7, 6, 5, 4, 3, 2, 1):
            a, b = toks[i:i + n], toks[i + n:i + 2 * n]
            if len(b) == n and a == b and all(a) and (n > 1 or len(a[0]) > 0):
                # palavra única repetida só conta se for curta/funcional ou colada
                if n == 1 and ks[i + 1]["start"] - ks[i]["end"] > 0.6:
                    break
                cuts.append({"start": ks[i]["i"], "end": ks[i + n - 1]["i"], "reason": "repetição/gaguejo"})
                i += n
                hit = True
                break
        if not hit:
            i += 1

    # 2) regravações: uma frase (ou o fim dela) que é refeita logo depois -> fica só a última versão.
    #    Critérios: mesmo começo (≥ 4 palavras ou ≥ 60% da frase) ou conteúdo quase todo repetido
    #    num trecho das próximas ~40 palavras.
    ph = phrases(words, deleted)
    flat = [w for p in ph for w in p]
    pos = {w["i"]: n for n, w in enumerate(flat)}
    for k, p in enumerate(ph):
        a = [norm(w["w"]) for w in p]
        if len(a) < 3:
            continue
        start = pos[p[-1]["i"]] + 1
        later = [norm(w["w"]) for w in flat[start:start + 40]]
        if len(later) < 3:
            continue
        # começo igual a alguma frase seguinte
        nexts = [[norm(w["w"]) for w in q] for q in ph[k + 1:k + 4]]
        same_start = False
        for b in nexts:
            n = 0
            while n < min(len(a), len(b)) and (a[n] == b[n] or difflib.SequenceMatcher(None, a[n], b[n]).ratio() > 0.8):
                n += 1
            if n >= 4 or (n >= 3 and n >= 0.6 * len(a)):
                same_start = True
                break
        # conteúdo quase todo repetido logo adiante
        sm = difflib.SequenceMatcher(None, a, later, autojunk=False)
        covered = sum(bl.size for bl in sm.get_matching_blocks())
        if same_start or covered >= 0.7 * len(a):
            cuts.append({"start": p[0]["i"], "end": p[-1]["i"], "reason": "regravação: mantida a última versão"})
            continue
        # o fim desta frase é recomeçado na próxima ("olá, hoje eu vou mostrar. / hoje eu vou mostrar três dicas")
        if k + 1 < len(ph):
            b = [norm(w["w"]) for w in ph[k + 1]]
            best = None                               # final de A que reaparece no começo de B (melhor alinhamento)
            for i in range(1, len(a) - 2):
                tail = a[i:]
                if len(b) >= len(tail) * 0.8:
                    r = difflib.SequenceMatcher(None, tail, b[:len(tail)]).ratio()
                    if r >= 0.8 and (best is None or r > best[0] + 0.02):
                        best = (r, i)
            if best:
                cuts.append({"start": p[best[1]]["i"], "end": p[-1]["i"], "reason": "regravação: frase recomeçada"})

    # 2b) voz de fundo: outra pessoa falando longe do microfone (soprando o texto, comentando).
    #     Só corta com segurança: a frase é bem mais baixa que a voz principal E é repetida logo
    #     depois pela voz principal — ou é MUITO mais baixa (15 dB). Assim um "Esse vídeo é"
    #     falado mais baixinho pela própria pessoa não some.
    levels = sorted(w["db"] for w in kept(words, deleted) if w.get("db", -99) > -90)
    main = levels[int(len(levels) * 0.75)] if len(levels) >= 8 else None
    if main is not None:
        for k, p in enumerate(ph):
            pl = sorted(w.get("db", -99) for w in p)
            lvl = pl[int(len(pl) * 0.8)] if pl else -99
            if lvl > main - 9:
                continue
            a = [norm(w["w"]) for w in p]
            later = [w for q in ph[k + 1:k + 6] for w in q if w.get("db", -99) > main - 9][:60]
            sm = difflib.SequenceMatcher(None, a, [norm(w["w"]) for w in later], autojunk=False)
            repeated = len(a) >= 2 and sum(b.size for b in sm.get_matching_blocks()) >= 0.6 * len(a)
            if repeated or lvl < main - 15:
                cuts.append({"start": p[0]["i"], "end": p[-1]["i"], "reason": "voz de fundo (outra pessoa)"})

    # 2c) palavrinha solta entre pausas ("Ou", "E", "Que") — resto de uma frase abandonada
    for p in ph:
        if len(p) <= 2 and all(norm(w["w"]) in STOP for w in p):
            cuts.append({"start": p[0]["i"], "end": p[-1]["i"], "reason": "palavra solta (frase abandonada)"})

    # 3) falas de bastidor
    backstage = [r"\bcorta\b", r"\bvou de novo\b", r"\bde novo\b.*\bvou\b", r"\bdeixa eu (repetir|comecar)\b",
                 r"\bta gravando\b", r"\bgravando\b.*\?", r"\bvamos de novo\b", r"\berrei\b",
                 r"^pode (ir|comecar|gravar)\b", r"^(ja|foi|comecou|valendo)\?*$", r"^(gravando|valendo)\b",
                 r"^(amem|tchau,? tchau)\.?$"]
    for p in ph:
        txt = strip_accents(" ".join(w["w"] for w in p).lower())
        if len(p) <= 10 and any(re.search(r, txt) for r in backstage):
            cuts.append({"start": p[0]["i"], "end": p[-1]["i"], "reason": "fala de bastidor"})

    # 4) muletas de fala: expressões que não acrescentam nada ao vídeo final
    muletas = [r"(o que|como) (e que )?eu (posso|poderia|vou) (te )?dizer", r"deixa eu (ver|pensar|lembrar)",
               r"digamos assim", r"sei la", r"tipo assim", r"como (e que )?(se )?diz", r"como e que fala",
               r"enfim", r"entendeu\?", r"sabe\?", r"ne\?", r"vamos la", r"e (e|eh)+\b", r"assim,? ne"]
    toks = [strip_accents(re.sub(r"[^\w?]", "", w["w"].lower())) for w in ks]
    text = " ".join(toks)
    for rx in muletas:
        for m in re.finditer(r"(?:^|\s)(" + rx + r"\??)(?=\s|$)", text):
            a = text[:m.start(1)].count(" ")
            b = a + m.group(1).count(" ")
            cuts.append({"start": ks[a]["i"], "end": ks[min(b, len(ks) - 1)]["i"], "reason": "muleta de fala"})

    # 5) hesitações
    for w in ks:
        if is_filler(w["w"]):
            cuts.append({"start": w["i"], "end": w["i"], "reason": "hesitação"})
    return cuts


# ------------------------------------------------------------------ análise do roteiro

STOP = set("""a o as os um uma uns umas de do da dos das no na nos nas em por para pra pro com sem
que e ou mas se nao não sim eu voce você ele ela nos nós eles elas isso isto aquilo esse essa este esta
meu minha seu sua é ser foi era vai vou tem ter tá ta estar está muito mais menos já ja também tambem
como quando onde porque porquê então entao aí ai lá la aqui assim tipo né ne coisa coisas gente pessoal
ao à às aos pelo pela pelos pelas me te lhe se só so bem bom boa até ate sobre entre hoje agora
""".split())

ORDINAL = {"primeir": 1, "segund": 2, "terceir": 3, "quart": 4, "quint": 5, "sext": 6, "setim": 7,
           "oitav": 8, "non": 9, "decim": 10}
LIST_NOUNS = r"(dica|passo|erro|motivo|razao|regra|ponto|forma|maneira|jeito|licao|segredo|pilar|etapa|sinal|habito|coisa|ferramenta|estrategia)s?"
EMPHASIS = ["nunca", "sempre", "segredo", "importante", "atencao", "cuidado", "verdade", "ninguem", "absurdo",
            "incrivel", "pior", "melhor", "erro", "problema", "resultado", "simples", "facil", "dificil",
            "milhao", "milhoes", "bilhao", "bilhoes", "dobro", "metade", "zero", "proibido", "perigoso", "mentira"]
NUMBER_WORDS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
                "oito": 8, "nove": 9, "dez": 10, "cem": 100, "mil": 1000}


def _phrase_text(p):
    return " ".join(w["w"] for w in p)


def _entities(p):
    """Sequências de palavras com inicial maiúscula fora do começo da frase (nomes próprios)."""
    out, cur = [], []
    for k, w in enumerate(p):
        raw = re.sub(r"[^\wÀ-ÿ]", "", w["w"])
        is_cap = raw[:1].isupper() and k > 0 and raw.lower() not in STOP and len(raw) > 1
        if is_cap or (cur and raw.lower() in ("de", "da", "do", "dos", "das") and k + 1 < len(p)
                      and re.sub(r"[^\wÀ-ÿ]", "", p[k + 1]["w"])[:1].isupper()):
            cur.append(w)
        else:
            if cur and re.sub(r"[^\wÀ-ÿ]", "", cur[-1]["w"])[:1].isupper():
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _keywords(p, n=3):
    toks = [re.sub(r"[^\wÀ-ÿ]", "", w["w"]) for w in p]
    toks = [t for t in toks if t and t.lower() not in STOP and len(t) > 3]
    toks.sort(key=len, reverse=True)
    return toks[:n]


UNITS = {"mil", "milhao", "milhoes", "bilhao", "bilhoes", "trilhao", "trilhoes", "reais", "real", "dolares",
         "dolar", "euros", "%", "porcento", "anos", "dias", "horas", "minutos", "vezes", "pessoas", "seguidores",
         "clientes", "vendas", "kg", "km"}
CURRENCY = {"reais": "R$ ", "real": "R$ ", "dolares": "US$ ", "dolar": "US$ ", "euros": "€ "}
SPOKEN_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
              "oito": 8, "nove": 9, "dez": 10, "vinte": 20, "trinta": 30, "cinquenta": 50, "cem": 100}
BIG = {"text_keyword", "media", "broll", "motion", "behind", "emphasis"}   # elementos que ocupam o centro da tela


def _clean(w):
    return w.strip(",.;:!?…\"'")


def _number_at(p, j):
    """Se a palavra j inicia um número com unidade ("25 bilhões de dólares"), devolve o trecho."""
    w = norm(p[j]["w"])
    digits = re.sub(r"[^\d]", "", p[j]["w"])
    nxt = [norm(x["w"]) for x in p[j + 1:j + 4]]
    if not digits and not (w in SPOKEN_NUM and nxt and nxt[0] in UNITS):
        return None
    k = j + 1
    while k < len(p) and k - j <= 4 and (norm(p[k]["w"]) in UNITS or
                                          (norm(p[k]["w"]) == "de" and k + 1 < len(p) and norm(p[k + 1]["w"]) in UNITS)):
        k += 1
    if k == j + 1 and not ("%" in p[j]["w"] or len(digits) >= 2):
        return None
    seg = p[j:k]
    toks = [norm(x["w"]) for x in seg]
    value = int(digits) if digits else SPOKEN_NUM.get(w, 0)
    cur = next((CURRENCY[t] for t in toks if t in CURRENCY), "")
    scale = next((t for t in toks if t in ("mil", "milhao", "milhoes", "bilhao", "bilhoes", "trilhao", "trilhoes")), "")
    suffix = {"mil": " mil", "milhao": " milhão", "milhoes": " milhões", "bilhao": " bilhão", "bilhoes": " bilhões",
              "trilhao": " trilhão", "trilhoes": " trilhões"}.get(scale, "")
    if "%" in p[j]["w"] or "porcento" in toks:
        suffix = "%"
    return seg, value, cur, suffix


def analyze(words, deleted, duration, formato=None):
    """Gera {analysis, items} — o mesmo formato que a IA devolve.
    `formato` (de vídeos de referência) ajusta a densidade de inserções."""
    ph = phrases(words, deleted, gap=0.8)
    allk = kept(words, deleted)
    density = ((formato or {}).get("metrics", {}).get("visual_interval") or 8.0) / 8.0
    density = max(0.4, min(2.5, density))
    items = []
    last_at = {}

    def can(kind, t, spacing):
        if t - last_at.get(kind, -999) < spacing * density:
            return False
        last_at[kind] = t
        return True

    def add(kind, p0, p1, prio, **kw):
        items.append({"kind": kind, "start": p0["i"], "end": p1["i"], "_t0": p0["start"], "_t1": p1["end"],
                      "_prio": prio, **kw})

    # ---- seções e listas ("a primeira razão…", "o segundo erro…")
    sections, list_items, cur = [], [], None
    for k, p in enumerate(ph):
        ntxt = strip_accents(_phrase_text(p).lower())
        m = re.search(r"\b(" + "|".join(ORDINAL) + r")[oa]s?\b\s+(\w+\s+)?" + LIST_NOUNS, ntxt)
        long_gap = k > 0 and p[0]["start"] - ph[k - 1][-1]["end"] > 1.6
        if m:
            n = next(v for key, v in ORDINAL.items() if m.group(1).startswith(key))
            noun_n = re.search(LIST_NOUNS, m.group(0)).group(1)
            ni = next((j for j, w in enumerate(p) if norm(w["w"]).startswith(noun_n)), 1)
            noun = _clean(p[ni]["w"]).upper()
            raw = [w["w"] for w in p[ni + 1:]]
            while raw and norm(raw[0]) in ("e", "eh", "é", "ser", "sera", "seria", "que", "a", "o", "eu", "acho"):
                raw.pop(0)
            clause = []
            for w in raw[:4]:   # até a primeira pontuação
                clause.append(_clean(w))
                if re.search(r"[,.;:!?…]$", w):
                    break
            label = " ".join(clause)
            list_items.append({"k": k, "n": n, "noun": noun, "label": label})
        if cur is None or m or long_gap:
            cur = {"title": (f"{list_items[-1]['noun']} {list_items[-1]['n']}: {list_items[-1]['label']}" if m
                             else " ".join(_clean(w["w"]) for w in p[:6])), "start": p[0]["i"], "end": p[-1]["i"]}
            sections.append(cur)
        else:
            cur["end"] = p[-1]["i"]
    list_k = {li["k"]: li for li in list_items}

    for k, p in enumerate(ph):
        txt = _phrase_text(p)
        ntxt = strip_accents(txt.lower())

        # gancho: pergunta ou frase curta de abertura vira título
        if False and k == 0 and 3 <= len(p) <= 14:
            add("text", p[0], p[-1], 2, style="title", text=" ".join(_clean(w["w"]) for w in p[:7]) + ("…" if len(p) > 7 else ""),
                reason="gancho de abertura")
            add("sfx", p[0], p[0], 0, sfx="swish", reason="entrada do título")
            add("zoom", p[max(0, len(p) - 4)], p[-1], 0, reason="ênfase no gancho")

        # anúncio de lista ("três razões", "3 dicas") -> motion de lista com os itens que vêm depois
        m = re.search(r"\b(\d+|" + "|".join(SPOKEN_NUM) + r")\s+(\w+\s+)?" + LIST_NOUNS, ntxt)
        if m and len(list_items) >= 2 and list_items[0]["k"] > k:
            add("motion", p[0], p[-1], 5, template="lista",
                params={"title": m.group(0).upper(), "items": [li["label"] for li in list_items[:5]]},
                reason="anúncio de lista")

        # item de lista -> título + ding + flash + whoosh
        li = list_k.get(k)
        if li:
            add("text", p[0], p[-1], 2, style="title", text=f"{li['noun']} #{li['n']}: {li['label']}", reason="item de lista")
            add("sfx", p[0], p[0], 0, sfx="ding_balcao", reason="item de lista")
            add("transition", p[0], p[0], 0, transition="flash", reason="novo tópico")

        # números -> contador (dinheiro/escala) ou palavra-chave grande
        for j in range(len(p)):
            got = _number_at(p, j)
            if not got:
                continue
            seg, value, cur_, suffix = got
            if not can("number", seg[0]["start"], 5):
                break
            if (cur_ or suffix) and value:
                add("motion", seg[0], p[min(len(p) - 1, j + len(seg) + 2)], 6, template="contador",
                    params={"value": value, "prefix": cur_, "suffix": suffix,
                            "label": " ".join(_clean(w["w"]) for w in p[j + len(seg):j + len(seg) + 3])},
                    reason="número/dado")
            else:
                j0 = max(0, j - 3)
                add("emphasis", p[j0], p[min(len(p) - 1, j + len(seg) + 1)], 4.5, text=_clean(seg[-1]["w"]),
                    reason="número/dado")
            add("sfx", seg[0], seg[0], 0, sfx="kaching" if cur_ else "pop_seco", reason="número")
            break

        # ênfase -> zoom (+ impacto às vezes)
        for j, w in enumerate(p):
            if norm(w["w"]) in EMPHASIS and can("zoom", w["start"], 6):
                add("zoom", p[max(0, j - 2)], p[min(len(p) - 1, j + 3)], 0, reason=f"ênfase em '{_clean(w['w'])}'")
                if can("impacto", w["start"], 15):
                    add("sfx", w, w, 0, sfx="boom_grave", reason="frase forte")
                break

        # pergunta -> zoom
        if txt.strip().endswith("?") and k > 0 and can("zoom", p[0]["start"], 5):
            add("zoom", p[max(0, len(p) - 4)], p[-1], 0, reason="pergunta")

        # nomes próprios -> foto real (Wikipedia)
        for ent in _entities(p):
            # "a SpaceX do Elon Musk" -> prefere o nome composto depois do conector
            parts, curp = [], []
            for w in ent:
                if norm(w["w"]) in ("de", "da", "do", "dos", "das"):
                    parts.append(curp)
                    curp = []
                else:
                    curp.append(w)
            parts.append(curp)
            best = max((x for x in parts if x), key=len)
            ent = best if len(parts) > 1 and len(best) >= 2 else ent
            name = " ".join(re.sub(r"[^\wÀ-ÿ\-]", "", w["w"]) for w in ent if norm(w["w"]) not in ("de", "da", "do", "dos", "das"))
            if len(name) > 2 and can("broll", ent[0]["start"], 4):
                gi = next(n for n, x in enumerate(allk) if x["i"] == ent[0]["i"])
                end = allk[min(len(allk) - 1, gi + len(ent) + 6)]
                link = f"b{ent[0]['i']}"
                add("broll", ent[0], end, 3, text=f"Imagem real de {name}", query=name, source="wikipedia",
                    layout="card", reason=f"menção a '{name}'", _id=link)
                add("sfx", ent[0], ent[0], 0, sfx="camera", reason="foto aparecendo", _link=link)
                break

    # frases de destaque (~10–15% do vídeo): superlativos, ênfases, frases curtas de efeito
    SUPER = {"maior", "menor", "melhor", "pior", "nunca", "sempre", "ninguem", "tudo",
             "unico", "unica", "segredo", "verdade", "simples", "impossivel", "incrivel", "absurdo", "historia"}
    speech = sum(w["end"] - w["start"] for w in allk) or 1
    budget = speech * 0.14
    cands = []
    for k, p in enumerate(ph):
        if k in list_k or len(p) < 3:
            continue
        toks = [norm(w["w"]) for w in p]
        score = 3 * sum(t in SUPER or t in EMPHASIS for t in toks) + (1 if 3 <= len(p) <= 8 else 0)
        score += 2 if re.search(r"[!.]$", p[-1]["w"]) and len(p) <= 8 else 0
        score += 1 if k == 0 else 0
        if score < 3:
            continue
        hits = [j for j, t in enumerate(toks) if t in SUPER or t in EMPHASIS]
        anchor = hits[-1] if hits else len(p) - 1
        # termina na pontuação depois da palavra forte (no máx. 3 palavras depois)
        j1 = anchor
        while j1 < min(len(p) - 1, anchor + 3) and not re.search(r"[,.;:!?…]$", p[j1]["w"]):
            j1 += 1
        if len(p) <= 8:
            j1 = len(p) - 1
        j0 = max(0, anchor - 5, min(anchor, j1 - 7))
        # começa depois de uma vírgula, se houver
        for jj in range(anchor - 1, j0 - 1, -1):
            if re.search(r"[,;:]$", p[jj]["w"]):
                j0 = jj + 1
                break
        seg = p[j0:j1 + 1]
        content = [w for w in seg if norm(w["w"]) not in STOP]
        key = max(content, key=lambda w: (norm(w["w"]) in SUPER or norm(w["w"]) in EMPHASIS, len(w["w"])))["w"] if content else seg[-1]["w"]
        cands.append((score, seg, _clean(key)))
    # GANCHO: os primeiros segundos quase sempre ganham tipografia de destaque (1–2 blocos)
    hook = [w for p in ph[:2] for w in p if w["start"] - (ph[0][0]["start"] if ph else 0) < 7.0][:16]
    if len(hook) >= 3:
        blocks = [hook] if len(hook) <= 8 else []
        if not blocks:   # divide em dois blocos, de preferência numa vírgula/ponto
            cut_at = next((j + 1 for j in range(3, len(hook) - 3) if re.search(r"[,.;:!?]$", hook[j]["w"])), len(hook) // 2)
            blocks = [hook[:cut_at], hook[cut_at:]]
        for blk in blocks:
            blk = blk[:9]
            content = [w for w in blk if norm(w["w"]) not in STOP]
            key = max(content, key=lambda w: (norm(w["w"]) in SUPER or norm(w["w"]) in EMPHASIS, len(w["w"])))["w"] \
                if content else blk[-1]["w"]
            add("emphasis", blk[0], blk[-1], 5.0, text=_clean(key), reason="gancho")
    used = 0.0
    for score, seg, key in sorted(cands, key=lambda c: -c[0]):
        dur = seg[-1]["end"] - seg[0]["start"]
        if used + dur > budget:
            continue
        if not can("emphasis_" + str(round(seg[0]["start"])), seg[0]["start"], 0):
            continue
        add("emphasis", seg[0], seg[-1], 4.6, text=key, reason="frase de destaque")
        used += dur

    # nova seção -> whoosh (se ainda não houver som ali)
    for s in sections[1:]:
        add("sfx", words[s["start"]], words[s["start"]], 0, sfx="whoosh_rapido", reason="nova seção")

    # B-roll de arquivo para manter o ritmo onde não há nada visual por muito tempo
    def visual_near(t, gap):
        return any(it["kind"] in ("broll", "motion", "text") and it["_t0"] - gap < t < it["_t1"] + gap for it in items)
    for p in ph:
        if len(p) >= 6 and not visual_near(p[0]["start"], 6 * density) and can("broll_kw", p[0]["start"], 14):
            kw = _keywords(p, 2)
            if kw:
                add("broll", p[0], p[min(len(p) - 1, 10)], 1, text="Material de apoio: " + " ".join(kw),
                    query=" ".join(kw), source="commons", layout="full", reason="manter ritmo visual")

    items = _resolve(items)
    all_kept = kept(words, deleted)
    summary = " ".join(w["w"] for w in all_kept[:40]) + ("…" if len(all_kept) > 40 else "")
    return {
        "analysis": {"summary": summary, "hook": _phrase_text(ph[0]) if ph else "",
                     "sections": sections, "key_points": [s["title"] for s in sections[:8]], "engine": "regras"},
        "items": items,
    }


def _resolve(items):
    """Evita poluição: um elemento grande por vez (o de maior prioridade vence),
    um efeito sonoro por momento e nada de zoom duplicado."""
    def kind_key(it):
        if it["kind"] == "text":
            return "text_" + it.get("style", "title")
        return it["kind"]
    big = sorted([it for it in items if kind_key(it) in BIG], key=lambda it: -it["_prio"])
    kept_big = []
    for it in big:
        if all(it["_t1"] <= o["_t0"] or it["_t0"] >= o["_t1"] for o in kept_big):
            kept_big.append(it)
    titles = sorted([it for it in items if kind_key(it) in ("text_title", "text_lower")], key=lambda it: -it["_prio"])
    kept_titles = []
    for it in titles:
        if all(it["_t1"] <= o["_t0"] or it["_t0"] >= o["_t1"] for o in kept_titles):
            kept_titles.append(it)
    # sons com sobriedade (como fazem editores de Reels): pop quando entra uma frase de destaque,
    # sons de conteúdo (ding, ka-ching, boom, câmera) onde algo acontece, e whoosh só em troca de
    # assunto — no máximo um som a cada ~2,5 s e um whoosh a cada ~8 s.
    pops = ["swoosh_sweep", "pop_bolha"]
    cand, booms = [], 0
    for i in sorted([i for i in items if i["kind"] == "sfx" and i.get("reason") != "nova seção"], key=lambda i: i["_t0"]):
        if i.get("sfx") == "boom_grave":
            booms += 1
            if booms > 1:      # no máximo um "boom" por vídeo
                continue
        cand.append(dict(i, _sp=2))
    for n, e in enumerate(sorted([i for i in kept_big if i["kind"] == "emphasis"], key=lambda i: i["_t0"])):
        cand.append({"kind": "sfx", "start": e["start"], "end": e["start"], "_t0": e["_t0"], "_t1": e["_t0"],
                     "_prio": 0, "_sp": 1.5, "sfx": pops[n % 2], "reason": "frase de destaque entrando"})
    sfx = []
    for it in sorted(cand, key=lambda i: -i["_sp"]):
        gap = 8.0 if it["_sp"] < 1 else 2.5
        if all(abs(it["_t0"] - o["_t0"]) >= (8.0 if (it["_sp"] < 1 or o["_sp"] < 1) else gap) for o in sfx):
            sfx.append(it)
    zooms = []
    for it in sorted([i for i in items if i["kind"] == "zoom"], key=lambda i: i["_t0"]):
        if not zooms or it["_t0"] > zooms[-1]["_t1"] + 1:
            zooms.append(it)
    alive = {i.get("_id") for i in kept_big}
    sfx = [i for i in sfx if not i.get("_link") or i["_link"] in alive]
    flashes = [i for i in items if i["kind"] == "transition"]
    out = kept_big + kept_titles + sfx + zooms + flashes
    out.sort(key=lambda i: i["_t0"])
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in out]

"""NÚMERO GIGANTE ATRÁS DELE (referência que ele mandou: instagram.com/p/Deu3Na-j-fn — o "1", "2", "3" enormes atrás
da pessoa, entrando deslizando da esquerda com rastro de movimento).

O número vira uma IMAGEM (PNG transparente do tamanho do vídeo, com o texto já na posição final) — a mesma imagem
entra no render (entre o fundo e o recorte dele) e na prévia (embaixo do recorte, com a mesma animação), então
prévia = exportação. Overlay: {"type": "behind", "big": true, "text": "50", "sup": "mil", "file": "<png em assets>"}.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "fonts" / "MontserratAlternates-ExtraBold.ttf"
# V015 02/11 ("uma tipografia mais alta, mesmo que estreita na largura"; o "m" da Alternates tinha pernas estranhas):
# `font: "anton"` = Anton (Google Fonts, OFL), condensada e alta
FONTS = {"anton": ROOT / "fonts" / "Anton-Regular.ttf"}
CREME = (245, 239, 230, 255)
TOP = 0.085          # topo dos algarismos: logo abaixo da barra do Reels (8%, regra dele)
CAP = 0.235          # altura dos algarismos (fração da altura do vídeo): a parte de baixo some atrás da cabeça
SUP = 0.36           # "mil" pequeno, alinhado no TOPO dos algarismos (50ᵐⁱˡ) — fica visível acima da cabeça
MAXW = 0.86          # nunca encosta nas bordas
# animação (a MESMA conta no render e na prévia): entra da esquerda desacelerando e SAI pela direita acelerando
# (empurrado pelo próximo número, quando ele vem logo em seguida: "5 mil" → "50 mil"), com desfoque de movimento
# HORIZONTAL em 3 fases (o rastro de cópias do tmix ficava "escadinha"); num corte, sai seco
SLIDE_S, SLIDE_DX, FADE_IN = 0.38, 0.55, 0.12
OUT_S, OUT_DX = 0.30, 0.60
UP_DY, UP_DYO = 0.34, 0.38   # `enter: "up"`: sobe de 34% da altura abaixo e sai 38% para cima
PUSH = 0.08          # o número sai até 0,08 s depois de o próximo começar a entrar (com 0,2 s os dois se misturavam: "05 mi")
VERSION = "v2"
# sigma do desfoque (px num vídeo de 1080 de largura) em cada terço da entrada e da saída (~ obturador de 1/60 s)
BLUR_IN = (17, 10, 3.5)
BLUR_OUT = (5, 14, 24)


def blur_phases(a, b, cut_end=False):
    """[(t0, t1, sigma)] do desfoque de movimento — o render usa como 'enable' do gblur e a prévia usa igual."""
    ph = [(a + SLIDE_S * k / 3, a + SLIDE_S * (k + 1) / 3, BLUR_IN[k]) for k in range(3)]
    if not cut_end:
        e = b - OUT_S
        ph += [(e + OUT_S * k / 3, e + OUT_S * (k + 1) / 3, BLUR_OUT[k]) for k in range(3)]
    return ph


_CUR = {"f": FONT}


def _font(px):
    return ImageFont.truetype(str(_CUR["f"]), max(8, int(px)))


LAYOUT_KEYS = ("cap", "top", "under", "under_cap", "under_w", "under_spread", "under_top", "font", "maxw", "color", "under_color")


def make_png(out, text, sup="", W=1080, H=1920, cap=None, top=None, under="", under_cap=None, under_w=0.94,
             under_spread=False, under_top=None, font=None, maxw=None, color=None, under_color=None):
    """Desenha o número (e o "mil" pequeno) num PNG transparente W×H, centralizado na horizontal.
    `cap`/`top` = altura e topo dos algarismos (fração da altura do vídeo). `under` = palavra EMBAIXO do número, em
    MAIÚSCULAS e larga (V011 02/11: "o 5 em cima e o MIL maiúsculo abaixo, pegando ombro e costas"): ocupa `under_w`
    da largura (ou `under_cap` de altura) e passa por trás da cabeça e dos ombros dele. `under_spread` = letras
    espalhadas de ponta a ponta (a 1ª encostada à esquerda, a última à direita): com a cabeça dele no meio, o M e o L
    ficam INTEIROS dos dois lados (juntas, o M virava um "n" comido pela cabeça)."""
    text, sup, under = str(text).strip(), str(sup or "").strip(), str(under or "").strip().upper()
    # cor (V011 02/11: "o 5 poderia estar no tom de Kronos e não branco"): "#E0BB6A" = dourado Kronos; padrão creme
    rgb = lambda c, d: (tuple(int(str(c).lstrip("#")[k:k + 2], 16) for k in (0, 2, 4)) + (255,)) if c else d
    INK, UINK = rgb(color, CREME), rgb(under_color or color, CREME)
    _CUR["f"] = FONTS.get(str(font or "").lower(), FONT)
    if not _CUR["f"].exists():                     # fonte extra ainda não baixada (fonts/ fica fora do git)
        from . import fonts as _fonts
        _fonts.ensure()
        if not _CUR["f"].exists():
            _CUR["f"] = FONT
    MW = float(maxw or MAXW)
    cap = float(cap or CAP)
    top = TOP if top is None else float(top)
    probe = _font(1000)
    b = probe.getbbox("0")                        # caixa de um ALGARISMO em em=1000 (símbolos como + e − usam a mesma
    cap_k = (b[3] - b[1]) / 1000                  # escala: o − sozinho virava um tijolo da altura de um número)
    em = cap * H / cap_k
    sym = not any(ch.isalnum() for ch in text)    # só símbolo: centraliza na altura dos algarismos
    while True:
        f = _font(em)
        tb = f.getbbox(text)
        fs = _font(em * SUP) if sup else None
        sb = fs.getbbox(sup) if sup else (0, 0, 0, 0)
        gap = 0.035 * W if sup else 0
        total = (tb[2] - tb[0]) + (gap + sb[2] - sb[0] if sup else 0)
        if total <= MW * W or em < 50:
            break
        em *= 0.95
    img = Image.new("RGBA", (W, H), INK[:3] + (0,))        # transparente da MESMA cor: o desfoque não escurece a borda
    d = ImageDraw.Draw(img)
    x0 = (W - total) / 2 - tb[0]
    y0 = top * H - tb[1]
    if sym:                                       # o + e o − no meio da altura em que estaria um número
        db = f.getbbox("0")
        y0 = top * H - db[1] + ((db[3] - db[1]) - (tb[3] - tb[1])) / 2 - (tb[1] - db[1])
    d.text((x0, y0), text, font=f, fill=INK)
    if sup:
        sx = x0 + tb[2] + gap - sb[0]
        sy = top * H - sb[1]                       # topo do "mil" = topo dos algarismos
        d.text((sx, sy), sup, font=fs, fill=INK)
    if under:
        lb = probe.getbbox("M")
        uk = (lb[3] - lb[1]) / 1000                # altura das MAIÚSCULAS em em=1000
        ue = (float(under_cap) * H / uk) if under_cap else 1000.0
        fu = _font(ue)
        ub = fu.getbbox(under)
        if not under_cap or (ub[2] - ub[0]) > under_w * W:     # cabe na largura pedida
            ue *= under_w * W / (ub[2] - ub[0])
            fu = _font(ue)
            ub = fu.getbbox(under)
        uy = top * H + (tb[3] - tb[1] if not sym else cap * H) + 0.022 * H
        if under_top is not None:                 # topo da palavra de baixo (fração da altura): na altura do pescoço
            uy = float(under_top) * H             # (mais estreito que a cabeça — o M e o L não são "mordidos")
        if under_spread and len(under) > 1:
            ws = [fu.getbbox(ch) for ch in under]
            left, right = (W - under_w * W) / 2, (W + under_w * W) / 2
            first, last = ws[0][2] - ws[0][0], ws[-1][2] - ws[-1][0]
            c0, c1 = left + first / 2, right - last / 2           # centros da 1ª e da última letra
            for k, (ch, bb) in enumerate(zip(under, ws)):
                cx = c0 + (c1 - c0) * k / (len(under) - 1)
                d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], uy - ub[1]), ch, font=fu, fill=UINK)
        else:
            d.text(((W - (ub[2] - ub[0])) / 2 - ub[0], uy - ub[1]), under, font=fu, fill=UINK)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return Path(out).name


def png_name(text, sup="", **lay):
    import hashlib
    extra = "".join(f"|{k}={lay[k]}" for k in LAYOUT_KEYS if lay.get(k) not in (None, ""))
    h = hashlib.sha1(f"{text}|{sup}|{TOP}|{CAP}|{SUP}|{VERSION}{extra}".encode()).hexdigest()[:8]
    return f"numero_atras_{h}.png"

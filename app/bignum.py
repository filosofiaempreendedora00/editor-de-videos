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


def _font(px):
    return ImageFont.truetype(str(FONT), max(8, int(px)))


def make_png(out, text, sup="", W=1080, H=1920):
    """Desenha o número (e o "mil" pequeno) num PNG transparente W×H, centralizado na horizontal."""
    text, sup = str(text).strip(), str(sup or "").strip()
    probe = _font(1000)
    b = probe.getbbox("0")                        # caixa de um ALGARISMO em em=1000 (símbolos como + e − usam a mesma
    cap_k = (b[3] - b[1]) / 1000                  # escala: o − sozinho virava um tijolo da altura de um número)
    em = CAP * H / cap_k
    sym = not any(ch.isalnum() for ch in text)    # só símbolo: centraliza na altura dos algarismos
    while True:
        f = _font(em)
        tb = f.getbbox(text)
        fs = _font(em * SUP) if sup else None
        sb = fs.getbbox(sup) if sup else (0, 0, 0, 0)
        gap = 0.035 * W if sup else 0
        total = (tb[2] - tb[0]) + (gap + sb[2] - sb[0] if sup else 0)
        if total <= MAXW * W or em < 50:
            break
        em *= 0.95
    img = Image.new("RGBA", (W, H), CREME[:3] + (0,))      # transparente CREME: o desfoque não escurece a borda
    d = ImageDraw.Draw(img)
    x0 = (W - total) / 2 - tb[0]
    y0 = TOP * H - tb[1]
    if sym:                                       # o + e o − no meio da altura em que estaria um número
        db = f.getbbox("0")
        y0 = TOP * H - db[1] + ((db[3] - db[1]) - (tb[3] - tb[1])) / 2 - (tb[1] - db[1])
    d.text((x0, y0), text, font=f, fill=CREME)
    if sup:
        sx = x0 + tb[2] + gap - sb[0]
        sy = TOP * H - sb[1]                       # topo do "mil" = topo dos algarismos
        d.text((sx, sy), sup, font=fs, fill=CREME)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return Path(out).name


def png_name(text, sup=""):
    import hashlib
    h = hashlib.sha1(f"{text}|{sup}|{TOP}|{CAP}|{SUP}|{VERSION}".encode()).hexdigest()[:8]
    return f"numero_atras_{h}.png"

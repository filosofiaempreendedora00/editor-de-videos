"""PRINTS QUE SOMAM (hook): dois prints de WhatsApp entram um de cada vez com clique, flutuando, a câmera
aproxima nas REAÇÕES de cada um e aparece a soma ("16 + 22 = 38").

`prepare` faz o trabalho chato sozinho (OCR local, Apple Vision):
- borra o VALOR em R$ de cada print (ninguém vê o preço) → cópia "<nome>_blur.jpg" em assets/;
- acha a pílula de reações (o número no rodapé, ex.: "16") e a região dela para o zoom;
- monta o motion `prints_soma` ancorado nas palavras + um clique por print.
"""
import re
import shutil
from pathlib import Path

from PIL import Image, ImageFilter

from . import ocr


# o que nunca pode aparecer num print: valor em R$, marca/@/link do cliente e nomes de pessoas do grupo
HIDE = [r"R\$\s*[\d.,]+", r"Instituto\s+Viriatum", r"\S*viriatum\S*", r"^Alice .*"]


def hide(src, dst, patterns=HIDE):
    """Borra (pixeliza + desfoca) os trechos do print que casam com `patterns` (OCR local). Devolve quantos."""
    im = Image.open(src).convert("RGB")
    hidden = 0
    for ln in ocr.read(src):
        for pat in patterns:
            for m in re.finditer(pat, ln["text"], re.I):
                x0, y0, x1, y1 = ocr.word_box(ln, m.start(), m.end())
                pad = (y1 - y0) * 0.45
                extra = pad * 2.2 if m.group(0).startswith("R$") else pad    # R$: leva junto o emoji de dinheiro
                box = tuple(int(v) for v in (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + extra), min(im.height, y1 + pad)))
                region = im.crop(box)
                small = region.resize((max(1, region.width // 14), max(1, region.height // 14)), Image.BILINEAR)
                region = small.resize(region.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius=(y1 - y0) * 0.35))
                im.paste(region, box[:2])
                hidden += 1
    im.save(dst, quality=95)
    return hidden


_blur_money = hide


def _reactions(path):
    """(número, região [x0,y0,x1,y1] em frações) da pílula de reações no rodapé do print."""
    im = Image.open(path).convert("RGB")
    W, H = im.size
    best = None
    for ln in ocr.read(path):
        x0, y0, x1, y1 = ln["box"]
        m = re.search(r"(\d+)\s*$", ln["text"].strip())
        if not m or y0 < H * 0.8:
            continue
        if best is None or y0 > best[1][1]:
            nx0, ny0, nx1, ny1 = ocr.word_box(ln, m.start(1), m.end(1))
            best = (int(m.group(1)), (nx0, ny0, nx1, ny1))
    if not best:
        return None, [0.55, 0.92, 0.95, 0.995]
    n, (x0, y0, x1, y1) = best
    cy, h = int((y0 + y1) / 2), int(y1 - y0)
    g = im.convert("L").load()

    def white_col(x):           # a pílula é branca: há branco na coluna (entre os emojis também)
        return any(g[x, y] > 238 for y in range(max(0, cy - int(h * .8)), min(H, cy + int(h * .8)), 2))

    left, miss = int(x0) - 2, 0
    while left > 0 and miss < int(h * 0.6):
        miss = 0 if white_col(left) else miss + 1
        left -= 1
    left += miss
    if x0 - left < h * 2 or x0 - left > W * 0.8:   # heurística falhou: ~3-4 emojis + número
        left = max(0, x0 - h * 7.5)
    right = min(W, x1 + h * 1.1)
    top, bottom = max(0, y0 - h * 0.75), min(H, y1 + h * 0.75)
    return n, [round(left / W, 4), round(top / H, 4), round(right / W, 4), round(bottom / H, 4)]


def prepare(pdir, files, ws):
    """files: 2 prints (em assets/ ou caminho); ws = [palavra do 1º print, do 2º, do zoom, da soma, de saída]."""
    assets = Path(pdir) / "assets"
    out_files, focus, nums, hidden = [], [], [], 0
    for f in files[:2]:
        f = Path(f)
        if not f.is_absolute() and (assets / f).exists():
            f = assets / f
        if f.parent.resolve() != assets.resolve():
            shutil.copy2(f, assets / f.name)
            f = assets / f.name
        dst = assets / f"{f.stem}_blur.jpg"
        hidden += _blur_money(f, dst)
        n, fr = _reactions(dst)
        out_files.append(dst.name)
        focus.append(fr)
        nums.append(n)
    w1p, w2p, wz, wsum, wend = ws
    nums_ok = all(isinstance(n, int) for n in nums)
    ov = {"type": "motion", "template": "prints_soma", "w0": w1p, "w1": wend, "hide_captions": True,
          "params": {"files": out_files, "focus": focus,
                     "items": [{"w": w1p}, {"w": w2p}, {"w": wz}, {"w": wsum}],
                     **({"nums": nums, "total": sum(nums)} if nums_ok else {})},
          "reason": "prints que somam (hook)"}
    clicks = [{"type": "sfx", "sfx": "click_classico", "w0": w, "w1": w, "reason": "print entrando"} for w in (w1p, w2p)]
    return ov, clicks, {"valores_borrados": hidden, "reacoes": nums, "foco": focus}

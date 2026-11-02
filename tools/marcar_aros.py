"""Aros de PINCEL à mão marcando coisas num vídeo (V015 02/11: Apple × Nike no relógio).

Ele reprovou o traço uniforme ("muito mal feitos esses tracejados… cara de paint"): o aro é um traço de pincel —
largura que engrossa no meio e afina nas pontas, cerdas (vários fios finos com falhas de tinta seca), começo e fim
que se cruzam como uma volta feita à mão — e o NOME fica perto do aro, nunca em cima do contorno.

Uso: python tools/marcar_aros.py <entrada.mp4> <saida.mp4> <marcas.json>
marcas.json = {"dur": s, "fps": 29.97, "drift": [dx/s, dy/s],
               "marks": [{"c": [x, y], "a": raio_maior, "b": raio_menor, "ang": graus, "t": s, "label": "Apple",
                          "lp": [x, y]}]}  (coordenadas no quadro original, em t=0)
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GOLD = (224, 187, 106)
CREAM = (245, 239, 230)


def ease(x):
    return 1 - (1 - max(0.0, min(1.0, x))) ** 3


def path(m, dx, dy, frac, n=220):
    """Pontos da volta (um pouco mais que 360°, começo e fim se cruzam) e a tangente em cada um."""
    a0 = math.radians(205)
    ca, sa = math.cos(math.radians(m["ang"])), math.sin(math.radians(m["ang"]))
    pts = []
    for i in range(int(n * frac) + 1):
        u = i / n
        th = a0 + 2 * math.pi * 1.1 * u
        r = 1 + sum(j * math.sin((k + 2) * th + k) for k, j in enumerate(m["jit"])) + 0.05 * u
        x, y = m["a"] * r * math.cos(th), m["b"] * r * math.sin(th)
        pts.append((m["c"][0] + dx + x * ca - y * sa, m["c"][1] + dy + x * sa + y * ca, u))
    return pts


def brush(draw, pts, width, rng_seed):
    """Traço de pincel: N cerdas paralelas, largura em forma de folha (fina-grossa-fina), tinta que falha de leve."""
    if len(pts) < 3:
        return
    rng = np.random.default_rng(rng_seed)
    nb = 15
    offs = np.linspace(-0.5, 0.5, nb)
    alphas = rng.uniform(0.55, 1.0, nb)
    widths = rng.uniform(2.4, 4.6, nb)
    gaps = [rng.uniform(0, 1, 40) for _ in range(nb)]          # falhas de tinta seca, diferentes em cada cerda
    body = []
    for i in range(1, len(pts)):
        x1, y1, u1 = pts[i]
        body.append((x1, y1))
    if len(body) > 1:
        draw.line(body, fill=GOLD + (150,), width=int(width * 0.55), joint="curve")
    for b in range(nb):
        seg = []
        for i in range(1, len(pts)):
            x0, y0, u0 = pts[i - 1]
            x1, y1, u1 = pts[i]
            tx, ty = x1 - x0, y1 - y0
            ln = math.hypot(tx, ty) or 1
            nx, ny = -ty / ln, tx / ln
            env = math.sin(math.pi * min(1.0, max(0.0, u1 / 1.1))) ** 0.6        # folha: fino nas pontas
            w = width * (0.25 + 0.75 * env)
            o = offs[b] * w
            dry = gaps[b][int(u1 * 39)] < (0.04 if abs(offs[b]) < 0.35 else 0.2)   # as cerdas de fora falham mais
            if dry:
                if len(seg) > 1:
                    draw.line(seg, fill=GOLD + (int(255 * alphas[b]),), width=int(round(widths[b])), joint="curve")
                seg = []
                continue
            seg.append((x1 + nx * o, y1 + ny * o))
        if len(seg) > 1:
            draw.line(seg, fill=GOLD + (int(255 * alphas[b]),), width=int(round(widths[b])), joint="curve")


def main():
    src, out, spec = sys.argv[1], sys.argv[2], json.loads(Path(sys.argv[3]).read_text())
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    W, H = spec.get("size", [1920, 1080])
    fps, dur = float(spec.get("fps", 29.97)), float(spec["dur"])
    ddx, ddy = spec.get("drift", [0, 0])
    font = ImageFont.truetype(str(ROOT / "fonts" / "MontserratAlternates-Bold.ttf"), int(spec.get("font_px", 74)))
    rng = np.random.default_rng(3)
    marks = spec["marks"]
    for m in marks:
        m["jit"] = [rng.uniform(-0.03, 0.03) for _ in range(4)]
    p = subprocess.Popen([ff, "-v", "error", "-y", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}",
                          "-r", f"{fps}", "-i", "-", "-filter_complex", "[0:v][1:v]overlay=format=auto,format=yuv420p",
                          "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-an", "-t", f"{dur}", out],
                         stdin=subprocess.PIPE)
    for k in range(int(dur * fps) + 1):
        t = k / fps
        dx, dy = ddx * t, ddy * t
        ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        di, ds = ImageDraw.Draw(ink), ImageDraw.Draw(sh)
        for j, m in enumerate(marks):
            fr = ease((t - m["t"]) / 0.55)
            if fr <= 0:
                continue
            pts = path(m, dx, dy, fr)
            brush(di, pts, m.get("w", 17), 100 + j)
            ds.line([(x + 3, y + 5) for x, y, _ in pts], fill=(10, 6, 3, 120), width=14, joint="curve")
            la = ease((t - m["t"] - 0.3) / 0.4)
            if la > 0:
                x, y = m["lp"][0] + dx, m["lp"][1] + dy + (1 - la) * 16
                ds.text((x + 3, y + 5), m["label"], font=font, fill=(10, 6, 3, int(190 * la)))
                di.text((x, y), m["label"], font=font, fill=CREAM + (int(255 * la),))
        frame = Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)), ink.filter(ImageFilter.GaussianBlur(0.6)))
        p.stdin.write(frame.tobytes())
    p.stdin.close()
    p.wait()
    print("ok", out)


if __name__ == "__main__":
    main()

"""Color grading automático — o que um colorista faria primeiro com um vídeo cru:

1. balanço de branco (tira o tom avermelhado/azulado da luz ambiente, preservando a pele);
2. pontos de preto e branco (contraste "limpo", sem lavado nem estourado);
3. exposição (traz o vídeo escuro para um brilho bom de rede social);
4. saturação na medida e uma curva em S suave;
5. em vídeo escuro: redução de ruído leve; sempre: nitidez leve.

A análise roda uma vez por vídeo (amostra de quadros) e vira uma cadeia de filtros do ffmpeg.
"""
import math
import subprocess

import numpy as np

from .media import FFMPEG

W = 160


def analyze(src, duration, hdr=False):
    """Mede cor e luz em ~16 quadros espalhados pelo vídeo (já convertido para SDR, se for HDR)."""
    from .media import TONEMAP
    n = 16
    step = max(0.5, duration / (n + 1))
    pre = TONEMAP + "," if hdr else ""
    p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf",
                        f"{pre}fps=1/{step:.3f},scale={W}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    data = np.frombuffer(p.stdout, np.uint8)
    if not len(data):
        return None
    px = data.reshape(-1, 3).astype(np.float32) / 255.0
    Y = px @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    mid = (Y > 0.08) & (Y < 0.92)
    m = px[mid] if mid.sum() > 500 else px
    mean_rgb = m.mean(0)
    mx, mn = px.max(1), px.min(1)
    sat = np.where(mx > 0.02, (mx - mn) / np.maximum(mx, 1e-3), 0)
    return {
        "black": float(np.percentile(Y, 1)),
        "white": float(np.percentile(Y, 99.5)),
        "mean": float(Y.mean()),
        "rgb": [float(x) for x in mean_rgb],
        # saturação medida só no que tem cor (pele, cabelo, roupa) — parede branca não conta
        "sat": float(sat[mid & (sat > 0.08)].mean() if (mid & (sat > 0.08)).sum() > 200 else sat.mean()),
    }


def params(a, strength=1.0):
    """Converte a análise em correções (todas limitadas para nunca "estragar" o vídeo)."""
    if not a:
        return None
    r, g, b = a["rgb"]
    gray = (r + g + b) / 3
    gains = []
    for c in (r, g, b):
        k = gray / max(c, 1e-3)
        k = 1 + (k - 1) * 0.45 * strength            # corrige ~45% do desvio: mantém o calor da pele
        gains.append(min(1.15, max(0.92, k)))
    lum = 0.2126 * gains[0] + 0.7152 * gains[1] + 0.0722 * gains[2]
    gains = [x / lum for x in gains]                  # o balanço não muda o brilho
    black = min(0.08, max(0.0, a["black"] * 0.85))
    white = max(0.8, min(1.0, a["white"] + (1 - a["white"]) * 0.3))
    mean_after = min(0.95, max(0.02, (a["mean"] - black) / max(0.05, white - black)))
    gamma, contrast = 1.0, 1.04
    if mean_after < 0.4:                              # escuro: clareia os meios-tons e devolve contraste
        gamma = math.log(mean_after) / math.log(0.42)
        gamma = min(1.35, max(1.0, 1 + (gamma - 1) * strength))
        contrast = 1.0 + 0.08 * (gamma - 1) / 0.35 + 0.04
    elif mean_after > 0.78:                           # muito claro (cena "high key"): só segura um pouco
        gamma = 0.93
    sat = 1.0
    if a["sat"] < 0.2:
        sat = min(1.12, 0.2 / max(a["sat"], 0.05))
    elif a["sat"] > 0.42:
        sat = 0.94                                    # já está saturado demais: segura
    if gamma > 1.1:
        sat = max(sat, 1.08)                          # clarear lava a cor: devolve um pouco
    return {"gains": [round(x, 4) for x in gains], "black": round(black, 4), "white": round(white, 4),
            "gamma": round(gamma, 3), "contrast": round(contrast, 3),
            "saturation": round(1 + (sat - 1) * strength, 3),
            "denoise": a["mean"] < 0.3, "analysis": a}


def ffmpeg_chain(pr):
    if not pr:
        return ""
    gr, gg, gb = pr["gains"]
    lo, hi = pr["black"], pr["white"]
    parts = [
        "format=yuv420p",   # colorlevels falha em 10 bits
        f"colorchannelmixer=rr={gr:.4f}:gg={gg:.4f}:bb={gb:.4f}",
        f"colorlevels=rimin={lo:.4f}:gimin={lo:.4f}:bimin={lo:.4f}:rimax={hi:.4f}:gimax={hi:.4f}:bimax={hi:.4f}",
        f"eq=gamma={pr['gamma']:.3f}:contrast={pr.get('contrast', 1.0):.3f}:saturation={pr['saturation']:.3f}",
        "curves=all='0/0 0.25/0.23 0.5/0.5 0.75/0.78 1/1'",
    ]
    if pr.get("denoise"):
        parts.append("hqdn3d=1.5:1.5:6:6")
    parts.append("unsharp=5:5:0.35:5:5:0")
    return ",".join(parts)

"""Exporta o vídeo final num único comando ffmpeg.

Ordem das camadas (de baixo para cima):
  vídeo cortado (zoom alternado/ênfase, transições) -> look de cor
  -> [fundo desfocado/escuro + texto atrás da pessoa + pessoa recortada]
  -> perspectiva 3D -> B-roll/prints/cards -> motions -> flash -> legendas e textos
Áudio: voz tratada + efeitos sonoros + música com ducking -> normalização (-14 LUFS).
"""
import re
import shutil
import subprocess
from pathlib import Path

from . import fonts, grade, motion, segment, sfx, timeline
from .media import FFMPEG, kind_of

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
SYSTEM_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
]

FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}

LOOKS = {
    "none": "",
    "cinema": "colorbalance=rs=-0.07:gs=-0.02:bs=0.08:rh=0.08:gh=0.02:bh=-0.07,"
              "eq=contrast=1.08:saturation=1.06,vignette=PI/5,noise=alls=5:allf=t",
    "quente": "colorbalance=rm=0.06:gm=0.01:bm=-0.05:rh=0.05:bh=-0.03,eq=saturation=1.1:contrast=1.04",
    "frio": "colorbalance=bs=0.06:bm=0.05:rh=-0.03,eq=saturation=0.95:contrast=1.05",
    "pb": "hue=s=0,eq=contrast=1.18,vignette=PI/5,noise=alls=8:allf=t",
    "vintage": "curves=preset=vintage,vignette=PI/4,noise=alls=10:allf=t",
    "vivido": "eq=saturation=1.3:contrast=1.06,unsharp=5:5:0.6",
    # Kronos: luxo quente — pretos levantados e quentes (viram Ônix #150C06), altas em âmbar,
    # saturação média-baixa, pele natural.
    "kronos": "curves=r='0/0.082 0.25/0.29 0.5/0.535 0.75/0.775 1/0.99':"
              "g='0/0.047 0.25/0.255 0.5/0.5 0.75/0.745 1/0.97':"
              "b='0/0.024 0.25/0.215 0.5/0.45 0.75/0.69 1/0.91',"
              "eq=saturation=0.86,colorbalance=rh=0.03:gh=0.01:bh=-0.03",
}

VOICE_CHAIN = ("highpass=f=80,afftdn=nf=-25,"
               "equalizer=f=200:t=q:w=1:g=-1.5,equalizer=f=3200:t=q:w=1.2:g=2.5,"
               "acompressor=threshold=-20dB:ratio=3:attack=5:release=90:makeup=2")


def ensure_fonts():
    fonts.ensure()


def even(x):
    return max(2, int(x) // 2 * 2)


def output_size(src, fmt):
    sw, sh = src["width"] or 1920, src["height"] or 1080
    if fmt in FORMATS:
        return FORMATS[fmt]
    scale = min(1.0, 1920 / max(sw, sh))
    return even(sw * scale), even(sh * scale)


def crop_fraction(src, W, H):
    """Fração (largura, altura) do quadro original que preenche a saída (corte centralizado)."""
    sw, sh = src["width"] or W, src["height"] or H
    if sw / sh > W / H:
        return (sh * W / H) / sw, 1.0
    return 1.0, (sw * H / W) / sh


# ---------------------------------------------------------------- legendas e textos (ASS)

def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ass_header(W, H, styles):
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", ""])


def ass_color(hexcolor, alpha=0):
    """#RRGGBB -> &HAABBGGRR do ASS (alpha 0 = opaco, 255 = invisível)."""
    h = hexcolor.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def apply_case(text, case):
    if case == "upper":
        return text.upper()
    if case == "lower":
        # siglas (IA, NASA, GPS) continuam maiúsculas
        return " ".join(w if (sum(c.isupper() for c in w) >= 2 and w.upper() == w) else w.lower()
                        for w in text.split(" "))
    return text


SOFT = "\\blur7"   # halo escuro difuso: legível em fundo claro sem parecer contorno


def build_ass(comp, W, H, path):
    s = comp["settings"]
    vertical = H > W
    cap = int(H * (0.052 if vertical else 0.075))
    cap_mv = int(H * (0.22 if vertical else 0.08))
    title = int(H * (0.04 if vertical else 0.06))
    kw = int(min(W, H) * (0.13 if vertical else 0.15))
    out = max(3, cap // 9)
    clean = int(W * 0.082) if vertical else int(H * 0.075)
    F = fonts.CAPTION_FONT
    txt = ass_color(s.get("caption_color", "#FFFFFF"))
    shade = s.get("caption_outline", "#000000")
    out_c, back_c = ass_color(shade, 0x55), ass_color(shade, 0x70)
    if s.get("caption_box"):   # caixa (ex.: Sépia ~78%) em vez do halo
        box = ass_color(s.get("caption_box_color", "#000000"), round(255 * (1 - float(s.get("caption_box_opacity", 0.78)))))
        clean_border = f"3,{max(8, clean // 5)},0"
        out_c = back_c = box
    else:
        clean_border = f"1,{max(3, clean // 18)},2"
    panel, panel_txt = ass_color(s.get("panel_color", "#FFFFFF")), ass_color(s.get("panel_text", "#111111"))
    styles = [
        f"Style: Clean,{F} SemiBold,{clean},{txt},{txt},{out_c},{back_c},0,0,0,0,100,100,{-clean * 0.035:.1f},0,{clean_border},5,40,40,0,1",
        f"Style: Emph,{F} Bold,{clean},{txt},{txt},{ass_color(shade, 0x55)},{ass_color(shade, 0x70)},0,0,0,0,100,100,{-clean * 0.045:.1f},0,1,{max(3, clean // 16)},2,8,40,40,0,1",
        f"Style: Pop,Arial Black,{cap},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{out},2,2,60,60,{cap_mv},1",
        f"Style: Classic,{F} SemiBold,{int(cap * .8)},&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,0,0,0,0,100,100,0,0,3,{out},0,2,60,60,{int(cap_mv * .6)},1",
        f"Style: Title,{F} Bold,{title},{panel_txt},{panel_txt},{panel},{panel},0,0,0,0,100,100,{-title * 0.03:.1f},0,3,{max(10, title // 3)},0,8,80,80,{int(H * .09)},1",
        f"Style: Keyword,{F} ExtraBold,{kw},&H00FFFFFF,&H00FFFFFF,&HA0000000,&H90000000,0,0,0,0,100,100,{-kw * 0.04:.1f},0,1,3,0,5,60,60,0,1",
        f"Style: Lower,{F} Bold,{int(title * .8)},{panel_txt},{panel_txt},{panel},{panel},0,0,0,0,100,100,0,0,3,{max(8, title // 4)},0,1,{int(W * .05)},60,{int(H * (.3 if vertical else .14))},1",
    ]
    lines = [ass_header(W, H, styles)]
    upper = s.get("uppercase", False)
    case = s.get("caption_case", "lower")
    gold = ass_color(s.get("accent", "#C29A5B"))

    def fmt(w):
        return ass_escape(w.upper() if upper else w)

    def cfmt(w):
        return ass_escape(apply_case(w, case))

    mode = s.get("captions", "clean")
    if mode == "clean":
        y = H * (0.62 if vertical else 0.82)
        for c in comp["captions"]:
            text = " ".join(cfmt(w["w"]) for w in c["words"]).rstrip(",;:")
            lines.append(f"Dialogue: 0,{ass_time(c['a'])},{ass_time(c['b'])},Clean,,0,0,0,,"
                         f"{{\\an5\\pos({W / 2:.0f},{y:.0f}){SOFT}\\fad(70,0)}}{text}")
    elif mode == "pop":
        for c in comp["captions"]:
            ws = c["words"]
            for k, w in enumerate(ws):
                a, b = w["a"], (ws[k + 1]["a"] if k + 1 < len(ws) else c["b"])
                if b - a < 0.02:
                    continue
                parts = [("{\\c&H0000E6FF&\\fscx108\\fscy108}" + cfmt(x["w"]) + "{\\r}") if j == k else cfmt(x["w"])
                         for j, x in enumerate(ws)]
                lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Pop,,0,0,0,,{' '.join(parts)}")
    elif mode == "classic":
        for c in comp["captions"]:
            lines.append(f"Dialogue: 0,{ass_time(c['a'])},{ass_time(c['b'])},Classic,,0,0,0,,"
                         + " ".join(cfmt(w["w"]) for w in c["words"]))

    # frases de destaque: linhas com tamanhos diferentes, palavra-chave dourada, revelação palavra a palavra
    # (as "atrás da cabeça" vão para build_behind_ass, desenhadas antes de recolocar a pessoa)
    for ov in comp["overlays"]:
        lay = ov.get("layout") if ov.get("type") == "emphasis" else None
        if lay and not lay.get("behind"):
            lines += emphasis_events(ov, lay, s, cfmt, gold)

    for ov in comp["overlays"]:
        if ov.get("type") != "text" or not ov.get("text"):
            continue
        text = ass_escape(ov["text"].upper() if upper else ov["text"])
        style = {"keyword": "Keyword", "lower": "Lower"}.get(ov.get("style"), "Title")
        anim = ("{\\fad(80,150)\\fscx60\\fscy60\\t(0,140,\\fscx112\\fscy112)\\t(140,240,\\fscx100\\fscy100)}"
                if style == "Keyword" else "{\\fad(150,150)}")
        lines.append(f"Dialogue: 2,{ass_time(ov['a'])},{ass_time(ov['b'])},{style},,0,0,0,,{anim}{text}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


ENTER_MS = 220


def emphasis_events(ov, lay, s, cfmt, gold):
    """Dialogues ASS de uma frase de destaque. Cada linha aparece quando começa a ser falada e as palavras
    se revelam uma a uma. Entrada: saindo do desfoque; na frase especial também com movimento
    (de cima / de lado) e a palavra-chave crescendo — como na referência @tay.ldantas."""
    out = []
    toks = [t for ln in lay["lines"] for t in ln["words"]]
    idx = {id(t): n for n, t in enumerate(toks)}
    times = [max(ov["a"], t["a"]) for t in toks]
    per_line = lay.get("per_line")
    heights = [ln["size"] * 0.98 for ln in lay["lines"]]
    y = lay["y"] - sum(heights) / 2
    an_block = 9 if lay["align"] == "right" else 8
    for li, ln in enumerate(lay["lines"]):
        color = gold if ln["gold"] else ass_color(s.get("caption_color", "#FFFFFF"))
        first = idx[id(ln["words"][0])]
        if per_line:
            x, ly = ln["x"], ln["top"]
            an = {"left": 7, "center": 8, "right": 9}[ln["align"]]
        else:
            x, ly, an = lay["x"], y, an_block
        for k in range(first, len(toks)):
            a = times[k]
            b = times[k + 1] if k + 1 < len(toks) else ov["b"]
            if b - a < 0.02:
                continue
            parts = []
            for t in ln["words"]:
                hidden = idx[id(t)] > k
                parts.append(("{\\alpha&HFF&}" if hidden else "{\\alpha&H00&}") + cfmt(t["w"]))
            pos = f"\\pos({x:.0f},{ly:.0f})"
            anim = ""
            if k == first:                      # a linha está entrando
                enter = ln.get("enter")
                d = 60 if enter else 0
                if enter in ("top", "left", "right"):
                    dx, dy = {"top": (0, -d), "left": (-d * 1.4, 0), "right": (d * 1.4, 0)}[enter]
                    pos = f"\\move({x + dx:.0f},{ly + dy:.0f},{x:.0f},{ly:.0f},0,{ENTER_MS})"
                elif enter == "zoom":
                    anim += f"\\fscx135\\fscy135\\t(0,{ENTER_MS + 60},\\fscx100\\fscy100)"
                blur0 = 12 if enter else 6
                anim += f"\\blur{blur0}\\t(0,{ENTER_MS},\\blur0.6)\\fad({120 if enter else 90},0)"
            if k == len(toks) - 1:
                anim += "\\fad(0,160)" if k != first else ""
            out.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Emph,,0,0,0,,"
                       f"{{\\an{an}{pos}\\fs{ln['size']}\\fsp{-ln['size'] * 0.045:.1f}"
                       f"\\1c{color}{SOFT}{anim}}}{' '.join(parts)}")
        y += heights[li]
    return out


def has_behind(o):
    return o.get("type") == "behind" or (o.get("type") == "emphasis" and (o.get("layout") or {}).get("behind"))


def build_behind_ass(comp, W, H, path):
    """Texto gigante que fica ATRÁS da pessoa (desenhado no fundo antes de recolocar a pessoa)."""
    size = int(min(W, H) * (0.24 if H > W else 0.3))
    styles = [f"Style: Behind,Arial Black,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
              f"0,0,0,0,100,100,-2,0,1,0,0,5,20,20,0,1"]
    lines = [ass_header(W, H, styles)]
    accent = ass_color(comp["settings"].get("accent", "#E0BB6A")) + "&"
    for ov in comp["overlays"]:
        if ov.get("type") == "behind" and ov.get("text"):
            text = ass_escape(ov["text"].upper())
            color = f"{{\\c{accent}}}" if ov.get("accent") else ""
            lines.append(f"Dialogue: 0,{ass_time(ov['a'])},{ass_time(ov['b'])},Behind,,0,0,0,,"
                         f"{{\\fad(200,200)\\fscx85\\fscy85\\t(0,400,\\fscx100\\fscy100)}}{color}{text}")
    # frases especiais "atrás da cabeça": mesmo estilo Emph da legenda, desenhadas no fundo
    s = comp["settings"]
    clean = int(W * 0.082) if H > W else int(H * 0.075)
    txt = ass_color(s.get("caption_color", "#FFFFFF"))
    shade = s.get("caption_outline", "#000000")
    emph_style = (f"Style: Emph,{fonts.CAPTION_FONT} Bold,{clean},{txt},{txt},{ass_color(shade, 0x55)},"
                  f"{ass_color(shade, 0x70)},0,0,0,0,100,100,{-clean * 0.045:.1f},0,1,{max(3, clean // 16)},2,8,40,40,0,1")
    lines[0] = ass_header(W, H, styles + [emph_style])
    case = s.get("caption_case", "lower")
    gold = ass_color(s.get("accent", "#C29A5B"))
    for ov in comp["overlays"]:
        lay = ov.get("layout") if ov.get("type") == "emphasis" else None
        if lay and lay.get("behind"):
            lines += emphasis_events(ov, lay, s, lambda w: ass_escape(apply_case(w, case)), gold)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def filter_path(p):
    """Caminho relativo à raiz (o ffmpeg roda nela) escapado para dentro de um filtro."""
    return Path(p).relative_to(ROOT).as_posix().replace("\\", "/").replace("'", "\\'").replace(":", "\\:")


# ---------------------------------------------------------------- preparação (motions, máscara)

DIP_CURVE = [0.25, 0.55, 0.85, 1, 0.8, 0.45, 0.15]   # opacidade por quadro (branco/escuro), pico no corte
BLUR_CURVE = [4, 10, 18, 22, 16, 8, 3]               # desfoque por quadro
DIP_PRE = 3
LEAK_FRAMES, LEAK_PRE = 9, 4           # 9 quadros (~0,3 s); o pico (creme) cai no quadro 4 = momento do corte
LEAK_DIR = ROOT / "transitions"


def leak_frames(fps, side=0):
    """Quadros RGBA da transição de luz (referência instagram.com/p/Dd4qhPrBCgr), com as cores Kronos:
    Coral #F0916B e Dourado #E0BB6A entram pela borda, estouram para Creme #F5EFE6 e somem.
    Gerados uma vez em baixa resolução (gradientes não precisam de mais) e escalados no render."""
    import numpy as np
    out = LEAK_DIR / f"leak_{int(round(fps))}_{side}"
    if (out / f"{LEAK_FRAMES:05d}.png").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    w, h = 270, 480
    y, x = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    if side:
        x = 1 - x
    coral, gold, creme = (np.array(c, float) for c in ((240, 145, 107), (224, 187, 106), (245, 239, 230)))
    deep = np.array((214, 96, 70), float)          # coral mais fundo, só na borda da luz
    frames = []
    # (quanto a luz já entrou 0..1, opacidade do creme por cima)
    steps = [(0.18, 0), (0.45, 0), (0.75, 0.2), (0.95, 0.6), (1, 1), (1, 1),
             (0.7, 0.55), (0.4, 0.22), (0.15, 0.05)]
    for k, (p, wh) in enumerate(steps):
        # frente de luz vindo da borda, com curvatura e um "blob" que varia por quadro
        front = x * 1.25 + 0.18 * np.sin(y * 3.1 + k * 0.5) - 0.12 * (y - 0.5) ** 2
        a = np.clip((p * 1.6 - front) / 0.45, 0, 1) ** 1.5
        tint = np.clip(front - p * 0.9 + 0.5, 0, 1)[..., None]
        col = deep * tint + coral * (1 - tint)
        col = col * (1 - a[..., None] * 0.5) + gold * (a[..., None] * 0.5)
        col = col * (1 - wh) + creme * wh
        alpha = np.clip(a * 0.95 + wh, 0, 1)
        frames.append(np.dstack([col, alpha * 255]).astype(np.uint8))
    for k, fr in enumerate(frames):
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
                        "-s", f"{w}x{h}", "-i", "-", "-frames:v", "1", str(out / f"{k + 1:05d}.png")],
                       input=fr.tobytes(), check=True)
    return out


def prepare(project, pdir, on_progress=None):
    pdir = Path(pdir).resolve()
    """Gera o que o render precisa antes do ffmpeg: frames de motion e máscara de recorte."""
    comp = timeline.compute(project)
    s = comp["settings"]
    W, H = output_size(project["source"], s.get("format", "original"))
    fps = min(60.0, project["source"].get("fps") or 30.0)
    jobs, owners = [], []
    for ov in comp["overlays"]:
        job = motion_job(ov, pdir, W, H, fps)
        if job:
            jobs.append(job)
            owners.append(ov["id"])
    frames = {}
    if jobs:
        dirs = motion.ensure(jobs, pdir / "motion_cache",
                             on_progress=lambda x: on_progress and on_progress(0.25 * x, "Animando motions…"))
        frames = dict(zip(owners, dirs))
    needs_mask = s.get("background") in ("blur", "escuro") or any(has_behind(o) for o in comp["overlays"])
    mask = pdir / "mask.mp4"
    if needs_mask and not mask.exists():
        if on_progress:
            on_progress(0.26, "Recortando você do fundo (só na primeira vez)…")
        segment.build_mask(pdir / project["source"]["file"], mask,
                           on_progress=lambda x: on_progress and on_progress(0.26 + 0.2 * x, "Recortando você do fundo…"))
    if needs_mask and mask.exists():
        place_behind_heads(project, comp, mask)
    return frames, (mask if needs_mask else None)


def head_center(mask, t):
    """Altura (0..1) do centro da cabeça no quadro do recorte em `t` (s, no original), ou None."""
    import numpy as np
    info = probe_size(mask)
    if not info:
        return None
    w, h = info
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t):.3f}", "-i", str(mask),
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if r.returncode or len(r.stdout) < w * h:
        return None
    m = np.frombuffer(r.stdout[:w * h], np.uint8).reshape(h, w) > 128
    rows = np.where(m.mean(1) > 0.04)[0]
    if not len(rows):
        return None
    top = rows[0] / h
    return min(0.6, top + 0.06)           # testa/olhos: a palavra cruza a cabeça e continua legível


def probe_size(path):
    from .media import probe
    i = probe(path)
    return (i["width"], i["height"]) if i["width"] else None


def place_behind_heads(project, comp, mask):
    """Frase especial "atrás da cabeça": centra a palavra-chave na altura real da cabeça naquele momento
    (considerando o zoom/enquadramento do trecho)."""
    words = project.get("words", [])
    src = project["source"]
    for ov in project.get("overlays", []):
        if ov.get("type") != "emphasis" or ov.get("variant") != "atras" or ov.get("head_y_manual"):
            continue
        t = words[ov["w0"]]["start"] + 0.25
        hc = head_center(mask, t)
        if hc is None:
            continue
        piece = next((p for p in comp["segments"] if p["start"] <= t <= p["end"]), None)
        z = piece["zoom"] if piece else 1.0
        out_y = (hc - (1 - 1 / z) * 0.4) * z      # mesmo recorte do piece_chain (y=(ih-oh)*0.4)
        ov["head_y"] = round(min(0.55, max(0.14, out_y)), 3)


def motion_job(ov, pdir, W, H, fps):
    dur = max(0.8, ov["b"] - ov["a"])
    base = {"width": W, "height": H, "fps": fps, "seconds": dur}
    params = dict(ov.get("params") or {})
    params.update({"dur": round(dur, 2), "vertical": H > W})
    if ov.get("type") == "motion" and ov.get("template") in motion.TEMPLATES:
        if ov["template"] == "carrossel3d":
            params["files"] = [(pdir / "assets" / f).as_uri() for f in params.get("files", [])
                               if (pdir / "assets" / f).exists()]
        if ov["template"] == "card3d" and ov.get("file"):
            params["src"] = (pdir / "assets" / ov["file"]).as_uri()
        return {**base, "template": ov["template"], "params": params}
    if ov.get("type") == "media" and ov.get("layout") == "card3d" and ov.get("file") \
            and kind_of(ov["file"]) == "image" and (pdir / "assets" / ov["file"]).exists():
        params["src"] = (pdir / "assets" / ov["file"]).as_uri()
        return {**base, "template": "card3d", "params": params}
    return None


# ---------------------------------------------------------------- comando ffmpeg

def build_command(project, pdir, out_path, motion_frames=None, mask=None, limit=None, scale=1.0):
    pdir = Path(pdir).resolve()
    comp = timeline.compute(project)
    src = project["source"]
    s = comp["settings"]
    pieces = comp["segments"]
    W, H = output_size(src, s.get("format", "original"))
    fx, fy = crop_fraction(src, W, H)
    fps = min(60.0, src.get("fps") or 30.0)
    total = min(comp["duration"], float(limit)) if limit else comp["duration"]
    td = comp["transition_duration"]
    n = len(pieces)
    if n == 0 or total <= 0:
        raise ValueError("Nada para exportar: todas as falas foram cortadas.")
    motion_frames = motion_frames or {}

    # rotação de vídeo de celular aplicada à mão: o ffmpeg 7.1 deixa de girar sozinho
    # quando o comando tem várias entradas (ex.: efeitos sonoros)
    rot = src.get("rotation")
    if rot is None:
        from .media import probe
        rot = probe(pdir / src["file"]).get("rotation", 0)
    rotate = {90: "transpose=2,", 270: "transpose=1,", 180: "hflip,vflip,"}.get(rot % 360, "")
    inputs = ["-noautorotate", "-i", str(pdir / src["file"])]
    from .media import TONEMAP, probe as _probe
    hdr = src.get("hdr", "?")
    if hdr == "?":
        hdr = _probe(pdir / src["file"]).get("hdr")
    if hdr:
        rotate = TONEMAP + "," + rotate
    f = []
    has_audio = src.get("has_audio", True)

    def add_input(*args):
        inputs.extend(args)
        return sum(1 for x in inputs if x == "-i") - 1

    mask_idx = add_input("-i", str(mask)) if mask else None

    # --- trechos (vídeo, máscara e áudio passam pelo MESMO corte)
    def piece_chain(label, k, p, is_mask=False):
        z = p["zoom"]
        cw, ch = fx / z, fy / z
        fmt = "format=gray" if is_mask else "format=yuv420p"
        kb = ""
        k0, k1 = p.get("kb0", 1.0), p.get("kb1", 1.0)
        if abs(k1 - k0) > 1e-4 or k0 > 1.0001:
            # zoom suave contínuo: a janela de origem encolhe/cresce quadro a quadro (interpolação sub-pixel,
            # sem a "tremidinha" do zoompan); mesmo ponto de apoio vertical (40%) do enquadramento
            nfr = max(1, round((p["end"] - p["start"]) * fps))
            kk = f"({k0:.5f}+({k1 - k0:.5f})*on/{nfr})"
            L, T = f"W*(1-1/{kk})/2", f"H*(1-1/{kk})*0.4"
            R, B = f"W-{L}", f"{T}+H/{kk}"
            kb = (f",perspective=x0='{L}':y0='{T}':x1='{R}':y1='{T}':x2='{L}':y2='{B}':x3='{R}':y3='{B}'"
                  f":interpolation=cubic:sense=source:eval=frame")
        return (f"[{label}{k}]trim=start={p['start']}:end={p['end']},setpts=PTS-STARTPTS,"
                f"crop=w=trunc(iw*{cw:.5f}/2)*2:h=trunc(ih*{ch:.5f}/2)*2:x=(iw-ow)/2:y=(ih-oh)*0.4,"
                f"scale={W}:{H}:flags=bicubic,setsar=1,fps={fps}{kb},{fmt}[{'m' if is_mask else 'v'}{k}]")

    f.append(f"[0:v]{rotate}split={n}" + "".join(f"[s{k}]" for k in range(n)))
    for k, p in enumerate(pieces):
        f.append(piece_chain("s", k, p))
    if mask_idx is not None:
        f.append(f"[{mask_idx}:v]split={n}" + "".join(f"[ms{k}]" for k in range(n)))
        for k, p in enumerate(pieces):
            f.append(piece_chain("ms", k, p, is_mask=True))
    if has_audio:
        f.append(f"[0:a]asplit={n}" + "".join(f"[r{k}]" for k in range(n)))
        for k, p in enumerate(pieces):
            d = p["end"] - p["start"]
            cont_prev = k > 0 and pieces[k - 1]["g"] == p["g"]
            cont_next = k + 1 < n and pieces[k + 1]["g"] == p["g"]
            fo = 0.3 if k == n - 1 else 0.015          # último trecho termina com fade suave
            fades = ("" if cont_prev else ",afade=t=in:d=0.01") + \
                    ("" if cont_next else f",afade=t=out:st={max(0, d - fo):.3f}:d={fo}")
            f.append(f"[r{k}]atrim=start={p['start']}:end={p['end']},asetpts=PTS-STARTPTS,"
                     f"aformat=sample_rates=48000:channel_layouts=stereo{fades}[a{k}]")

    groups = []
    for k, p in enumerate(pieces):
        if not groups or groups[-1][-1][1]["g"] != p["g"]:
            groups.append([])
        groups[-1].append((k, p))

    def join(prefix, out_label, kind):
        """Concatena peças em grupos e aplica crossfade entre grupos (se houver)."""
        glabels = []
        for gi, grp in enumerate(groups):
            if len(grp) == 1:
                glabels.append(f"{prefix}{grp[0][0]}")
            else:
                lab = f"{prefix}g{gi}"
                if kind == "a":
                    f.append("".join(f"[{prefix}{k}]" for k, _ in grp) + f"concat=n={len(grp)}:v=0:a=1[{lab}]")
                else:
                    f.append("".join(f"[{prefix}{k}]" for k, _ in grp) + f"concat=n={len(grp)}:v=1:a=0[{lab}]")
                glabels.append(lab)
        if len(glabels) == 1:
            f.append(f"[{glabels[0]}]{'anull' if kind == 'a' else 'null'}[{out_label}]")
            return
        if td > 0:
            prev = glabels[0]
            for gi in range(1, len(glabels)):
                lab = f"{prefix}x{gi}" if gi < len(glabels) - 1 else out_label
                if kind == "a":
                    f.append(f"[{prev}][{glabels[gi]}]acrossfade=d={td}[{lab}]")
                else:
                    off = pieces[groups[gi][0][0]]["out"]
                    f.append(f"[{prev}][{glabels[gi]}]xfade=transition=fade:duration={td}:offset={off:.3f}[{lab}]")
                prev = lab
        else:
            if kind == "a":
                f.append("".join(f"[{x}]" for x in glabels) + f"concat=n={len(glabels)}:v=0:a=1[{out_label}]")
            else:
                f.append("".join(f"[{x}]" for x in glabels) + f"concat=n={len(glabels)}:v=1:a=0[{out_label}]")

    join("v", "base0", "v")
    if mask_idx is not None:
        join("m", "mask0", "v")
    if has_audio:
        join("a", "voice0", "a")
    else:
        vidx = add_input("-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo")
        f.append(f"[{vidx}:a]anull[voice0]")

    # --- color grading automático (corrige o insumo) e depois o look escolhido
    cur = "base0"
    if s.get("grade", "auto") == "auto":
        pr = grade_params(project, pdir, float(s.get("grade_strength", 1.0)))
        chain = grade.ffmpeg_chain(pr)
        if chain:
            f.append(f"[{cur}]{chain},format=yuv420p[gd]")
            cur = "gd"
    look = LOOKS.get(s.get("look") or "none", "")
    if look:
        f.append(f"[{cur}]{look},format=yuv420p[lk]")
        cur = "lk"

    # --- recorte: fundo tratado + texto atrás + pessoa por cima
    has_text = False
    if mask_idx is not None:
        ensure_fonts()
        f.append(f"[{cur}]split[pa][pb]")
        bg = s.get("background")
        if bg == "blur":
            f.append("[pb]gblur=sigma=22,eq=brightness=-0.04[bg0]")
        elif bg == "escuro":
            f.append("[pb]gblur=sigma=10,eq=brightness=-0.32:saturation=0.6[bg0]")
        else:
            f.append("[pb]null[bg0]")
        bgl = "bg0"
        if any(has_behind(o) for o in comp["overlays"]):
            behind = pdir / "render_behind.ass"
            build_behind_ass(comp, W, H, behind)
            f.append(f"[bg0]ass='{filter_path(behind)}':fontsdir=fonts[bg1]")
            bgl = "bg1"
        f.append("[mask0]gblur=sigma=1.5,format=gray[mk]")
        f.append("[pa]format=yuva420p[pa2]")
        f.append("[pa2][mk]alphamerge[person]")
        f.append(f"[{bgl}][person]overlay=format=auto,format=yuv420p[cut]")
        cur = "cut"

    # --- perspectiva 3D da pessoa (em trechos)
    for j, ov in enumerate(o for o in comp["overlays"] if o.get("type") == "perspective"):
        a, b = ov["a"], ov["b"]
        L, R = (0.10, 0.88) if ov.get("side", "left") == "left" else (0.12, 0.90)
        tl, tr = (W * L, H * 0.10), (W * R, H * 0.17)
        bl, br = (W * L, H * 0.90), (W * R, H * 0.83)
        if ov.get("side") == "right":
            tl, tr, bl, br = (W * L, H * 0.17), (W * R, H * 0.10), (W * L, H * 0.83), (W * R, H * 0.90)
        f.append(f"[{cur}]split=3[pc{j}][pd{j}][pe{j}]")
        f.append(f"[pd{j}]gblur=sigma=30,eq=brightness=-0.3:saturation=0.7[pbg{j}]")
        f.append(f"[pe{j}]format=rgba,scale={W - 8}:{H - 8},pad={W}:{H}:4:4:color=black@0,perspective={tl[0]:.0f}:{tl[1]:.0f}:{tr[0]:.0f}:{tr[1]:.0f}:"
                 f"{bl[0]:.0f}:{bl[1]:.0f}:{br[0]:.0f}:{br[1]:.0f}:sense=destination:interpolation=cubic[pfg{j}]")
        f.append(f"[pbg{j}][pfg{j}]overlay=format=auto[pv{j}]")
        f.append(f"[pc{j}][pv{j}]overlay=enable='between(t,{a:.3f},{b:.3f})',format=yuv420p[pp{j}]")
        cur = f"pp{j}"

    # --- B-roll, prints e cards
    for j, ov in enumerate(comp["overlays"]):
        if ov.get("type") != "media" or not ov.get("file") or ov["id"] in motion_frames:
            continue
        fpath = pdir / "assets" / ov["file"]
        if not fpath.exists():
            continue
        dur = max(0.3, ov["b"] - ov["a"])
        is_img = kind_of(fpath) == "image"
        if is_img:
            idx = add_input("-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(fpath))
        else:
            start = float(ov.get("clip_start") or 0)
            idx = add_input("-ss", f"{start:.2f}", "-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(fpath))
        frames_total = int(dur * fps) + 1
        push = f"zoompan=z='1+0.06*on/{frames_total}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
        layout = ov.get("layout") or ("card" if ov.get("print") else "full")
        tag = f"o{j}"
        if layout == "pip":
            pw = even(W * (0.5 if W > H else 0.72))
            ph = even(pw * 9 / 16) if W > H else even(pw * 10 / 16)
            f.append(f"[{idx}:v]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},setsar=1,"
                     f"fps={fps},format=yuva420p,fade=t=in:st=0:d=0.15:alpha=1,setpts=PTS-STARTPTS+{ov['a']:.3f}/TB[{tag}]")
            pos = "x=(W-w)/2:y=H*0.12" if H > W else "x=W-w-48:y=48"
        elif layout in ("card", "card3d"):
            cw_, ch_ = even(W * (0.86 if H > W else 0.74)), even(H * (0.6 if H > W else 0.78))
            f.append(f"[{idx}:v]split[cb{j}][cf{j}]")
            f.append(f"[cb{j}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,"
                     f"eq=brightness=-0.25:saturation=0.8,setsar=1[cbb{j}]")
            f.append(f"[cf{j}]scale={cw_}:{ch_}:force_original_aspect_ratio=decrease,setsar=1[cff{j}]")
            f.append(f"[cbb{j}][cff{j}]overlay=(W-w)/2:(H-h)/2,{push},format=yuva420p,"
                     f"fade=t=in:st=0:d=0.15:alpha=1,setpts=PTS-STARTPTS+{ov['a']:.3f}/TB[{tag}]")
            pos = "x=0:y=0"
        else:
            fill = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},{push}"
                    if is_img else f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps}")
            f.append(f"[{idx}:v]{fill},setsar=1,format=yuva420p,fade=t=in:st=0:d=0.12:alpha=1,"
                     f"setpts=PTS-STARTPTS+{ov['a']:.3f}/TB[{tag}]")
            pos = "x=0:y=0"
        f.append(f"[{cur}][{tag}]overlay={pos}:enable='between(t,{ov['a']:.3f},{ov['b']:.3f})':eof_action=pass,"
                 f"format=yuv420p[b{j}]")
        cur = f"b{j}"

    # --- motions (sequências PNG com transparência)
    for j, ov in enumerate(comp["overlays"]):
        d = motion_frames.get(ov.get("id"))
        if not d:
            continue
        idx = add_input("-framerate", str(fps), "-i", str(Path(d) / "%05d.png"))
        f.append(f"[{idx}:v]format=yuva420p,setpts=PTS-STARTPTS+{ov['a']:.3f}/TB[mo{j}]")
        f.append(f"[{cur}][mo{j}]overlay=0:0:enable='between(t,{ov['a']:.3f},{ov['b']:.3f})':eof_action=repeat,"
                 f"format=yuv420p[mv{j}]")
        cur = f"mv{j}"

    # --- flash (antigo) e transições pontuais "branco"/"escuro" (mergulho de cor) e "desfoque"
    flashes = [o for o in comp["overlays"] if o.get("type") == "flash"] if s.get("flashes", True) else []
    flashes += [o for o in comp["overlays"] if o.get("type") == "transition" and o.get("style") == "branco"]
    dips = [(o, "0xF5EFE6") for o in flashes] + \
        [(o, "0x150C06") for o in comp["overlays"] if o.get("type") == "transition" and o.get("style") == "escuro"]
    if dips:
        boxes = []
        for o, color in dips:
            for k, al in enumerate(DIP_CURVE):          # um quadro por passo, pico no corte
                t0 = o["a"] + (k - DIP_PRE) / fps
                boxes.append(f"drawbox=x=0:y=0:w=iw:h=ih:color={color}@{al}:t=fill:"
                             f"enable='between(t,{max(0, t0):.3f},{t0 + 1 / fps - 0.001:.3f})'")
        f.append(f"[{cur}]" + ",".join(boxes) + "[fl]")
        cur = "fl"
    blurs = [o for o in comp["overlays"] if o.get("type") == "transition" and o.get("style") == "desfoque"]
    for j, o in enumerate(blurs):
        steps = []
        for k, sg in enumerate(BLUR_CURVE):
            t0 = o["a"] + (k - DIP_PRE) / fps
            steps.append(f"gblur=sigma={sg}:enable='between(t,{max(0, t0):.3f},{t0 + 1 / fps - 0.001:.3f})'")
        f.append(f"[{cur}]" + ",".join(steps) + f"[bl{j}]")
        cur = f"bl{j}"

    # --- transição de luz (film burn): luz quente invade, estoura para creme e a cena nova sai do claro
    leaks = [o for o in comp["overlays"] if o.get("type") == "transition" and o.get("style", "leak") == "leak"]
    for j, o in enumerate(leaks):
        d = leak_frames(fps, side=j % 2)
        t0 = max(0.0, o["a"] - LEAK_PRE / fps)
        t1 = o["a"] + (LEAK_FRAMES - LEAK_PRE) / fps
        idx = add_input("-framerate", f"{fps:g}", "-i", str(Path(d) / "%05d.png"))
        f.append(f"[{idx}:v]format=rgba,scale={W}:{H},setpts=PTS-STARTPTS+{t0:.3f}/TB[lk{j}]")
        f.append(f"[{cur}]gblur=sigma=14:enable='between(t,{o['a'] - 0.1:.3f},{o['a'] + 0.04:.3f})'[lkb{j}]")
        f.append(f"[lkb{j}][lk{j}]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})':eof_action=pass,format=yuv420p[lkv{j}]")
        cur = f"lkv{j}"

    # --- legendas, títulos, palavras-chave
    has_text = (s.get("captions") in ("clean", "pop", "classic") and comp["captions"]) or any(
        o.get("type") in ("text", "emphasis") for o in comp["overlays"])
    if has_text:
        ensure_fonts()
        ass = pdir / "render.ass"
        build_ass(comp, W, H, ass)
        f.append(f"[{cur}]ass='{filter_path(ass)}':fontsdir=fonts[vt]")
        cur = "vt"
    # barra de progresso (preenche da esquerda para a direita durante o vídeo)
    if s.get("progress_bar"):
        bh = max(6, int(H * 0.006))
        y = H - bh - int(H * 0.035) if H > W else H - bh
        track = s.get("panel_color", "#2E2017").lstrip("#")
        fill = s.get("progress_color", s.get("accent", "#E0BB6A")).lstrip("#")
        # a cor é gerada dentro do filtro (uma entrada extra derruba o ffmpeg 7.1)
        f.append(f"color=c=0x{fill}:s={W}x{bh}:r={fps}:d={total:.3f}[pbc]")
        f.append(f"[{cur}]drawbox=x=0:y={y}:w={W}:h={bh}:color=0x{track}@0.78:t=fill[pbt]")
        f.append(f"[pbt][pbc]overlay=x='-W+W*t/{total:.3f}':y={y}:eof_action=pass:repeatlast=0[pbf]")
        cur = "pbf"

    # remove a "etiqueta" de rotação herdada do celular (os quadros já estão em pé)
    f.append(f"[{cur}]format=yuv420p,sidedata=mode=delete:type=DISPLAYMATRIX[vout]")

    # --- áudio
    voice = "voice0"
    if s.get("voice", True) and has_audio:
        f.append(f"[voice0]{VOICE_CHAIN}[voice1]")
        voice = "voice1"
    sfx_labels = []
    vol = float(s.get("sfx_volume", 0.55))
    for j, ov in enumerate(comp["overlays"]):
        if ov.get("type") != "sfx":
            continue
        p = sfx.path_of(ov.get("sfx", ""))
        if not p:
            continue
        idx = add_input("-i", str(p))
        meta = sfx.meta_of(ov.get("sfx", ""))
        # começa adiantado: o pico do som cai exatamente no momento marcado
        ms = int(max(0.0, ov["a"] - float(meta.get("lead", 0))) * 1000)
        gain = vol * float(ov.get("volume", 1.0)) * 10 ** (float(meta.get("gain", -6)) / 20)
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"volume={gain:.3f},adelay={ms}:all=1[fx{j}]")
        sfx_labels.append(f"fx{j}")
    music = s.get("music")
    has_music = bool(music and (pdir / "assets" / music).exists())
    # a voz só é dividida se a música precisar dela para o ducking
    if has_music:
        f.append(f"[{voice}]asplit[vmain][vsc]")
        voice_main, side = "vmain", "vsc"
    else:
        voice_main, side = voice, None
    if sfx_labels:
        f.append(f"[{voice_main}]" + "".join(f"[{x}]" for x in sfx_labels)
                 + f"amix=inputs={len(sfx_labels) + 1}:duration=first:normalize=0[vfx]")
        mixed = "vfx"
    else:
        mixed = voice_main
    if has_music:
        idx = add_input("-stream_loop", "-1", "-i", str(pdir / "assets" / music))
        mv = float(s.get("music_volume", 0.15))
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={mv},"
                 f"atrim=0:{total:.3f},afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        f.append(f"[mus][{side}]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[duck]")
        f.append(f"[{mixed}][duck]amix=inputs=2:duration=first:normalize=0[mix]")
        mixed = "mix"
    f.append(f"[{mixed}]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    script = pdir / "render_filter.txt"
    script.write_text(";\n".join(f), encoding="utf-8")
    speed = float(s.get("speed", 1.0) or 1.0)
    vopts = ["-r", f"{fps}", *(["-s", f"{even(W * scale)}x{even(H * scale)}"] if scale != 1.0 else []),
             "-c:v", "h264_videotoolbox", "-b:v", "12M", "-allow_sw", "1", "-profile:v", "high"]
    if abs(speed - 1.0) < 0.001:
        cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
               *inputs, "-filter_complex_script", str(script),
               "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}", *vopts,
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
        return cmd, total
    # velocidade ≠ 1: o vídeo acelera aqui; a voz sai em WAV (1x) e é acelerada depois pelo
    # Rubber Band (sem mudar o tom nem o timbre) — ver render()
    script.write_text(script.read_text(encoding="utf-8").replace("[vout]", "[vpre]", 1)
                      + f";\n[vpre]setpts=PTS/{speed:.4f}[vout]", encoding="utf-8")
    vtmp, atmp = Path(out_path).with_suffix(".video.tmp.mp4"), Path(out_path).with_suffix(".voz.tmp.wav")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
           *inputs, "-filter_complex_script", str(script),
           "-map", "[vout]", "-t", f"{total / speed:.3f}", *vopts, "-an", str(vtmp),
           "-map", "[aout]", "-t", f"{total:.3f}", "-c:a", "pcm_s16le", "-ar", "48000", str(atmp)]
    return cmd, total / speed


def grade_params(project, pdir, strength=1.0):
    """Análise de cor do vídeo (feita uma vez e guardada em grade.json)."""
    import json
    f = Path(pdir) / "grade.json"
    if f.exists():
        a = json.loads(f.read_text())
    else:
        src = project["source"]
        from .media import probe as _probe
        hdr = src.get("hdr", "?")
        if hdr == "?":
            hdr = _probe(Path(pdir) / src["file"]).get("hdr")
        a = grade.analyze(Path(pdir) / src["file"], src.get("duration") or 10, hdr=bool(hdr))
        f.write_text(json.dumps(a))
    return grade.params(a, strength)


def render(project, pdir, out_path, on_progress=None, limit=None, scale=1.0):
    frames, mask = prepare(project, pdir, on_progress)
    cmd, total = build_command(project, pdir, out_path, frames, mask, limit=limit, scale=scale)
    base = 0.46 if mask else (0.25 if frames else 0.0)

    def prog(x):
        if on_progress:
            on_progress(base + (0.99 - base) * x, "Renderizando…")
    speed = float(project.get("settings", {}).get("speed", 1.0) or 1.0)
    vtmp, atmp = Path(out_path).with_suffix(".video.tmp.mp4"), Path(out_path).with_suffix(".voz.tmp.wav")
    try:
        try:
            _run(cmd, total, prog)
        except RuntimeError:
            i = cmd.index("h264_videotoolbox")
            cmd[i - 1:i + 7] = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p"]
            _run(cmd, total, prog)
        if abs(speed - 1.0) >= 0.001:
            if on_progress:
                on_progress(0.99, "Acelerando a voz sem distorcer…")
            stretch_voice(atmp, speed)
            r = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(vtmp), "-i", str(atmp),
                                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                "-shortest", "-movflags", "+faststart", str(out_path)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-1500:])
    except Exception:
        Path(out_path).unlink(missing_ok=True)   # não deixa arquivo quebrado na pasta de exportações
        raise
    finally:
        vtmp.unlink(missing_ok=True)
        atmp.unlink(missing_ok=True)
    write_credits(project, Path(out_path))


def stretch_voice(wav_path, speed):
    """Acelera o áudio mantendo tom e timbre (Rubber Band, alta qualidade, formantes preservados)."""
    import numpy as np
    import wave
    import pedalboard
    with wave.open(str(wav_path), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    audio = data.reshape(-1, ch).T.copy()
    out = pedalboard.time_stretch(audio, sr, stretch_factor=float(speed), high_quality=True,
                                  transient_mode="crisp", preserve_formants=True)
    out = np.clip(out.T, -1, 1)
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())


def write_credits(project, out_path):
    used = {o.get("file") for o in project.get("overlays", []) if o.get("file")}
    for o in project.get("overlays", []):
        for f in (o.get("params") or {}).get("files", []):
            used.add(f)
    lines = [f"- {c['credit']} | licença: {c.get('license', '?')} | {c.get('page_url', '')}"
             for c in project.get("credits", []) if c.get("file") in used]
    if lines:
        out_path.with_suffix(".creditos.txt").write_text(
            "Créditos dos materiais usados neste vídeo:\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def _run(cmd, total, on_progress):
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in p.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and total:
            on_progress(min(1.0, int(m.group(1)) / 1e6 / total))
    err = p.stderr.read()
    if p.wait() != 0:
        raise RuntimeError(err[-2500:] or "ffmpeg falhou")

"""Exporta o vídeo final num único comando ffmpeg.

Ordem das camadas (de baixo para cima):
  vídeo cortado (zoom alternado/ênfase, transições) -> look de cor
  -> [fundo desfocado/escuro + texto atrás da pessoa + pessoa recortada]
  -> perspectiva 3D -> B-roll/prints/cards -> motions -> flash -> legendas e textos
Áudio: voz tratada + efeitos sonoros + música com ducking -> normalização (-14 LUFS).
"""
import math
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
    # (v2, out/2026: a v1 deixava a parede verde-ciano e a pele laranja — "cara de filtro")
    "kronos": "curves=r='0/0.05 0.5/0.515 1/0.995':g='0/0.035 0.5/0.5 1/0.985':b='0/0.025 0.5/0.48 1/0.96',"
              "eq=saturation=0.92",
}

VOICE_CHAIN = ("highpass=f=80,afftdn=nf=-25,"
               "equalizer=f=200:t=q:w=1:g=-1.5,equalizer=f=3200:t=q:w=1.2:g=2.5,"
               "acompressor=threshold=-20dB:ratio=3:attack=5:release=90:makeup=2")


def ensure_fonts():
    fonts.ensure()


# legenda padrão (pedido dele): um pouco menor (não encosta nas laterais) e no terço de baixo (longe da boca)
CAP_SIZE, CAP_Y = 0.044, 0.72
TV_W, TV_Y = 0.92, 0.40              # TV desenhada (antiga): largura (fração da tela) e centro vertical
# TV DE VERDADE numa sala (Mixkit 9612, 1280×720, câmera passeando para a direita ~15,8 px/s): janela de recorte que
# acompanha a TV (x0 + vx·t, y0, cw de largura) e o retângulo verde da tela DENTRO dessa janela (fixo, pois os dois
# andam juntos). O comercial cobre o verde com 2 px de sobra: a moldura, o rack e o abajur ficam de verdade.
# ESTABILIZADA e em vai-e-volta (backgrounds/tv_sala_estavel.mp4, 23,3 s): a TV fica PARADA no quadro (deslocamento
# sub-pixel), sem o pulo de quando a sala acabava (Liquid Death: "a TV buga indo pra esquerda") nem o tremor do recorte
# andando de pixel em pixel. Janela fixa (vx 0).
TV_SALA = {"file": "tv_sala_estavel.mp4", "x0": 193, "vx": 0.0, "y0": 80, "cw": 640, "dur": 23.3,
           "sx": 105, "sy": 166, "sw": 430, "sh": 238}     # 4 px de sobra: a borda verde cintilava
TV_KEY = "chromakey=0x00FF00:0.30:0.05,despill=type=green:mix=0.6:expand=0.2"   # tela verde → transparente
TV_MARGIN = 8                         # px (na janela da sala) que o comercial passa da tela, por trás da moldura
TOPO_H, TOPO_DY = 0.40, 0.13          # tela dividida 1: ativo nos 40% de cima, você 13% mais para baixo
MEIO_S, HEAD_TOP = 1.0, 0.15        # tela dividida 2 (50/50): você em largura total (92% deixava tarjas pretas — reprovado)


def even(x):
    return max(2, int(x) // 2 * 2)


def output_size(src, fmt):
    sw, sh = src["width"] or 1920, src["height"] or 1080
    if fmt in FORMATS:
        return FORMATS[fmt]
    # gravação pequena (ex.: WhatsApp 576x1024) sai em 1920 no lado maior: legenda e textos nítidos e o
    # Instagram comprime menos (a imagem é ampliada uma vez só, com lanczos)
    scale = 1920 / max(sw, sh) if max(sw, sh) < 1280 else min(1.0, 1920 / max(sw, sh))
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
# O libass mede o tamanho da fonte pela "altura da célula" (usWinAscent+usWinDescent = 1,379 em na Montserrat),
# o navegador pelo em. Sem esta correção a legenda exportada saía 28% MENOR que a da prévia.
FONT_K = 1.379


def halo(em):
    """Sombra suave como a da prévia (text-shadow 0 0 .25em): contorno fino escuro bem desfocado, sem traço duro."""
    return f"\\bord{em * 0.07:.1f}\\shad0\\blur{em * 0.16:.1f}"


def build_ass(comp, W, H, path):
    s = comp["settings"]
    vertical = H > W
    cap = int(H * (0.052 if vertical else 0.075))
    cap_mv = int(H * (0.22 if vertical else 0.08))
    title = int(H * (0.04 if vertical else 0.06))
    kw = int(min(W, H) * (0.13 if vertical else 0.15))
    out = max(3, cap // 9)
    clean_em = H * CAP_SIZE if vertical else H * 0.075     # = 4,4cqh da prévia (".frame.vertical .cap.clean")
    clean = round(clean_em * FONT_K)
    F = fonts.CAPTION_FONT
    txt = ass_color(s.get("caption_color", "#FFFFFF"))
    shade = s.get("caption_outline", "#000000")
    out_c, back_c = ass_color(shade, 0x4C), ass_color(shade, 0x70)
    if s.get("caption_box"):   # caixa (ex.: Sépia ~78%) em vez do halo
        box = ass_color(s.get("caption_box_color", "#000000"), round(255 * (1 - float(s.get("caption_box_opacity", 0.78)))))
        clean_border = f"3,{max(8, clean // 5)},0"
        out_c = back_c = box
    else:
        clean_border = f"1,{clean_em * 0.07:.1f},0"
    panel, panel_txt = ass_color(s.get("panel_color", "#FFFFFF")), ass_color(s.get("panel_text", "#111111"))
    styles = [
        f"Style: Clean,{F} SemiBold,{clean},{txt},{txt},{out_c},{back_c},0,0,0,0,100,100,{-clean_em * 0.035:.1f},0,{clean_border},5,40,40,0,1",
        f"Style: CleanBox,{F} SemiBold,{clean},{txt},{txt},{ass_color(s.get('caption_box_color', '#2E2017'), 0x38)},"
        f"{ass_color(s.get('caption_box_color', '#2E2017'), 0x38)},0,0,0,0,100,100,{-clean_em * 0.035:.1f},0,3,{clean_em * 0.2:.0f},0,5,40,40,0,1",
        f"Style: Emph,{F} Bold,{clean},{txt},{txt},{ass_color(shade, 0x59)},{ass_color(shade, 0x70)},0,0,0,0,100,100,{-clean_em * 0.045:.1f},0,1,{clean_em * 0.07:.1f},0,8,40,40,0,1",
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
        if isinstance(w, dict):            # palavra da legenda: nome próprio mantém a caixa; destaque = CAIXA ALTA dourada
            if w.get("hl"):
                return f"{{\\1c{gold}}}" + ass_escape(w["w"].upper()) + f"{{\\1c{txt}}}"
            return ass_escape(w["w"] if w.get("kc") else apply_case(w["w"], case))
        return ass_escape(apply_case(w, case))

    mode = s.get("captions", "clean")
    if mode == "clean":
        y = H * (CAP_Y if vertical else 0.82)
        for c in comp["captions"]:
            text = " ".join(cfmt(w) for w in c["words"]).rstrip(",;:")
            st = "CleanBox" if c.get("box") else "Clean"   # sobre o print da tela verde: caixinha sépia (legível no branco)
            lines.append(f"Dialogue: 0,{ass_time(c['a'])},{ass_time(c['b'])},{st},,0,0,0,,"
                         f"{{\\an5\\pos({W / 2:.0f},{(H * c['y'] if c.get('y') else y) - clean_em * 0.06:.0f}){'' if c.get('box') else halo(clean_em)}\\fad(70,0)}}{text}")
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
            if lay.get("panel"):           # sobre o print da tela verde: painel sépia (paleta Kronos) atrás do bloco
                x0, y0, x1, y1 = lay["panel"]
                r = min(28, (y1 - y0) // 6)
                shape = (f"m {r} 0 l {x1 - x0 - r} 0 b {x1 - x0} 0 {x1 - x0} 0 {x1 - x0} {r} l {x1 - x0} {y1 - y0 - r} "
                         f"b {x1 - x0} {y1 - y0} {x1 - x0} {y1 - y0} {x1 - x0 - r} {y1 - y0} l {r} {y1 - y0} "
                         f"b 0 {y1 - y0} 0 {y1 - y0} 0 {y1 - y0 - r} l 0 {r} b 0 0 0 0 {r} 0")
                box = ass_color(s.get("caption_box_color", "#2E2017"))
                lines.append(f"Dialogue: 0,{ass_time(ov['a'])},{ass_time(ov['b'])},Clean,,0,0,0,,"
                             f"{{\\an7\\pos({x0},{y0})\\bord0\\shad0\\blur0\\1c{box}\\1a&H30&\\fad(120,160)\\p1}}{shape}{{\\p0}}")
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
    an_block = {"left": 7, "right": 9}.get(lay["align"], 8)
    for li, ln in enumerate(lay["lines"]):
        color = gold if ln["gold"] else ass_color(s.get("caption_color", "#FFFFFF"))
        first = idx[id(ln["words"][0])]
        if per_line:
            x, ly = ln["x"], ln["top"]
            an = {"left": 7, "center": 8, "right": 9}[ln["align"]]
        else:
            x, ly, an = lay["x"], y, an_block
        # topo da linha no libass = topo da "célula" da fonte; no navegador (line-height .98) a letra fica 0,26 em
        # mais acima — corrige para a exportação ficar igual à prévia
        ly -= ln["size"] * 0.26
        for k in range(first, len(toks)):
            a = times[k]
            b = times[k + 1] if k + 1 < len(toks) else ov["b"]
            if b - a < 0.02:
                continue
            parts = []
            for t in ln["words"]:
                hidden = idx[id(t)] > k
                parts.append(("{\\alpha&HFF&}" if hidden else "{\\alpha&H00&}") + cfmt(t))
            pos = f"\\pos({x:.0f},{ly:.0f})"
            anim = ""
            if k == first:                      # a linha está entrando
                enter = ln.get("enter")
                d = 60 if enter else 0
                if enter in ("top", "left", "right"):
                    dx, dy = {"top": (0, -d), "left": (-d * 1.4, 0), "right": (d * 1.4, 0)}[enter]
                    pos = f"\\move({x + dx:.0f},{ly + dy:.0f},{x:.0f},{ly:.0f},0,{ENTER_MS})"
                elif enter == "rise":             # valor subindo por trás da cabeça
                    pos = f"\\move({x:.0f},{ly + ln['size'] * 0.9:.0f},{x:.0f},{ly:.0f},0,{ENTER_MS + 180})"
                elif enter == "zoom":
                    anim += f"\\fscx135\\fscy135\\t(0,{ENTER_MS + 60},\\fscx100\\fscy100)"
                blur0 = 12 if enter else 6
                anim += f"\\blur{blur0 + ln['size'] * 0.16:.1f}\\t(0,{ENTER_MS},\\blur{ln['size'] * 0.16:.1f})\\fad({120 if enter else 90},0)"
            if k == len(toks) - 1:
                anim += "\\fad(0,160)" if k != first else ""
            out.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Emph,,0,0,0,,"
                       f"{{\\an{an}{pos}\\fs{round(ln['size'] * FONT_K)}\\fsp{-ln['size'] * 0.045:.1f}"
                       f"\\1c{color}{halo(ln['size'])}{anim}}}{' '.join(parts)}")
        y += heights[li]
    return out


CALOR_RGB, CALOR_ALPHA, CALOR_PERSON = "0xC2300E", 0.5, 0.25   # a mesma cor/força da prévia (app.js, #heat-tint)


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
    gs_on = any(o.get("type") == "greenscreen" or (o.get("type") == "media" and o.get("layout") == "topo")
                for o in comp["overlays"])
    scene_on = (s.get("bg_scene") or "none") != "none" or gs_on
    calor_on = any(o.get("type") == "calor" for o in comp["overlays"])
    needs_mask = s.get("background") in ("blur", "escuro") or scene_on or calor_on or any(has_behind(o) for o in comp["overlays"])
    # o CALOR usa o mesmo recorte da prévia (você + cadeira): o vermelho fica só atrás de você, igual nas duas
    mask = pdir / ("mask_fg.mp4" if scene_on or calor_on else "mask.mp4")
    if needs_mask and not mask.exists():
        if on_progress:
            on_progress(0.26, "Recortando você do fundo (só na primeira vez)…")
        prog = lambda x, m=None: on_progress and on_progress(0.26 + 0.2 * x, m or "Recortando você do fundo…")
        if scene_on or calor_on:
            from . import background
            background.build_fg_mask(pdir / project["source"]["file"], mask, on_progress=prog)
        else:
            segment.build_mask(pdir / project["source"]["file"], mask, on_progress=prog)
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
        if ov["template"] in ("carrossel3d", "prints_soma", "hook_cards", "slogan", "polaroid", "produto_oferta", "por_tras", "alcance", "guerra_peste"):
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

    def ovt(t):
        """Início de uma camada (B-roll, motion, luz) no grid de quadros, meio quadro ADIANTADO. O vídeo principal
        chega às junções com tempo em milésimos (16133, 16167 ms…) e a camada em 1/30 s (16133,33…): a cada 3
        quadros a camada ficava "um fio" à frente e a junção repetia o quadro anterior — B-roll/emoji travando."""
        return max(0.0, round(t * fps) / fps - 0.5 / fps)
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

    # Camadas (B-roll, fotos, motions, luz) entram por `movie=` DENTRO do filtro, não por `-i`: com `-i` o ffmpeg
    # decodifica todas de uma vez e guarda os quadros até a hora de cada uma (Liquid Death: 35 camadas = 22 GB, o
    # macOS matava o render e o que mais estivesse rodando). O `movie` só lê quando a camada é pedida.
    lz_n = [0]

    def lazy(*args):
        o, a, path = {}, list(args), None
        while a:
            k = a.pop(0)
            if k == "-i":
                path = str(a.pop(0))
            else:
                o[k] = a.pop(0)
        lab = f"lz{lz_n[0]}"
        lz_n[0] += 1
        q = "'" + path.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:") + "'"
        T = o.get("-t")
        if "%" in Path(path).name:                                   # sequência de PNGs (motion, luz)
            chain = f"movie={q}:f=image2,setpts=N/({o.get('-framerate', fps)})/TB"
        elif o.get("-loop") == "1":                                  # foto parada
            chain = f"movie={q},loop=loop=-1:size=1,setpts=N/({o.get('-framerate', fps)})/TB,trim=duration={T}"
        else:
            ss = float(o.get("-ss") or 0)
            chain = f"movie={q}" + (f":seek_point={ss:.3f},trim=start={ss:.3f}" if ss > 0 else "") + ",setpts=PTS-STARTPTS"
            if o.get("-stream_loop") and T:
                from .media import probe
                info = probe(path)
                avail = float(info.get("duration") or 0) - ss
                if 0.1 < avail < float(T) - 0.02:                   # o trecho é mais curto que a janela: repete
                    sf = float(info.get("fps") or 30)
                    chain += f",loop=loop=-1:size={int(avail * sf) + 2},setpts=N/({sf:.4f})/TB"
            if T:
                chain += f",trim=duration={T}"
        f.append(chain + f"[{lab}:v]")
        return lab

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
        # corte em quadro exato (timeline): recua 1/4 de quadro para pegar exatamente os quadros k..m-1
        q = 0.25 / fps
        return (f"[{label}{k}]trim=start={max(0.0, p['start'] - q):.6f}:end={p['end'] - q:.6f},setpts=PTS-STARTPTS,"
                f"crop=w=trunc(iw*{cw:.5f}/2)*2:h=trunc(ih*{ch:.5f}/2)*2:x=(iw-ow)/2:y=(ih-oh)*0.4,"
                f"scale={W}:{H}:flags=lanczos,setsar=1,fps={fps},"
                # o filtro fps descarta o ÚLTIMO quadro de cada trecho; com ~20 trechos a imagem ia se adiantando
                # ao som (até ~0,6 s). Repete o último quadro e corta em EXATAMENTE N quadros = duração do áudio
                f"tpad=stop_mode=clone:stop=2,trim=end_frame={max(1, round((p['end'] - p['start']) * fps))},"
                f"setpts=N/({fps}*TB){kb},{fmt}[{'m' if is_mask else 'v'}{k}]")

    from . import background
    plate = background.plate_path(project, pdir) if mask_idx is not None else None
    mask_src = f"{mask_idx}:v"
    if plate is not None:
        # CENÁRIO: você + cadeira (máscara) sobre a foto desfocada, no quadro ORIGINAL — os cortes e zooms
        # vêm depois, então o fundo aproxima junto com você, como numa câmera de verdade
        SW, SH = int(src["width"]) // 2 * 2, int(src["height"]) // 2 * 2
        sfps = src.get("fps") or 30
        pidx = add_input("-loop", "1", "-framerate", f"{sfps}", "-t", f"{src['duration'] + 1:.3f}", "-i", str(plate))
        gains = background.match_gains(mask, plate)
        f.append(f"[{mask_idx}:v]split=2[mbg][mrest]")
        mask_src = "mrest"
        clean = pdir / "fg_clean.mp4"
        if clean.exists():                      # você com a borda descontaminada (sem a linha branca)
            fg_label = f"{add_input('-i', str(clean))}:v"
        else:
            f.append(f"[0:v]{rotate}null[srcr]")
            fg_label = "srcr"
        f.append(background.composite_graph(fg_label, "mbg", f"{pidx}:v", "scene", SW, SH, sfps,
                                            float(s.get('bg_blur', SW * 0.011)), gains))
        f.append(f"[scene]split={n}" + "".join(f"[s{k}]" for k in range(n)))
    else:
        f.append(f"[0:v]{rotate}split={n}" + "".join(f"[s{k}]" for k in range(n)))
    for k, p in enumerate(pieces):
        f.append(piece_chain("s", k, p))
    if mask_idx is not None:
        f.append(f"[{mask_src}]split={n}" + "".join(f"[ms{k}]" for k in range(n)))
        for k, p in enumerate(pieces):
            f.append(piece_chain("ms", k, p, is_mask=True))
    if has_audio:
        f.append(f"[0:a]asplit={n}" + "".join(f"[r{k}]" for k in range(n)))
        for k, p in enumerate(pieces):
            d = p["end"] - p["start"]
            # emenda contínua no original (mesmo trecho, ou pedaço vizinho de uma "divisão"): sem fade no áudio
            cont_prev = k > 0 and (pieces[k - 1]["g"] == p["g"] or abs(pieces[k - 1]["end"] - p["start"]) < 0.004)
            cont_next = k + 1 < n and (pieces[k + 1]["g"] == p["g"] or abs(pieces[k + 1]["start"] - p["end"]) < 0.004)
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
        hold = float(s.get("end_hold", 0.6) or 0.6)
        if hold > 0.8:
            # fim estendido (B-roll final segurando com a música): a voz some logo depois da última palavra — o que
            # a câmera gravou depois (mão no celular, barulho) não entra
            join("a", "voice0r", "a")
            dset_ = {i for i, w in enumerate(project["words"]) if w.get("deleted")}
            lw = max((w["end"] for i, w in enumerate(project["words"]) if i not in dset_ and w.get("w", "").strip()), default=0)
            t_lw = timeline.to_output(pieces, lw)
            f.append(f"[voice0r]afade=t=out:st={t_lw + 0.12:.3f}:d=0.3[voice0]")
        else:
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
    topo_mask = {}
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
        # CALOR (Epicteto 20/10: "o fundo fosse ficando vermelho, esquentando, de forma natural e não brega, sem
        # emoji"): ATRÁS de você o fundo vai ganhando uma camada vermelho-brasa que sobe devagar; você fica intacto
        for j, o in enumerate(o for o in comp["overlays"] if o.get("type") == "calor"):
            a, b = o["a"], max(o["a"] + 0.6, o["b"])
            ramp = max(0.6, (b - a) * float(o.get("ramp", 0.75)))
            al = float(o.get("strength", CALOR_ALPHA))
            f.append(f"color=c={CALOR_RGB}:s={W}x{H}:r={fps}:d={b + 0.5:.3f},format=yuva420p,colorchannelmixer=aa={al:.3f},"
                     f"fade=t=in:st={a:.3f}:d={ramp:.3f}:alpha=1,fade=t=out:st={b - 0.25:.3f}:d=0.25:alpha=1[heat{j}]")
            f.append(f"[{bgl}][heat{j}]overlay=enable='between(t,{a:.3f},{b:.3f})':eof_action=pass,format=yuv420p[bgh{j}]")
            bgl = f"bgh{j}"
        if any(has_behind(o) for o in comp["overlays"]):
            behind = pdir / "render_behind.ass"
            build_behind_ass(comp, W, H, behind)
            f.append(f"[bg0]ass='{filter_path(behind)}':fontsdir=fonts[bg1]")
            bgl = "bg1"
        gss = [o for o in comp["overlays"] if o.get("type") == "greenscreen" and o.get("file")
               and (pdir / "assets" / o["file"]).exists()]
        tops = [o["id"] for o in comp["overlays"] if o.get("type") == "media" and o.get("layout") == "topo" and o.get("file")]
        if gss or tops:
            f.append(f"[mask0]split={len(gss) + len(tops) + 1}[mask0c]" + "".join(f"[mgs{j}]" for j in range(len(gss)))
                     + "".join(f"[mtp_{i}]" for i in tops))
        topo_mask = {i: f"mtp_{i}" for i in tops}
        f.append(f"[{'mask0c' if gss or tops else 'mask0'}]gblur=sigma=1.5,format=gray[mk]")
        f.append("[pa]format=yuva420p[pa2]")
        f.append("[pa2][mk]alphamerge[person]")
        f.append(f"[{bgl}][person]overlay=format=auto,format=yuv420p[cut]")
        cur = "cut"
        # ...e ele também esquenta um pouco (25% do vermelho do fundo): a cabeça "esquenta" e a borda do recorte
        # (restinho do fundo antigo no cabelo) não fica azulada contra o vermelho
        for j, o in enumerate(o for o in comp["overlays"] if o.get("type") == "calor"):
            a, b = o["a"], max(o["a"] + 0.6, o["b"])
            ramp = max(0.6, (b - a) * float(o.get("ramp", 0.75)))
            al = float(o.get("strength", CALOR_ALPHA)) * CALOR_PERSON
            f.append(f"color=c={CALOR_RGB}:s={W}x{H}:r={fps}:d={b + 0.5:.3f},format=yuva420p,colorchannelmixer=aa={al:.3f},"
                     f"fade=t=in:st={a:.3f}:d={ramp:.3f}:alpha=1,fade=t=out:st={b - 0.25:.3f}:d=0.25:alpha=1[heatp{j}]")
            f.append(f"[{cur}][heatp{j}]overlay=enable='between(t,{a:.3f},{b:.3f})':eof_action=pass,format=yuv420p[cuth{j}]")
            cur = f"cuth{j}"

        # --- TELA VERDE: o print vira o fundo (rolando devagar se for comprido) e você fica no cantinho
        for j, o in enumerate(gss):
            a, b = o["a"], max(o["a"] + 0.5, o["b"])
            S = float(o.get("size", 0.52))
            img = pdir / "assets" / o["file"]
            from .media import probe as _pr
            iw, ih = (lambda i: (i["width"] or 1080, i["height"] or 1920))(_pr(img))
            # print de ponta a ponta (sem faixa clara do fundo nas laterais nem embaixo — parecia uma linha branca)
            fw = W // 2 * 2
            fh = int(ih * fw / iw) // 2 * 2
            top0 = 0
            if fh > H:                                 # print comprido: rola de cima para baixo durante a leitura
                top1 = H - fh
                yexp = (f"if(lt(t\\,{a + 0.6:.2f})\\,{top0}\\,if(gt(t\\,{b - 0.6:.2f})\\,{top1}\\,"
                        f"{top0}+({top1 - top0})*(t-{a + 0.6:.2f})/{max(0.1, b - a - 1.2):.2f}))")
            else:
                yexp = str(int((H - fh) * 0.42))
            idx = add_input("-loop", "1", "-framerate", f"{fps}", "-t", f"{total + 1:.3f}", "-i", str(img))
            f.append(f"[{idx}:v]split[gi{j}][gb{j}]")
            f.append(f"[gb{j}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28,"
                     f"eq=brightness=-0.22:saturation=0.8,format=yuv420p[gbg{j}]")
            f.append(f"[gi{j}]scale={fw}:{fh},format=yuva420p[gim{j}]")
            f.append(f"[gbg{j}][gim{j}]overlay=x=(W-w)/2:y='{yexp}':format=auto,format=yuv420p[gsi{j}]")
            # você recortado (com o microfone), menor, encostado no canto de baixo
            f.append(f"[{cur}]split[gsbase{j}][gsp{j}]")
            f.append(f"[mgs{j}]format=gray,lut=y='clip((val-90)*1.6\\,0\\,255)',gblur=sigma=1.2[gsm{j}]")
            f.append(f"[gsp{j}]format=yuva420p[gspa{j}];[gspa{j}][gsm{j}]alphamerge,scale=iw*{S:.3f}:ih*{S:.3f}[gsper{j}]")
            # um pouco para dentro da tela (rosto e ombros inteiros), encostado embaixo
            # colado no canto: um pouco para FORA da tela embaixo e na lateral (as bordas do recorte são macias e
            # deixavam uma linha clara do print entre você e a borda)
            xexp = f"-{int(W * 0.04)}" if o.get("corner", "bl") == "bl" else f"W-w+{int(W * 0.04)}"
            f.append(f"[gsi{j}][gsper{j}]overlay=x={xexp}:y=H-h+{int(H * 0.025)}:format=auto,format=yuva420p,"
                     f"null[gsc{j}]")
            f.append(f"[gsbase{j}][gsc{j}]overlay=enable='between(t,{a:.3f},{b:.3f})':format=auto,format=yuv420p[gsv{j}]")
            cur = f"gsv{j}"

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
    # junção entre duas telas divididas: a que sai termina meio quadro ANTES (sem sobreposição) — a que entra pega você
    # do vídeo já composto, e com as duas ligadas no mesmo quadro você saía "dentro" da anterior (a sala da TV 2×)
    SPL = ("topo", "meio", "tv")
    meds = sorted([o for o in comp["overlays"] if o.get("type") == "media" and o.get("file") and "a" in o], key=lambda o: o["a"])
    early = {x["id"] for x, y in zip(meds, meds[1:]) if x.get("layout") in SPL and y.get("layout") in SPL and abs(y["a"] - x["b"]) < 0.05}
    win, exit_up = {}, {}
    for j, ov in enumerate(comp["overlays"]):
        if ov.get("type") != "media" or not ov.get("file") or ov["id"] in motion_frames:
            continue
        fpath = pdir / "assets" / ov["file"]
        if not fpath.exists():
            continue
        dur = max(0.3, ov["b"] - ov["a"])
        is_img = kind_of(fpath) == "image"
        # sobra de 0,25 s no fim: o vídeo nunca acaba ANTES do fim da janela (senão, entre dois B-rolls,
        # você aparecia por 1–2 quadros — a prévia corta seco)
        vin = None
        if is_img:
            idx = lazy("-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.25:.3f}", "-i", str(fpath))
        else:
            start = float(ov.get("clip_start") or 0)
            shot = float(ov.get("shot_end") or 0) - start
            if 0.3 < shot < dur + 0.25:
                # o PLANO escolhido acaba antes da janela (ex.: a lata vira viatura de polícia): nunca invade a cena
                # seguinte do comercial. Toca mais devagar (até 0,6×) e, se ainda faltar, vai e volta ("bumerangue")
                # — NUNCA congela no último quadro ("travou legal o ativo", reclamação repetida no Liquid Death)
                idx = lazy("-ss", f"{start:.2f}", "-t", f"{shot - 0.05:.3f}", "-i", str(fpath))
                rate = max(0.6, shot / (dur + 0.25))
                nfr = max(2, int((shot - 0.05) * fps))
                # reverse/loop guardam TODOS os quadros na memória: reduz antes (lado menor ≤ 1080, yuv420p) — com o comercial
                # em 4K o ffmpeg chegou a 22 GB e o macOS matava o que mais estivesse rodando
                f.append(f"[{idx}:v]setpts=PTS-STARTPTS,fps={fps},trim=end_frame={nfr},"
                         f"scale='if(gt(iw,ih),-2,min(iw,1080))':'if(gt(iw,ih),min(ih,1080),-2)',format=yuv420p,split[bf{j}][br{j}]")
                f.append(f"[br{j}]reverse[brr{j}]")
                f.append(f"[bf{j}][brr{j}]concat=n=2:v=1:a=0,loop=loop=-1:size={2 * nfr}:start=0,"
                         f"setpts=N/({fps}*{rate:.4f})/TB,fps={fps},trim=duration={dur + 0.5:.3f}[shot{j}]")
                vin = f"shot{j}"
            else:
                idx = lazy("-ss", f"{start:.2f}", "-stream_loop", "-1", "-t", f"{dur + 0.25:.3f}", "-i", str(fpath))
        vin = vin or f"{idx}:v"
        layout0 = ov.get("layout") or ("card" if ov.get("print") else "full")
        if is_img and layout0 not in ("full", "card", "card3d"):
            # REGRA DELE: foto nunca parada — zoom in lento (os mesmos 6% da tela cheia e da prévia)
            try:
                from PIL import Image as _Im
                with _Im.open(fpath) as _im:
                    iw_, ih_ = _im.size
            except Exception:  # noqa: BLE001
                iw_, ih_ = 16, 9
            zh = 1440
            zw = even(zh * iw_ / ih_)
            nfr = int((dur + 0.25) * fps) + 1
            f.append(f"[{vin}]scale={zw}:{zh},zoompan=z='1+0.06*on/{nfr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                     f":d=1:s={zw}x{zh}:fps={fps}[kb{j}]")
            vin = f"kb{j}"
        frames_total = int(dur * fps) + 1
        push = f"zoompan=z='1+0.06*on/{frames_total}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
        layout = ov.get("layout") or ("card" if ov.get("print") else "full")
        tag = f"o{j}"
        if layout == "viral":
            # MODELO VIRAL (Reels): fundo ônix, o vídeo num quadro quadrado de cantos arredondados no centro,
            # a legenda cai dentro do quadro (parte de baixo) — o vídeo de apoio sempre MUDO
            cw_ = even(W * (0.88 if H > W else 0.56))
            chh = cw_ if H > W else even(H * 0.74)
            if H > W and ov.get("ar"):          # a tvzinha toma a proporção do ativo (nada de foto cortada)
                chh = even(cw_ / min(1.8, max(0.75, float(ov["ar"]))))
            r = int(cw_ * 0.07)
            # enquadra a parte de CIMA (rosto/produto) e deixa de fora as legendas que o vídeo do creator já tem
            fill = f"scale={cw_}:{chh}:force_original_aspect_ratio=increase,crop={cw_}:{chh}:(iw-ow)/2:(ih-oh)*0.12,fps={fps}"
            f.append(f"[{vin}]{fill},setsar=1,format=yuva420p,"
                     f"geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':"
                     f"a='255*lte(pow(max(0\\,max({r}-X\\,X-(W-1-{r})))\\,2)+pow(max(0\\,max({r}-Y\\,Y-(H-1-{r})))\\,2)\\,{r * r})'[vc{j}]")
            f.append(f"color=c=0x150C06:s={W}x{H}:r={fps}:d={dur + 0.25:.3f},format=yuva420p[vb{j}]")
            yy = int(H * 0.47 - chh / 2) if H > W else int((H - chh) / 2)
            f.append(f"[vb{j}][vc{j}]overlay=x=(W-w)/2:y={yy}:format=auto,format=yuva420p,"
                     f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[{tag}]")
            pos = "x=0:y=0"
        elif layout in ("topo", "meio") or (layout == "tv" and (pdir / "assets" / TV_SALA["file"]).exists()):
            # TELA DIVIDIDA (ativo HORIZONTAL), dois estilos (regra dele):
            #  topo = ativo nos 40% de cima, você 13% mais para baixo e o alto da sua cabeça (recorte, 82%) por cima
            #         da borda do ativo; legenda embaixo (~84%)
            #  meio = 50/50: ativo na metade de cima, você menor (zoom out) na de baixo, sem sobrepor; legenda NA divisa
            # em ambos, um DESFOQUE separa as duas cenas (faixa borrada e esfumada na divisa)
            meio = layout in ("meio", "tv")
            Ht = even(H * (ov.get("ht") or (0.42 if meio else TOPO_H)))
            a0, b0 = max(0.0, ov["a"] - 0.2), ov["b"] + 0.4
            if layout == "tv":
                # a sala de verdade em cima (a TV no rack, o abajur) com o comercial na tela; ele embaixo
                T = TV_SALA
                rs = min(float(ov.get("room_t") or 0), max(0.0, T["dur"] - dur - 0.3))
                ridx = lazy("-ss", f"{rs:.3f}", "-t", f"{dur + 0.3:.3f}", "-i", str(pdir / "assets" / T["file"]))
                ch_ = T["cw"] * Ht / W
                k_ = W / T["cw"]
                tw, th = even(T["sw"] * k_), even(T["sh"] * k_)
                # a tela verde vira TRANSPARENTE (chroma key) e o comercial fica ATRÁS da sala: a moldura da TV é a de
                # verdade, sem fresta verde cintilando ("deixando bordinhas da TV pra parecer mais realista", 19/10).
                # Mesma chave da prévia (backgrounds/tv_sala_alpha.webm: TV_KEY)
                f.append(f"[{ridx}:v]fps={fps},tpad=stop_mode=clone:stop_duration=2,"
                         f"crop={T['cw']}:{ch_:.0f}:'{T['x0']}+{T['vx']}*(t+{rs:.3f})':{T['y0']},format=rgba,{TV_KEY},"
                         f"scale={W}:{Ht},setsar=1[tvr{j}]")
                m_ = TV_MARGIN
                tw2, th2 = even((T["sw"] + 2 * m_) * k_), even((T["sh"] + 2 * m_) * k_)
                f.append(f"[{vin}]fps={fps},scale={tw2}:{th2}:force_original_aspect_ratio=increase,crop={tw2}:{th2},setsar=1,"
                         f"eq=brightness=0.02:saturation=1.05,"
                         f"pad={W}:{Ht}:{int((T['sx'] - m_) * k_)}:{int((T['sy'] - m_) * k_)}:color=black,format=yuva420p[tvc{j}]")
                f.append(f"[tvc{j}][tvr{j}]overlay=x=0:y=0:shortest=1,format=yuva420p,"
                         f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[ta{j}]")
            else:
                # o ativo PREENCHE a faixa (nada de cópia desfocada em cima/embaixo — reprovado); o que sobra na
                # largura é cortado do lado menos importante: `fx` 0 = alinha à esquerda, 0.5 = centro, 1 = direita
                afx = min(1.0, max(0.0, float(ov.get("fx", 0.5))))
                f.append(f"[{vin}]fps={fps},scale={W}:{Ht}:force_original_aspect_ratio=increase,"
                         f"crop={W}:{Ht}:(iw-ow)*{afx:.3f}:(ih-oh)/2,setsar=1,format=yuva420p,"
                         f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[ta{j}]")
            # o vídeo principal é picado em ANTES | JANELA | DEPOIS (concat no fim): sem isso o ffmpeg guardava na memória
            # todos os quadros do começo até a tela dividida entrar, para cada uma (22 GB no Liquid Death)
            EX = 0.35
            if ov.get("exit") == "up" and ov["b"] - ov["a"] > EX + 0.3:
                # SAI POR CIMA (Jung, estalo: "eu ocupasse a tela inteira… jogando isso do carro pra cima até sumir"):
                # a dividida acaba EX antes; ele volta inteiro e a faixa do ativo sobe por cima dele até sumir
                exit_up[ov["id"]] = (ov["b"] - EX, ov["b"], even(H * (ov.get("ht") or 0.42)))
                ov = {**ov, "b": ov["b"] - EX}
            hb_ = -0.5 / fps if ov["id"] in early else 0.5 / fps
            k0, k1 = math.ceil((ov["a"] - 0.5 / fps) * fps - 1e-6), math.floor((ov["b"] + hb_) * fps + 1e-6)
            wA, wB = (k0 - 0.5) / fps, (k1 + 0.5) / fps
            win[ov["id"]] = (wA, wB, f"tA{j}", f"tC{j}")
            f.append(f"[{cur}]split=5[tA{j}][tbr{j}][tC{j}][tp{j}][tq{j}]")
            f.append(f"[tbr{j}]trim=start={wA:.4f}:end={wB:.4f}[tb{j}]")
            if meio:
                sw, sh_ = even(W * MEIO_S), even(H * MEIO_S)
                yo = int(H * ov["yo"]) if ov.get("yo") is not None else int(Ht + H * 0.015 - H * HEAD_TOP * MEIO_S)
                # sem fonte de cor infinita (ela se acumulava na memória até o trecho começar e travava o render)
                f.append(f"[tp{j}]trim=start={a0:.3f}:end={b0:.3f},scale={sw}:{sh_},"
                         f"pad={W}:{yo + sh_}:{(W - sw) // 2}:{yo}:color=0x150C06,crop={W}:{H}:0:0,format=yuva420p[ts{j}]")
                f.append(f"[tq{j}]nullsink")
            else:
                dy = even(H * (ov["dy"] if ov.get("dy") is not None else TOPO_DY))
                if dy >= 0:
                    shift = f"crop={W}:{H - dy}:0:0,pad={W}:{H}:0:{dy}:color=0x150C06"
                else:                                  # ele SOBE: tira o alto do quadro e completa embaixo
                    shift = f"crop={W}:{H + dy}:0:{-dy},pad={W}:{H}:0:0:color=0x150C06"
                f.append(f"[tp{j}]trim=start={a0:.3f}:end={b0:.3f},{shift},format=yuva420p[ts{j}]")
            if ov["id"] in exit_up:
                f.append(f"[ta{j}]split[ta{j}m][tax{j}]")
                f.append(f"[ts{j}][ta{j}m]overlay=x=0:y=0:eof_action=pass:format=auto[tsa{j}]")
            else:
                f.append(f"[ts{j}][ta{j}]overlay=x=0:y=0:eof_action=pass:format=auto[tsa{j}]")
            # desfoque na divisa
            bh = even(H * 0.06)
            f.append(f"[tsa{j}]split[tsx{j}][tsy{j}]")
            f.append(f"[tsy{j}]crop={W}:{bh}:0:{Ht - bh // 2},gblur=sigma={W / 60:.1f}"
                     + (",eq=brightness=-0.10" if meio else "") +
                     f",format=yuva420p,geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':a='255*sin(PI*Y/H)'[tsb{j}]")
            f.append(f"[tsx{j}][tsb{j}]overlay=x=0:y={Ht - bh // 2}:format=auto[tsc{j}]")
            mlab = topo_mask.get(ov["id"]) if not meio else None
            if mlab:
                dy = even(H * (ov["dy"] if ov.get("dy") is not None else TOPO_DY))
                shift = (f"crop={W}:{H - dy}:0:0,pad={W}:{H}:0:{dy}" if dy >= 0 else f"crop={W}:{H + dy}:0:{-dy},pad={W}:{H}:0:0")
                f.append(f"[{mlab}]trim=start={a0:.3f}:end={b0:.3f},format=gray,lut=y='clip((val-90)*1.6\\,0\\,255)',"
                         f"gblur=sigma=1.2,{shift}:color=black[tm{j}]")
                f.append(f"[tq{j}]trim=start={a0:.3f}:end={b0:.3f},{shift},format=yuva420p[tqs{j}]")
                f.append(f"[tqs{j}][tm{j}]alphamerge,colorchannelmixer=aa=0.82[tper{j}]")
                f.append(f"[tsc{j}][tper{j}]overlay=format=auto,format=yuva420p[{tag}]")
            else:
                if not meio:
                    f.append(f"[tq{j}]nullsink")
                f.append(f"[tsc{j}]format=yuva420p[{tag}]")
            cur = f"tb{j}"
            pos = "x=0:y=0"
        elif layout == "duo" and ov.get("file2") and (pdir / "assets" / ov["file2"]).exists():
            # TELA DIVIDIDA ENTRE DOIS ATIVOS (pedido dele: o celular em cima, a turma conversando embaixo)
            hh = even(H / 2)
            f2 = pdir / "assets" / ov["file2"]
            if kind_of(f2) == "image":
                idx2 = lazy("-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.25:.3f}", "-i", str(f2))
                nfr2 = int((dur + 0.25) * fps) + 1
                try:
                    from PIL import Image as _Im
                    with _Im.open(f2) as _im:
                        zw2 = even(1440 * _im.size[0] / _im.size[1])
                except Exception:  # noqa: BLE001
                    zw2 = 2560
                f.append(f"[{idx2}:v]scale={zw2}:1440,zoompan=z='1+0.06*on/{nfr2}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                         f":d=1:s={zw2}x1440:fps={fps}[kb2{j}]")
            else:
                idx2 = lazy("-ss", f"{float(ov.get('clip_start2') or 0):.2f}", "-stream_loop", "-1", "-t", f"{dur + 0.25:.3f}", "-i", str(f2))
            fx1, fx2 = (min(1.0, max(0.0, float(ov.get(k, 0.5)))) for k in ("fx", "fx2"))
            f.append(f"[{vin}]scale={W}:{hh}:force_original_aspect_ratio=increase,crop={W}:{hh}:(iw-ow)*{fx1:.3f}:(ih-oh)/2,setsar=1,fps={fps}[du1{j}]")
            in2 = f"kb2{j}" if kind_of(f2) == "image" else f"{idx2}:v"
            f.append(f"[{in2}]scale={W}:{H - hh}:force_original_aspect_ratio=increase,crop={W}:{H - hh}:(iw-ow)*{fx2:.3f}:(ih-oh)/2,setsar=1,fps={fps}[du2{j}]")
            f.append(f"[du1{j}][du2{j}]vstack=2,split[dux{j}][duy{j}]")
            bh = even(H * 0.06)
            f.append(f"[duy{j}]crop={W}:{bh}:0:{hh - bh // 2},gblur=sigma={W / 60:.1f},eq=brightness=-0.10,format=yuva420p,"
                     f"geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':a='255*sin(PI*Y/H)'[duz{j}]")
            f.append(f"[dux{j}][duz{j}]overlay=x=0:y={hh - bh // 2},format=yuva420p,"
                     f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[{tag}]")
            pos = "x=0:y=0"
        elif layout == "tv":
            # TV DE VERDADE (pedido dele p/ o comercial): moldura desenhada (app/static/img/tv.png, tela 16:9 em
            # 60,50 880×495 de 1000×700) com o vídeo INTEIRO na tela; fundo ônix; legenda desce (timeline)
            tvw = even(W * TV_W); k = tvw / 1000
            tvh = even(700 * k); sx, sy, sw, sh = int(60 * k), int(50 * k), even(880 * k), even(495 * k)
            ty = int(H * TV_Y - tvh / 2)
            tv = lazy("-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.25:.3f}", "-i", str(Path(__file__).parent / "static" / "img" / "tv.png"))
            f.append(f"[{vin}]scale={sw}:{sh}:force_original_aspect_ratio=decrease,pad={sw}:{sh}:(ow-iw)/2:(oh-ih)/2:color=black,"
                     f"setsar=1,fps={fps}[tvs{j}]")
            f.append(f"[{tv}:v]scale={tvw}:{tvh},format=rgba[tvf{j}]")
            f.append(f"color=c=0x150C06:s={W}x{H}:r={fps}:d={dur + 0.25:.3f}[tvb{j}]")
            f.append(f"[tvb{j}][tvs{j}]overlay=x={(W - tvw) // 2 + sx}:y={ty + sy}:shortest=1[tvx{j}]")
            f.append(f"[tvx{j}][tvf{j}]overlay=x={(W - tvw) // 2}:y={ty}:shortest=1,format=yuva420p,"
                     f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[{tag}]")
            pos = "x=0:y=0"
        elif layout == "pip":
            pw = even(W * (0.5 if W > H else 0.72))
            ph = even(pw * 9 / 16) if W > H else even(pw * 10 / 16)
            f.append(f"[{vin}]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},setsar=1,"
                     f"fps={fps},format=yuva420p,settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[{tag}]")
            pos = "x=(W-w)/2:y=H*0.12" if H > W else "x=W-w-48:y=48"
        elif layout in ("card", "card3d"):
            cw_, ch_ = even(W * (0.86 if H > W else 0.74)), even(H * (0.6 if H > W else 0.78))
            f.append(f"[{vin}]split[cb{j}][cf{j}]")
            f.append(f"[cb{j}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,"
                     f"eq=brightness=-0.25:saturation=0.8,setsar=1[cbb{j}]")
            f.append(f"[cf{j}]scale={cw_}:{ch_}:force_original_aspect_ratio=decrease,setsar=1[cff{j}]")
            f.append(f"[cbb{j}][cff{j}]overlay=(W-w)/2:(H-h)/2,{push},format=yuva420p,"
                     f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[{tag}]")
            pos = "x=0:y=0"
        else:
            fill = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},{push}"
                    if is_img else f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                                   f"crop={W}:{H}:(iw-ow)*{min(1.0, max(0.0, float(ov.get('fx', 0.5)))):.3f}:(ih-oh)/2,fps={fps}")
            f.append(f"[{vin}]{fill},setsar=1,format=yuva420p,"
                     f"settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[{tag}]")
            pos = "x=0:y=0"
        # janelas encostadas se sobrepõem meio quadro (o próximo B-roll vem por cima): troca seca, sem buraco
        ha = 0.5 / fps
        hb = -ha if ov["id"] in early else ha
        f.append(f"[{cur}][{tag}]overlay={pos}:enable='between(t,{ov['a'] - ha:.4f},{ov['b'] + hb:.4f})':eof_action=pass,"
                 f"format=yuv420p[b{j}]")
        cur = f"b{j}"
        if ov["id"] in win:                                  # tela dividida: ANTES + janela + DEPOIS de volta num fio só
            wA, wB, la, lc = win[ov["id"]]
            segs = []
            if wA > 0.5 / fps:
                f.append(f"[{la}]trim=end={wA:.4f},setpts=PTS-STARTPTS[{la}s]")
                segs.append(f"[{la}s]")
            else:
                f.append(f"[{la}]nullsink")
            f.append(f"[{cur}]setpts=PTS-STARTPTS[{cur}s]")
            segs.append(f"[{cur}s]")
            if wB < total - 0.5 / fps:
                f.append(f"[{lc}]trim=start={wB:.4f},setpts=PTS-STARTPTS[{lc}s]")
                segs.append(f"[{lc}s]")
            else:
                f.append(f"[{lc}]nullsink")
            f.append("".join(segs) + f"concat=n={len(segs)}:v=1:a=0[{cur}c]")
            cur = f"{cur}c"
            if ov["id"] in exit_up:
                e0, e1, eh = exit_up[ov["id"]]
                f.append(f"[{cur}][tax{j}]overlay=x=0:y='-(t-{e0:.4f})/{e1 - e0:.4f}*{eh}':"
                         f"enable='between(t,{e0:.4f},{e1:.4f})':eof_action=pass,format=yuv420p[{cur}x]")
                cur = f"{cur}x"

    # --- motions (sequências PNG com transparência)
    for j, ov in enumerate(comp["overlays"]):
        d = motion_frames.get(ov.get("id"))
        if not d:
            continue
        idx = lazy("-framerate", str(fps), "-i", str(Path(d) / "%05d.png"))
        f.append(f"[{idx}:v]format=yuva420p,settb=AVTB,setpts=PTS-STARTPTS+{ovt(ov['a']):.5f}/TB[mo{j}]")
        f.append(f"[{cur}][mo{j}]overlay=0:0:enable='between(t,{ov['a'] - 0.5 / fps:.4f},{ov['b']:.3f})':eof_action=repeat,"
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
        idx = lazy("-framerate", f"{fps:g}", "-i", str(Path(d) / "%05d.png"))
        f.append(f"[{idx}:v]format=rgba,scale={W}:{H},settb=AVTB,setpts=PTS-STARTPTS+{ovt(t0):.5f}/TB[lk{j}]")
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
    vol = float(s.get("sfx_volume") if s.get("sfx_volume") is not None else 0.9)
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
        gain = min(1.0, vol * float(ov.get("volume", 1.0)) * 10 ** (float(meta.get("gain", -6)) / 20) * 1.6)  # = prévia
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"volume={gain:.3f},adelay={ms}:all=1[fx{j}]")
        sfx_labels.append(f"fx{j}")
    from . import music as music_mod
    speed = float(s.get("speed", 1.0) or 1.0)
    # com velocidade ≠ 1 a música entra DEPOIS de acelerar a voz (ver render) — nunca é acelerada
    mus_f, mus_label = ([], None) if abs(speed - 1.0) >= 0.001 else music_mod.filters(project, pdir, add_input, total)
    has_music = mus_label is not None
    if abs(speed - 1.0) < 0.001 and music_mod.clips(project) and not has_music:
        raise RuntimeError("O projeto tem música, mas o arquivo dela não foi encontrado — exportação cancelada "
                           "(nunca exportar sem a música).")
    voice_main = voice
    if sfx_labels:
        f.append(f"[{voice_main}]" + "".join(f"[{x}]" for x in sfx_labels)
                 + f"amix=inputs={len(sfx_labels) + 1}:duration=first:normalize=0[vfx]")
        mixed = "vfx"
    else:
        mixed = voice_main
    if has_music:          # música em volume constante, como na prévia (sem "ducking" bombeando)
        f.extend(mus_f)
        f.append(f"[{mixed}][{mus_label}]amix=inputs=2:duration=first:normalize=0[mix]")
        mixed = "mix"
    # sem loudnorm dinâmico aqui (ele "bombeava" a voz): o volume é acertado depois, com ganho FIXO (ver render)
    f.append(f"[{mixed}]aresample=48000[aout]")

    script = pdir / "render_filter.txt"
    script.write_text(";\n".join(f), encoding="utf-8")
    vopts = ["-r", f"{fps}", *(["-s", f"{even(W * scale)}x{even(H * scale)}"] if scale != 1.0 else []),
             "-c:v", "h264_videotoolbox", "-b:v", "12M", "-allow_sw", "1", "-profile:v", "high"]
    # o vídeo sai num arquivo e o áudio em WAV (1x); render() acelera a voz (se speed ≠ 1), mistura a música
    # (se speed ≠ 1) e acerta o volume com ganho fixo — tudo para soar IGUAL à prévia
    if abs(speed - 1.0) >= 0.001:
        script.write_text(script.read_text(encoding="utf-8").replace("[vout]", "[vpre]", 1)
                          + f";\n[vpre]setpts=PTS/{speed:.4f},fps={fps}:round=near[vout]", encoding="utf-8")
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
        if on_progress:
            on_progress(0.99, "Finalizando o áudio…")
        finish_audio(project, Path(pdir), vtmp, atmp, Path(out_path), speed)
    except Exception:
        Path(out_path).unlink(missing_ok=True)   # não deixa arquivo quebrado na pasta de exportações
        raise
    finally:
        vtmp.unlink(missing_ok=True)
        atmp.unlink(missing_ok=True)
    check_music(project, Path(pdir), Path(out_path), speed)
    write_credits(project, Path(out_path))


def _ff(*args):
    r = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])
    return r


def finish_audio(project, pdir, vtmp, atmp, out_path, speed, target=-14.0):
    """Áudio final igual ao da prévia: a voz acelera com WSOLA (atempo — o mesmo tipo de algoritmo do navegador,
    sem o timbre "metálico" do Rubber Band/denoise), a música entra em 1x e o volume sobe/desce com UM ganho fixo
    (loudnorm dinâmico mudava a dinâmica da fala). Um limitador só segura picos acima de -1 dBTP."""
    import json as _json
    work = atmp
    if abs(speed - 1.0) >= 0.001:
        sped = atmp.with_suffix(".rapida.wav")
        _ff("-i", str(atmp), "-af", f"atempo={speed:.4f}", "-c:a", "pcm_s16le", str(sped))
        work = sped
        from . import music as music_mod
        ins = ["-i", str(work)]

        def add_in(*args):
            ins.extend(args)
            return sum(1 for x in ins if x == "-i") - 1
        total_edit = timeline.compute(project)["duration"]
        mf, ml = music_mod.filters(project, pdir, add_in, total_edit, speed)
        if music_mod.clips(project) and not ml:
            raise RuntimeError("O projeto tem música, mas o arquivo dela não foi encontrado — exportação cancelada "
                               "(nunca exportar sem a música).")
        if ml:
            # (music.filters numera as entradas a partir de 0 = voz; ajusta para a lista local)
            mixed = atmp.with_suffix(".mix.wav")
            fc = ";".join(mf + [f"[0:a][{ml}]amix=inputs=2:duration=first:normalize=0[a]"])
            _ff(*ins, "-filter_complex", fc, "-map", "[a]", "-c:a", "pcm_s16le", str(mixed))
            work = mixed
    # mede a loudness integrada e aplica ganho fixo até -14 LUFS (padrão Reels)
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(work), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    try:
        m = _json.loads(r[r.rindex("{"):r.rindex("}") + 1])
        # sobe até -14 LUFS, mas nunca a ponto de o pico passar de -1 dBTP (assim nada é comprimido/limitado)
        gain = min(target - float(m["input_i"]), -1.0 - float(m["input_tp"]))
    except Exception:  # noqa: BLE001
        gain = 0.0
    gain = max(-12.0, min(12.0, gain))
    _ff("-i", str(vtmp), "-i", str(work), "-map", "0:v", "-map", "1:a",
        "-af", f"volume={gain:.2f}dB",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path))
    for x in (atmp.with_suffix(".rapida.wav"), atmp.with_suffix(".mix.wav")):
        x.unlink(missing_ok=True)


def check_music(project, pdir, out_path, speed=1.0):
    """Confere no MP4 PRONTO que a música está lá (regra do usuário: "ela tem que ir sempre junto"). Mede quanto
    da faixa original existe no áudio final (projeção do sinal); ausente → apaga o MP4 e dá erro."""
    import numpy as np
    from . import music as music_mod
    clips = music_mod.clips(project)
    if not clips:
        return None
    c = max(clips, key=lambda c: float(c.get("dur", 0)))
    path = music_mod.path_of(c, pdir)
    sr = 8000
    pcm = lambda args: np.frombuffer(subprocess.run([FFMPEG, "-v", "error", *args, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                                                    capture_output=True).stdout, np.int16).astype(np.float32)
    t0 = float(c.get("start", 0)) / speed + 1.0
    dur = min(30.0, float(c.get("dur", 0)) / speed - 2.5)
    if dur < 3:
        return None
    out = pcm(["-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(out_path)])
    ref = pcm(["-ss", f"{float(c.get('in', 0)) + 1.0:.3f}", "-t", f"{dur:.3f}", "-i", str(path)])
    n = min(len(out), len(ref))
    if n < sr:
        return None
    out, ref = out[:n], ref[:n]
    best = max((abs(float(np.dot(out, np.roll(ref, lag))) / (float(np.dot(ref, ref)) + 1e-9)), lag)
               for lag in range(-sr // 10, sr // 10 + 1, sr // 400))
    k = best[0]
    if k < 0.25 * min(1.0, float(c.get("vol", 0.18)) * 1.6):
        Path(out_path).unlink(missing_ok=True)
        raise RuntimeError("A música não está no vídeo exportado — exportação cancelada (nunca sem a música).")
    level = 20 * np.log10(k * np.sqrt((ref ** 2).mean()) / (np.sqrt((out ** 2).mean()) + 1e-9) + 1e-9)
    print(f"Música conferida no MP4: presente, ~{abs(level):.0f} dB abaixo do total.")
    return level


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
    from .background import credit_of
    if credit_of(project):
        lines.append("- " + credit_of(project))
    from .music import credits as music_credits
    lines += ["- Música: " + c for c in music_credits(project)]
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

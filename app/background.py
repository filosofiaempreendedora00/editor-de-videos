"""Fundo trocado (cenário): você e a cadeira ficam, o resto vira outro ambiente.

Como fica realista (sem gerar imagem por IA — foto REAL, que engana o olho):
- recorte de alta qualidade (U²-Net humano, local) quadro a quadro + "máscara fixa" do que fica parado na frente
  da câmera quase o vídeo todo (a cadeira), com suavização no tempo (sem tremer) e borda "apertada" (sem halo
  da parede original);
- a foto do cenário é desfocada como numa lente de celular (profundidade de campo), escurecida um pouco
  (o fundo nunca é mais claro que você), com granulação igual à do vídeo;
- o cenário entra ANTES dos cortes/zooms: quando o vídeo dá zoom, o fundo aproxima junto (como numa câmera real);
- a cor final (grade/look) é aplicada por cima de tudo — você e o fundo ficam com a mesma "luz".
"""
import json
import subprocess
from pathlib import Path

import numpy as np

from .media import FFMPEG, probe

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "backgrounds"
MODELS = ROOT / "models"

# cenários prontos (fotos reais, licença livre — o crédito vai no .creditos.txt da exportação)
SCENES = [
    {"slug": "biblioteca", "name": "Biblioteca clássica (padrão)",
     "desc": "Long Room (Trinity College, Dublin): corredor de madeira, estantes até o teto, bustos de mármore",
     "file": "Long_Room_Interior,_Trinity_College_Dublin,_Ireland_-_Diliff.jpg",
     "credit": "Diliff — Wikimedia Commons, CC BY-SA 4.0", "focus_x": 0.5, "focus_y": 0.55},
    {"slug": "gabinete", "name": "Gabinete real",
     "desc": "Real Gabinete Português de Leitura (Rio): estantes douradas em três andares",
     "file": "2018_Rio_de_Janeiro_Interior_do_Real_Gabinete_Portugu%C3%AAs_de_Leitura.jpg",
     "credit": "Wikimedia Commons, CC BY-SA 4.0", "focus_x": 0.5, "focus_y": 0.6},
    {"slug": "biblioteca_escura", "name": "Biblioteca escura",
     "desc": "Abadia de Admont: estantes antigas na penumbra",
     "file": "Admont_Abbey_Library_books.jpg",
     "credit": "Wikimedia Commons, CC BY-SA 4.0", "focus_x": 0.55, "focus_y": 0.5},
]
DEFAULT_SCENE = "biblioteca"


def scene(slug):
    return next((s for s in SCENES if s["slug"] == slug), None)


def ensure_plate(slug):
    """Baixa (uma vez) a foto do cenário em boa resolução."""
    import httpx
    sc = scene(slug)
    if not sc:
        raise ValueError(f"cenário desconhecido: {slug}")
    BG_DIR.mkdir(exist_ok=True)
    out = BG_DIR / f"{slug}.jpg"
    if not out.exists():
        url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{sc['file']}?width=2400"
        r = httpx.get(url, timeout=120, follow_redirects=True, headers={"User-Agent": "EditorDeVideos/0.3 (local)"})
        r.raise_for_status()
        out.write_bytes(r.content)
    return out


def thumb(slug):
    """Miniatura local (servida pelo editor) do cenário."""
    out = BG_DIR / f"{slug}.thumb.jpg"
    if not out.exists():
        src = ensure_plate(slug)
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf",
                        "scale=360:480:force_original_aspect_ratio=increase,crop=360:480", "-q:v", "4", str(out)],
                       check=True)
    return out


def plate_path(project, pdir):
    """Imagem do cenário escolhido: um dos prontos ou um arquivo seu (assets/)."""
    s = project.get("settings", {}).get("bg_scene") or "none"
    if s == "none":
        return None
    if s.startswith("file:"):
        p = Path(pdir) / "assets" / s[5:]
        return p if p.exists() else None
    return ensure_plate(s)


def credit_of(project):
    s = project.get("settings", {}).get("bg_scene") or "none"
    sc = scene(s)
    return f"Cenário: {sc['desc']} — {sc['credit']}" if sc else None


# ---------------------------------------------------------------- recorte (você + cadeira)

def _session():
    import os
    os.environ.setdefault("U2NET_HOME", str(MODELS))
    from rembg import new_session
    for prov in (["CoreMLExecutionProvider", "CPUExecutionProvider"], ["CPUExecutionProvider"]):
        try:
            return new_session("u2net_human_seg", providers=prov)
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("não consegui carregar o modelo de recorte")


import threading
_mask_locks = {}


def build_fg_mask(src, out, on_progress=None):
    """mask_fg.mp4 (tons de cinza, mesmo tamanho/tempo do original): branco = você + cadeira."""
    lock = _mask_locks.setdefault(str(out), threading.Lock())
    with lock:
        if Path(out).exists():
            return out
        tmp = Path(out).with_suffix(".part.mp4")
        _build_fg_mask(src, tmp, on_progress)
        if Path(tmp).with_suffix(".json").exists():
            Path(tmp).with_suffix(".json").replace(Path(out).with_suffix(".json"))
        tmp.replace(out)
        return out


def _build_fg_mask(src, out, on_progress=None):
    from PIL import Image
    from rembg import remove
    info = probe(src)
    w, h, fps = info["width"], info["height"], info["fps"] or 30
    total = max(1, int(info["duration"] * fps))
    sess = _session()

    def frames():
        p = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(src), "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        n = w * h * 3
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        p.wait()

    def seg(fr):
        m = remove(Image.fromarray(fr), session=sess, only_mask=True, post_process_mask=False)
        return np.asarray(m.resize((w, h)), np.float32) / 255.0

    # 1) máscara fixa: o que está na frente da câmera em >= 75% de ~20 quadros (a cadeira, o tronco)
    if on_progress:
        on_progress(0.02, "Encontrando você e a cadeira…")
    sample_at = set(np.linspace(0, total - 1, 20).astype(int).tolist())
    acc, cnt = np.zeros((h, w), np.float32), 0
    for i, fr in enumerate(frames()):
        if i in sample_at:
            acc += seg(fr) > 0.5
            cnt += 1
            if on_progress:
                on_progress(0.02 + 0.06 * cnt / len(sample_at), f"Encontrando você e a cadeira… {int(100 * cnt / len(sample_at))}%")
    static = (acc / max(1, cnt) >= 0.75).astype(np.float32)

    # 2) quadro a quadro, com suavização no tempo
    enc = subprocess.Popen([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray",
                            "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "12", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    prev = None
    color_fg, color_n = np.zeros(3), 0
    last_person = None
    for i, fr in enumerate(frames()):
        # 2x mais rápido: analisa um quadro sim, um não (a 30 fps a pessoa quase não muda em 1/30 s);
        # o quadro do meio reaproveita o anterior, e a suavização no tempo cuida da transição
        if i % 2 == 0 or last_person is None:
            person = last_person = seg(fr)
        else:
            person = last_person
        # a parte fixa (cadeira) só conta onde o pixel AGORA é escuro: a cadeira é escura, a parede é clara —
        # quando a cabeça sai de um lugar, a parede que aparece ali não vira "você"
        luma = fr.astype(np.float32).mean(2)
        dark = np.clip((125 - luma) / 45, 0, 1)
        m = np.maximum(person, static * dark)
        if i % 30 == 0:                        # cor média de você (para igualar a luz do cenário)
            sel = person > 0.8
            if sel.any():
                color_fg += fr[sel].reshape(-1, 3).mean(0)
                color_n += 1
        if prev is not None:
            m = 0.7 * m + 0.3 * prev          # sem tremedeira na borda
        prev = m
        enc.stdin.write((np.clip(m, 0, 1) * 255).astype(np.uint8).tobytes())
        if on_progress and i % 15 == 0:
            x = min(0.99, i / total)
            on_progress(0.05 + 0.85 * x, f"Recortando você e a cadeira… {int(100 * x)}%")
    enc.stdin.close()
    enc.wait()
    if color_n:
        Path(out).with_suffix(".json").write_text(json.dumps({"fg_rgb": (color_fg / color_n).round(1).tolist()}))
    return out


def match_gains(mask, plate, strength=0.55):
    """Ganhos R/G/B para a foto do cenário ir na direção da "luz" que bate em você (sem exagero)."""
    meta = Path(mask).with_suffix(".json")
    if not meta.exists():
        return (1.0, 1.0, 1.0)
    fg = np.array(json.loads(meta.read_text())["fg_rgb"], float)
    from PIL import Image
    pl = np.asarray(Image.open(plate).convert("RGB").resize((160, 280)), float).reshape(-1, 3).mean(0)
    # compara só o EQUILÍBRIO de cor (não o brilho): normaliza pela média
    fgn, pln = fg / fg.mean(), pl / pl.mean()
    g = (fgn / pln) ** strength
    g = g / g.mean()
    return tuple(float(round(x, 3)) for x in np.clip(g, 0.8, 1.2))


# ---------------------------------------------------------------- borda limpa (sem a "linha branca")

def build_clean_fg(src, mask, out, on_progress=None):
    """fg_clean.mp4: o vídeo original com a BORDA DESCONTAMINADA. Nos pixels do contorno (fios de cabelo,
    ombro), a cor gravada é metade você, metade parede branca — é isso que vira a linha branca. Aqui esses pixels
    recebem a cor de dentro (cabelo/pele) vinda do interior, como fazem os programas profissionais de recorte."""
    import cv2
    info = probe(src)
    w, h, fps = info["width"], info["height"], info["fps"] or 30
    total = max(1, int(info["duration"] * fps))
    from .media import TONEMAP
    vf = ["-vf", TONEMAP] if info.get("hdr") else []
    dec = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(src), *vf, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    mdec = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(mask), "-vf", f"scale={w}:{h}",
                             "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "14", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    k = max(9, (w // 40) | 1)                    # alcance da "puxada" de cor do interior
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    i = 0
    while True:
        buf = dec.stdout.read(w * h * 3)
        mb = mdec.stdout.read(w * h)
        if len(buf) < w * h * 3 or len(mb) < w * h:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(np.float32)
        m = np.frombuffer(mb, np.uint8).reshape(h, w).astype(np.float32) / 255.0
        core = cv2.erode((m > 0.92).astype(np.float32), ker, iterations=2)       # interior "puro"
        num = cv2.GaussianBlur(fr * core[..., None], (k, k), 0)
        den = cv2.GaussianBlur(core, (k, k), 0)[..., None]
        inside = num / np.maximum(den, 1e-3)                                     # cor de dentro, espalhada
        # faixa da borda: quanto mais perto do lado de fora, mais usa a cor de dentro
        band = np.clip((0.97 - m) / 0.6, 0, 1)[..., None] * (den > 0.02)
        # só "escurece" o que a parede clareou (não inventa brilho)
        clean = fr * (1 - band) + np.minimum(fr, inside + 18) * band
        enc.stdin.write(np.clip(clean, 0, 255).astype(np.uint8).tobytes())
        i += 1
        if on_progress and i % 30 == 0:
            x = min(0.99, i / total)
            on_progress(0.88 + 0.05 * x, f"Limpando a borda do cabelo… {int(100 * x)}%")
    enc.stdin.close()
    enc.wait()
    dec.wait()
    mdec.wait()
    return out


def fg_source(pdir, project):
    """Vídeo usado como "você" no cenário: o de borda limpa (se existir) ou o original."""
    clean = Path(pdir) / "fg_clean.mp4"
    return clean if clean.exists() else Path(pdir) / project["source"]["file"]


# ---------------------------------------------------------------- filtros (render e prévia)

def plate_chain(W, H, fps, blur_sigma, gains=(1.0, 1.0, 1.0)):
    """Cadeia ffmpeg para a foto: preenche o quadro, desfoca (lente), puxa a cor para a luz que bate em você,
    escurece levemente (bordas mais escuras, como lente) e ganha granulação de vídeo."""
    r, g, b = gains
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma={blur_sigma:.1f},colorchannelmixer=rr={r}:gg={g}:bb={b},"
            f"eq=brightness=-0.035:saturation=0.9:contrast=0.97,vignette=PI/5,"
            f"noise=alls=5:allf=t,fps={fps},format=yuv420p")


def mask_chain(W, H):
    """Borda: aperta ~1 px (some o halo branco da parede) e suaviza."""
    return (f"scale={W}:{H}:flags=bicubic,format=gray,"
            f"lut=y='clip((val-95)*1.7\\,0\\,255)',gblur=sigma=1.0")


def composite_graph(fg, mk, pl, out, W, H, fps, sigma, gains, hdr=False):
    """Grafo: cenário (desfocado/casado) + você (borda limpa) + LIGHT WRAP (a luz do cenário vaza ~2 px na
    borda, como acontece com uma pessoa de verdade na frente de um fundo)."""
    from .media import TONEMAP
    tm = TONEMAP + "," if hdr else ""
    return (f"[{pl}]{plate_chain(W, H, fps, sigma, gains)},split[pl1][pl2];"
            f"[{mk}]{mask_chain(W, H)},split[mk1][mk2];"
            f"[{fg}]{tm}scale={W}:{H},format=yuva420p[fg0];[fg0][mk1]alphamerge[fg];"
            f"[pl1][fg]overlay=format=auto:shortest=1,format=yuv420p[cmp];"
            # light wrap: borda = máscara desfocada − máscara; o cenário bem desfocado entra só ali, de leve
            f"[mk2]gblur=sigma={max(2, W / 260):.1f},format=gray[mkb];"
            f"[pl2]gblur=sigma={max(6, W / 70):.1f},format=yuva420p[wrapc];"
            f"[mkb]negate,lut=y='clip(val*0.5\\,0\\,255)'[wa];"
            f"[wrapc][wa]alphamerge[wrap];"
            f"[cmp][wrap]overlay=format=auto,format=yuv420p[{out}]")


def build_preview(src, mask, plate, out, blur_sigma=None, on_progress=None, fg=None, prog_range=(0.94, 0.99)):
    """Prévia do editor já com o fundo novo (720p, leve)."""
    info = probe(src)
    w, h = info["width"], info["height"]
    if max(w, h) > 1280:
        s = 1280 / max(w, h)
        w, h = int(w * s) // 2 * 2, int(h * s) // 2 * 2
    fps = info["fps"] or 30
    sigma = blur_sigma if blur_sigma is not None else w * 0.011
    fg = fg or src
    hdr = bool(info.get("hdr")) and Path(fg) == Path(src)
    fc = composite_graph("3:v", "1:v", "2:v", "v", w, h, fps, sigma, match_gains(mask, plate), hdr)
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-i", str(mask),
           "-loop", "1", "-framerate", f"{fps}", "-t", f"{info['duration']:.3f}", "-i", str(plate), "-i", str(fg),
           "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart"]
    import re as _re
    dur = max(0.1, info["duration"])
    a, b = prog_range
    err = ""
    for enc in (["-c:v", "h264_videotoolbox", "-b:v", "5M"], ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]):
        p = subprocess.Popen(cmd + enc + ["-progress", "pipe:1", "-nostats", str(out)], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        for line in p.stdout:                    # andamento real da montagem
            m = _re.match(r"out_time_us=(\d+)", line)
            if m and on_progress:
                x = min(1.0, int(m.group(1)) / 1e6 / dur)
                on_progress(a + (b - a) * x, f"Montando a prévia com o novo fundo… {int(100 * x)}%")
        err = p.stderr.read()
        if p.wait() == 0:
            return out
    raise RuntimeError("falha ao gerar a prévia com o fundo: " + err[-300:])


def apply(project, pdir, on_progress=None):
    """Garante máscara + foto e gera a prévia. Devolve o nome do arquivo de prévia (ou None = fundo original)."""
    pdir = Path(pdir)
    plate = plate_path(project, pdir)
    if plate is None:
        return None
    src = pdir / project["source"]["file"]
    mask = pdir / "mask_fg.mp4"
    clean = pdir / "fg_clean.mp4"
    quick = mask.exists() and clean.exists()       # troca de cenário: só falta montar a prévia
    if not mask.exists():
        build_fg_mask(src, mask, on_progress=on_progress)
    if not clean.exists():
        tmp = pdir / "fg_clean.part.mp4"
        build_clean_fg(src, mask, tmp, on_progress=on_progress)
        tmp.replace(clean)
    if on_progress:
        on_progress(0.03 if quick else 0.94, "Montando a prévia com o novo fundo…")
    out = pdir / "preview_bg.mp4"
    tmp = pdir / "preview_bg.part.mp4"
    build_preview(src, mask, plate, tmp, fg=clean, on_progress=on_progress,
                  prog_range=(0.03, 0.99) if quick else (0.94, 0.99))
    tmp.replace(out)
    (pdir / "preview_bg.json").write_text(json.dumps({"scene": project["settings"].get("bg_scene")}))
    return out.name


# ---------------------------------------------------------------- você recortado para a PRÉVIA do editor

def build_alpha_preview(src, mask, out, fg=None, on_progress=None):
    """fg_alpha.webm: só você (e a cadeira/microfone) com fundo TRANSPARENTE, leve, para a prévia do editor
    mostrar a tela verde já recortada — igual à exportação."""
    import re as _re
    info = probe(src)
    h = min(960, info["height"]) // 2 * 2
    w = int(info["width"] * h / info["height"]) // 2 * 2
    fg = fg or src
    fc = (f"[1:v]scale={w}:{h},format=gray,lut=y='clip((val-95)*1.7\\,0\\,255)',gblur=sigma=1.0[m];"
          f"[0:v]scale={w}:{h},format=yuva420p[f];[f][m]alphamerge,format=yuva420p[v]")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(fg), "-i", str(mask),
           "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libvpx", "-pix_fmt", "yuva420p",
           "-auto-alt-ref", "0", "-b:v", "2M", "-deadline", "realtime", "-cpu-used", "8",
           "-g", "12", "-keyint_min", "12",                      # quadro-chave a cada ~0,4 s: busca instantânea
           "-progress", "pipe:1", "-nostats", str(out)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    dur = max(0.1, info["duration"])
    for line in p.stdout:
        m = _re.match(r"out_time_us=(\d+)", line)
        if m and on_progress:
            x = min(1.0, int(m.group(1)) / 1e6 / dur)
            on_progress(0.93 + 0.06 * x, f"Preparando você recortado para a prévia… {int(100 * x)}%")
    if p.wait() != 0:
        raise RuntimeError("falha ao gerar o recorte da prévia: " + p.stderr.read()[-300:])
    return out


def ensure_cutout(project, pdir, on_progress=None):
    """Recorta você (uma vez por vídeo): máscara + borda limpa + versão transparente para a prévia."""
    pdir = Path(pdir)
    src = pdir / project["source"]["file"]
    mask, clean, alpha = pdir / "mask_fg.mp4", pdir / "fg_clean.mp4", pdir / "fg_alpha.webm"
    if not mask.exists():
        build_fg_mask(src, mask, on_progress=on_progress)
    if not clean.exists():
        tmp = pdir / "fg_clean.part.mp4"
        build_clean_fg(src, mask, tmp, on_progress=on_progress)
        tmp.replace(clean)
    if not alpha.exists():
        tmp = pdir / "fg_alpha.part.webm"
        build_alpha_preview(src, mask, tmp, fg=clean, on_progress=on_progress)
        tmp.replace(alpha)
    return alpha.name

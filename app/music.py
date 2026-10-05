"""Faixa de música (estilo CapCut): clipes de música na linha do tempo, que você arrasta e apara.

Cada clipe em `project["music"]`:
  {"id", "file": "lib:<slug>" | "<arquivo em assets/>", "title", "start": s (no vídeo editado),
   "in": s (de onde a música começa a tocar), "dur": s (no vídeo editado), "vol": 0..1, "fade": s}

A música NUNCA é acelerada junto com o vídeo: com velocidade 1,2x, o clipe que ocupa 10 s da edição toca
10/1,2 s de música em velocidade normal, no lugar certo do vídeo final.
"""
import json
from pathlib import Path

from .media import probe

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"
BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"

# músicas de exemplo (Kevin MacLeod, incompetech.com — CC BY 4.0: crédito vai no .creditos.txt)
CATALOG = [
    {"slug": "deliberate_thought", "title": "Deliberate Thought", "mood": "Piano reflexivo, autoridade calma",
     "url": BASE + "Deliberate%20Thought.mp3"},
    {"slug": "perspectives", "title": "Perspectives", "mood": "Cinematográfica, elegante",
     "url": BASE + "Perspectives.mp3"},
    {"slug": "dreamer", "title": "Dreamer", "mood": "Suave, intimista",
     "url": BASE + "Dreamer.mp3"},
    {"slug": "inspired", "title": "Inspired", "mood": "Inspiradora, sobe aos poucos",
     "url": BASE + "Inspired.mp3"},
    {"slug": "wallpaper", "title": "Wallpaper", "mood": "Lo-fi leve, de fundo",
     "url": BASE + "Wallpaper.mp3"},
    {"slug": "bossa_antigua", "title": "Bossa Antigua", "mood": "Bossa nova, brasileira e leve",
     "url": BASE + "Bossa%20Antigua.mp3"},
]
CREDIT = '"{title}" Kevin MacLeod (incompetech.com) — Licensed under Creative Commons: By Attribution 4.0'


def entry(slug):
    return next((c for c in CATALOG if c["slug"] == slug), None)


def ensure(slug):
    import httpx
    c = entry(slug)
    if not c:
        raise ValueError(f"música desconhecida: {slug}")
    MUSIC_DIR.mkdir(exist_ok=True)
    out = MUSIC_DIR / f"{slug}.mp3"
    if not out.exists():
        r = httpx.get(c["url"], timeout=120, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        tmp = out.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(out)
    return out


def path_of(clip, pdir):
    f = clip.get("file") or ""
    if f.startswith("lib:"):
        return ensure(f[4:])
    p = Path(pdir) / "assets" / f
    return p if p.exists() else None


def duration(path):
    meta = Path(path).with_suffix(".json")
    if meta.exists():
        return json.loads(meta.read_text())["duration"]
    d = probe(path)["duration"]
    try:
        meta.write_text(json.dumps({"duration": d}))
    except OSError:
        pass
    return d


def clips(project):
    """Clipes de música do projeto (inclui a música antiga "no vídeo todo" das configurações)."""
    out = [c for c in project.get("music") or [] if c.get("file")]
    legacy = (project.get("settings") or {}).get("music")
    if not out and legacy:
        out = [{"id": "legacy", "file": legacy, "start": 0, "in": 0, "dur": 1e9,
                "vol": float(project["settings"].get("music_volume", 0.15)), "fade": 1.5}]
    return out


def credits(project):
    out = []
    for c in clips(project):
        f = c.get("file", "")
        if f.startswith("lib:") and entry(f[4:]):
            out.append(CREDIT.format(title=entry(f[4:])["title"]))
    return sorted(set(out))


def filters(project, pdir, add_input, total_edit, speed=1.0, prefix="m"):
    """Filtros ffmpeg dos clipes de música no tempo do VÍDEO FINAL (já com a velocidade aplicada à edição,
    mas a música em 1x). Devolve (lista de filtros, rótulo da mistura de música) ou ([], None)."""
    f, labels = [], []
    for k, c in enumerate(clips(project)):
        path = path_of(c, pdir)
        if not path:
            continue
        start = max(0.0, float(c.get("start", 0))) / speed
        end_edit = min(total_edit, float(c.get("start", 0)) + float(c.get("dur", 0)))
        dur = (end_edit - float(c.get("start", 0))) / speed
        if dur <= 0.05:
            continue
        src_in = max(0.0, float(c.get("in", 0)))
        vol = float(c.get("vol", 0.18))
        fade = min(float(c.get("fade", 1.0)), dur / 3)
        idx = add_input("-stream_loop", "-1", "-i", str(path))
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"atrim=start={src_in:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,volume={vol:.3f},"
                 f"afade=t=in:d={min(0.6, fade):.2f},afade=t=out:st={max(0, dur - fade):.3f}:d={fade:.2f},"
                 f"adelay={int(start * 1000)}:all=1[{prefix}{k}]")
        labels.append(f"{prefix}{k}")
    if not labels:
        return [], None
    if len(labels) == 1:
        return f, labels[0]
    f.append("".join(f"[{x}]" for x in labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0[{prefix}mix]")
    return f, f"{prefix}mix"

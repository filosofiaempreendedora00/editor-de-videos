"""Faixa de música (estilo CapCut): clipes de música na linha do tempo, que você arrasta e apara.

Cada clipe em `project["music"]`:
  {"id", "file": "lib:<slug>" | "<arquivo em assets/>", "title", "start": s (no vídeo editado),
   "in": s (de onde a música começa a tocar), "dur": s (no vídeo editado), "vol": 0..1, "fade": s}

A música NUNCA é acelerada junto com o vídeo: com velocidade 1,2x, o clipe que ocupa 10 s da edição toca
10/1,2 s de música em velocidade normal, no lugar certo do vídeo final.
"""
import json
import re
from pathlib import Path

from .media import probe

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music"
BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"

# biblioteca de música de fundo (instrumental, para ficar baixinha sob a fala)
# Mixkit: "Mixkit Stock Music Free License" — uso comercial em vídeos, sem precisar dar crédito.
# Kevin MacLeod (incompetech.com): CC BY 4.0 — o crédito vai no .creditos.txt.
MIXKIT = "Mixkit — Mixkit Stock Music Free License (uso comercial liberado)"
GROUPS = ["🔥 Em alta (estilo Reels)", "🧠 Evergreen — psicologia, marketing, vendas", "Outras",
          "🎻 Suspense com cordas (retenção)", "🎯 Com personalidade (menos genéricas)"]
CATALOG = [
    # 19/10: ele achou a música do Joshie "genérica" — opções com mais personalidade, medidas (BPM/pulso/graves)
    {"slug": "mk_magical_moment", "title": "Magical Moment", "mood": "Clima mágico e leve, 89 BPM — encantamento", "group": GROUPS[4], "url": "https://assets.mixkit.co/music/813/813.mp3", "credit": MIXKIT},
    {"slug": "mk_smile", "title": "Smile", "mood": "Quente e feliz, 76 BPM (o andamento das referências)", "group": GROUPS[4], "url": "https://assets.mixkit.co/music/1076/1076.mp3", "credit": MIXKIT},
    {"slug": "mk_cotton_candy_rnb", "title": "Cotton Candy R&B Beat", "mood": "R&B moderno com grave quente, 99 BPM", "group": GROUPS[4], "url": "https://assets.mixkit.co/music/1094/1094.mp3", "credit": MIXKIT},
    {"slug": "mk_gimme_that_groove", "title": "Gimme that Groove!", "mood": "Funk com groove, 112 BPM — a mais animada", "group": GROUPS[4], "url": "https://assets.mixkit.co/music/872/872.mp3", "credit": MIXKIT},
    {"slug": "mk_just_keep_walking", "title": "Just Keep Walking", "mood": "Indie/acústico animado, 96 BPM — história com final feliz", "group": GROUPS[4], "url": "https://assets.mixkit.co/music/963/963.mp3", "credit": MIXKIT},
    {"slug": "mk_sleepy_cat", "title": "Sleepy Cat", "mood": "Lo-fi com piano, leve e moderno", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/135/135.mp3", "credit": MIXKIT},
    {"slug": "mk_sweet_september", "title": "Sweet September", "mood": "Lo-fi hip-hop, ritmo de Reels", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/282/282.mp3", "credit": MIXKIT},
    {"slug": "mk_lo_fi_01", "title": "Lo-Fi 01", "mood": "Lo-fi suave, conversa de fundo", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/763/763.mp3", "credit": MIXKIT},
    {"slug": "mk_lo_fi_04", "title": "Lo-Fi 04", "mood": "Lo-fi tranquilo e envolvente", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/766/766.mp3", "credit": MIXKIT},
    {"slug": "mk_hip_hop_02", "title": "Hip Hop 02", "mood": "Hip-hop com piano, motivacional", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/738/738.mp3", "credit": MIXKIT},
    {"slug": "mk_hazy_after_hours", "title": "Hazy After Hours", "mood": "Eletrônica noturna e elegante", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/132/132.mp3", "credit": MIXKIT},
    {"slug": "mk_deep_urban", "title": "Deep Urban", "mood": "Deep house urbano, sofisticado", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/623/623.mp3", "credit": MIXKIT},
    {"slug": "mk_tides_turning", "title": "Tides Turning", "mood": "Synth chill, virada positiva", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/439/439.mp3", "credit": MIXKIT},
    {"slug": "mk_digital_clouds", "title": "Digital Clouds", "mood": "Chill tech, moderno e limpo", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/175/175.mp3", "credit": MIXKIT},
    {"slug": "mk_minimal_emotion", "title": "Minimal Emotion", "mood": "Eletrônica minimalista, foco", "group": GROUPS[0], "url": "https://assets.mixkit.co/music/160/160.mp3", "credit": MIXKIT},
    {"slug": "mk_piano_reflections", "title": "Piano Reflections", "mood": "Piano reflexivo — autoridade calma", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/22/22.mp3", "credit": MIXKIT},
    {"slug": "mk_possible_dreams", "title": "Possible Dreams", "mood": "Piano clássico, inspirador", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/599/599.mp3", "credit": MIXKIT},
    {"slug": "mk_skyline", "title": "Skyline", "mood": "Piano clássico, aberto e elegante", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/601/601.mp3", "credit": MIXKIT},
    {"slug": "mk_discover", "title": "Discover", "mood": "Orquestral com piano — descoberta", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/587/587.mp3", "credit": MIXKIT},
    {"slug": "mk_silent_descent", "title": "Silent Descent", "mood": "Trilha de cinema, introspectiva", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/614/614.mp3", "credit": MIXKIT},
    {"slug": "mk_vastness", "title": "Vastness", "mood": "Ambiente cinematográfico com piano", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/184/184.mp3", "credit": MIXKIT},
    {"slug": "mk_forest_mist_whispers", "title": "Forest Mist Whispers", "mood": "Ambiente com piano, profundo", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/148/148.mp3", "credit": MIXKIT},
    {"slug": "mk_focus_on_yourself", "title": "Focus on Yourself", "mood": "Eletrônica serena — foco e clareza", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/568/568.mp3", "credit": MIXKIT},
    {"slug": "mk_your_breath", "title": "Your Breath", "mood": "Corporativa moderna, respiro", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/634/634.mp3", "credit": MIXKIT},
    {"slug": "mk_drawing_the_sky", "title": "Drawing the Sky", "mood": "Orquestral leve, visão de futuro", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/606/606.mp3", "credit": MIXKIT},
    {"slug": "mk_curiosity", "title": "Curiosity", "mood": "Chill curioso — psicologia, perguntas", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/480/480.mp3", "credit": MIXKIT},
    {"slug": "mk_echoes", "title": "Echoes", "mood": "Atmosfera densa, reflexão", "group": GROUPS[1], "url": "https://assets.mixkit.co/music/188/188.mp3", "credit": MIXKIT},
    # 🎻 suspense com violinos/cordas para segurar a atenção (Kevin MacLeod, CC BY 4.0: crédito na legenda do post)
    {"slug": "volatile_reaction", "title": "Volatile Reaction", "mood": "Cordas em ostinato acelerado — tensão que puxa pro próximo segundo",
     "group": GROUPS[3], "url": BASE + "Volatile%20Reaction.mp3"},
    {"slug": "hitman", "title": "Hitman", "mood": "Suspense de espião, cordas graves e pulsação",
     "group": GROUPS[3], "url": BASE + "Hitman.mp3"},
    {"slug": "investigations", "title": "Investigations", "mood": "Pizzicato de violinos, mistério curioso e leve",
     "group": GROUPS[3], "url": BASE + "Investigations.mp3"},
    {"slug": "sneaky_snitch", "title": "Sneaky Snitch", "mood": "Pizzicato 'na ponta dos pés', suspense com humor",
     "group": GROUPS[3], "url": BASE + "Sneaky%20Snitch.mp3"},
    {"slug": "long_note_four", "title": "Long Note Four", "mood": "Cordas longas e tensas, expectativa crescente",
     "group": GROUPS[3], "url": BASE + "Long%20Note%20Four.mp3"},
    {"slug": "deliberate_thought", "title": "Deliberate Thought", "mood": "Piano reflexivo, autoridade calma",
     "group": GROUPS[2], "url": BASE + "Deliberate%20Thought.mp3"},
    {"slug": "perspectives", "title": "Perspectives", "mood": "Cinematográfica, elegante",
     "group": GROUPS[2], "url": BASE + "Perspectives.mp3"},
    {"slug": "dreamer", "title": "Dreamer", "mood": "Suave, intimista",
     "group": GROUPS[2], "url": BASE + "Dreamer.mp3"},
    {"slug": "inspired", "title": "Inspired", "mood": "Inspiradora, sobe aos poucos",
     "group": GROUPS[2], "url": BASE + "Inspired.mp3"},
    {"slug": "wallpaper", "title": "Wallpaper", "mood": "Lo-fi leve, de fundo",
     "group": GROUPS[2], "url": BASE + "Wallpaper.mp3"},
    {"slug": "bossa_antigua", "title": "Bossa Antigua", "mood": "Bossa nova, brasileira e leve",
     "group": GROUPS[2], "url": BASE + "Bossa%20Antigua.mp3"},
]

CREDIT = '"{title}" Kevin MacLeod (incompetech.com) — Licensed under Creative Commons: By Attribution 4.0'


# FAIXAS EXTRAS (as dos vídeos aprovados que eram arquivo do próprio projeto, ex.: o Vivaldi do Joshie): ficam em
# music/aprovados/ e entram na biblioteca como qualquer outra — dá para usar em outro vídeo
EXTRA_FILE = MUSIC_DIR / "extra.json"
ROOT_CONFIG = Path(__file__).resolve().parent.parent / "config.json"


def extras():
    try:
        return json.loads(EXTRA_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def entry(slug):
    return next((c for c in CATALOG if c["slug"] == slug), None) or next((c for c in extras() if c["slug"] == slug), None)


def favorites():
    """Músicas favoritas dele (⭐ no seletor) — em config.json (vai para o backup privado)."""
    try:
        return list(json.loads(ROOT_CONFIG.read_text(encoding="utf-8")).get("music_favs") or [])
    except Exception:  # noqa: BLE001
        return []


def set_favorite(slug, on):
    cfg = json.loads(ROOT_CONFIG.read_text(encoding="utf-8")) if ROOT_CONFIG.exists() else {}
    favs = [s for s in (cfg.get("music_favs") or []) if s != slug]
    if on:
        favs.insert(0, slug)
    cfg["music_favs"] = favs
    ROOT_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return favs


def approved():
    """{slug: [códigos]} das músicas usadas nos vídeos EDITADOS/PUBLICADOS do kanban (o modelo de boas práticas dele).
    Faixas que eram arquivo do projeto são copiadas para music/aprovados/ e viram entradas extras."""
    import shutil
    from . import roteiros
    from .store import load, PROJECTS
    out, ex = {}, {e["slug"]: e for e in extras()}
    try:
        rs = [r for r in roteiros.load() if r.get("status") in ("editado", "publicado", "destaque") and r.get("project")]
    except Exception:  # noqa: BLE001
        rs = []
    for r in rs:
        try:
            p = load(r["project"])
        except Exception:  # noqa: BLE001
            continue
        clips = [c for c in (p.get("music") or []) if c.get("file")]
        if not clips:
            continue
        c = max(clips, key=lambda c: float(c.get("dur", 0)))            # a trilha principal (não os trechos)
        f = c["file"]
        if f.startswith("lib:"):
            slug = f[4:]
        else:
            src = PROJECTS / r["project"] / "assets" / f
            if not src.exists():
                continue
            slug = "aprov_" + re.sub(r"[^a-z0-9]+", "_", Path(f).stem.lower()).strip("_")
            if slug not in ex:
                (MUSIC_DIR / "aprovados").mkdir(parents=True, exist_ok=True)
                dst = MUSIC_DIR / "aprovados" / f
                if not dst.exists():
                    shutil.copy2(src, dst)
                ex[slug] = {"slug": slug, "title": c.get("title") or Path(f).stem, "mood": f"usada no {r['code']}",
                            "group": "🎬 Dos vídeos aprovados", "file": f"aprovados/{f}"}
        out.setdefault(slug, []).append(r["code"])
    if ex and len(ex) != len(extras()):
        EXTRA_FILE.write_text(json.dumps(list(ex.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def ensure(slug):
    import httpx
    c = entry(slug)
    if not c:
        raise ValueError(f"música desconhecida: {slug}")
    if c.get("file"):                                   # faixa extra (arquivo local)
        return MUSIC_DIR / c["file"]
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
            e = entry(f[4:])
            out.append(f'"{e["title"]}" — {e["credit"]}' if e.get("credit") else CREDIT.format(title=e["title"]))
    return sorted(set(out))


LOOP_X = 3.0   # s de crossfade quando a faixa recomeça


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
        vol = min(1.0, float(c.get("vol", 0.18)) * 1.6)     # MESMO volume da prévia (syncMusic: vol × 1,6)
        fade = min(float(c.get("fade", 1.0)), dur / 3)
        # faixa mais curta que o vídeo: recomeça com CROSSFADE de LOOP_X s (antes o -stream_loop emendava seco e
        # "parecia que a música acaba" no Liquid Death — Sweet September tem 98,7 s, o vídeo 106 s). Igual na prévia.
        L = float(probe(path).get("duration") or 0)
        span = L - src_in
        if span > LOOP_X * 3 and dur > span - 0.05:
            n = int((dur - LOOP_X) // (span - LOOP_X)) + 1
            ins = [add_input("-i", str(path)) for _ in range(n)]
            for q, ix in enumerate(ins):
                f.append(f"[{ix}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=start={src_in:.3f},"
                         f"asetpts=PTS-STARTPTS[{prefix}{k}l{q}]")
            cur = f"{prefix}{k}l0"
            for q in range(1, n):
                f.append(f"[{cur}][{prefix}{k}l{q}]acrossfade=d={LOOP_X}:c1=tri:c2=tri[{prefix}{k}x{q}]")
                cur = f"{prefix}{k}x{q}"
            src_label, trim_start = cur, 0.0
        else:
            idx = add_input("-stream_loop", "-1", "-i", str(path))
            src_label, trim_start = f"{idx}:a", src_in
        f.append(f"[{src_label}]aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"atrim=start={trim_start:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,volume={vol:.3f},"
                 f"afade=t=in:d={min(0.6, fade):.2f},afade=t=out:st={max(0, dur - fade):.3f}:d={fade:.2f},"
                 f"adelay={int(start * 1000)}:all=1[{prefix}{k}]")
        labels.append(f"{prefix}{k}")
    if not labels:
        return [], None
    if len(labels) == 1:
        return f, labels[0]
    f.append("".join(f"[{x}]" for x in labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0[{prefix}mix]")
    return f, f"{prefix}mix"

"""Vídeos de referência -> "formato" de edição reutilizável.

Para cada referência mede: ritmo de cortes, duração média dos planos, velocidade
de fala, pausas, presença de música, cor/brilho/saturação, proporção da tela,
gancho (primeiras falas) e gera uma folha de quadros (contact sheet).
Um formato agrega várias referências e vira: configurações do editor +
densidade de inserções + um briefing de estilo usado pelo planejador.
"""
import json
import re
import statistics
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

from . import transcribe
from .media import FFMPEG, extract_audio, probe

ROOT = Path(__file__).resolve().parent.parent
FORMATOS = ROOT / "formatos"


def slugify(name):
    s = re.sub(r"[^\w\-]+", "-", name.strip().lower()).strip("-")
    return s or f"formato-{int(time.time())}"


def scene_cuts(path, threshold=0.32):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-an", "-vf",
                        f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def color_stats(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-an", "-vf",
                        "fps=1,scale=160:-2,signalstats,metadata=print", "-f", "null", "-"],
                       capture_output=True, text=True)
    def avg(key):
        vals = [float(x) for x in re.findall(rf"lavfi\.signalstats\.{key}=([\d.]+)", p.stderr)]
        return round(statistics.mean(vals), 1) if vals else None
    return {"brightness": avg("YAVG"), "saturation": avg("SATAVG"), "hue": avg("HUEAVG")}


def contact_sheet(path, out, duration, n=12):
    step = max(0.5, duration / (n + 1))
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path), "-vf",
                    f"fps=1/{step:.3f},scale=360:-2,tile=4x3:padding=6:color=black", "-frames:v", "1", str(out)])


def audio_profile(wav_path, words):
    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if not len(data):
        return {"music": False}
    speech = np.zeros(len(data), bool)
    for x in words:
        speech[int(x["start"] * sr):int(x["end"] * sr)] = True
    rms = lambda a: float(np.sqrt(np.mean(a ** 2))) if len(a) else 0.0
    s, g = rms(data[speech]), rms(data[~speech])
    # nos silêncios entre falas, música de fundo mantém energia; silêncio real não
    return {"music": bool(s and g / s > 0.18), "gap_energy": round(g / s, 3) if s else 0}


def analyze(path, workdir, language=None, on_progress=None):
    path, workdir = Path(path), Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    info = probe(path)
    dur = info["duration"] or 1
    prog = on_progress or (lambda *_: None)
    prog(0.05, "Detectando cortes…")
    cuts = scene_cuts(path)
    prog(0.2, "Lendo cores…")
    colors = color_stats(path)
    contact_sheet(path, workdir / f"{path.stem}.sheet.jpg", dur)
    words = []
    audio = {"music": False}
    if info["has_audio"]:
        prog(0.3, "Transcrevendo a referência…")
        wav = workdir / f"{path.stem}.wav"
        extract_audio(path, wav)
        words = transcribe.transcribe(wav, language, on_progress=lambda x: prog(0.3 + 0.6 * x, "Transcrevendo a referência…"))
        audio = audio_profile(wav, words)
        wav.unlink(missing_ok=True)
    gaps = [b["start"] - a["end"] for a, b in zip(words, words[1:])]
    speech_time = sum(w["end"] - w["start"] for w in words)
    hook_words = [w["w"] for w in words if w["start"] < 6][:25]
    m = {
        "file": path.name,
        "duration": round(dur, 1),
        "width": info["width"], "height": info["height"],
        "aspect": "9:16" if info["height"] > info["width"] * 1.2 else ("1:1" if abs(info["height"] - info["width"]) < 50 else "16:9"),
        "cuts": len(cuts),
        "cuts_per_min": round(len(cuts) / dur * 60, 1),
        "avg_shot": round(dur / (len(cuts) + 1), 2),
        "wpm": round(len(words) / dur * 60) if words else 0,
        "pause_mean": round(statistics.mean(gaps), 2) if gaps else 0,
        "pause_p90": round(sorted(gaps)[int(len(gaps) * 0.9)], 2) if len(gaps) > 5 else 0,
        "speech_ratio": round(speech_time / dur, 2),
        **audio, **colors,
        "hook": " ".join(hook_words),
        "transcript": " ".join(w["w"] for w in words)[:3000],
    }
    (workdir / f"{path.stem}.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    prog(1.0, "Pronto")
    return m


# ---------------------------------------------------------------- formatos

def formato_dir(slug):
    return FORMATOS / slug


def load(slug):
    f = formato_dir(slug) / "formato.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def list_all():
    FORMATOS.mkdir(exist_ok=True)
    out = []
    for d in sorted(FORMATOS.iterdir()):
        f = d / "formato.json"
        if f.exists():
            out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def save(fmt):
    d = formato_dir(fmt["slug"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "formato.json").write_text(json.dumps(fmt, ensure_ascii=False, indent=1), encoding="utf-8")


def create(name):
    slug = slugify(name)
    fmt = load(slug) or {"slug": slug, "name": name, "refs": [], "notes": "", "created": time.time()}
    save(fmt)
    (formato_dir(slug) / "refs").mkdir(exist_ok=True)
    return fmt


def rebuild(slug):
    """Recalcula métricas agregadas, configurações sugeridas e o briefing do formato."""
    fmt = load(slug)
    refs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((formato_dir(slug) / "refs").glob("*.json"))]
    fmt["refs"] = refs
    if not refs:
        save(fmt)
        return fmt

    def mean(key):
        vals = [r[key] for r in refs if isinstance(r.get(key), (int, float)) and r.get(key)]
        return round(statistics.mean(vals), 2) if vals else 0

    aspects = [r["aspect"] for r in refs]
    metrics = {k: mean(k) for k in ("duration", "cuts_per_min", "avg_shot", "wpm", "pause_mean", "pause_p90",
                                    "speech_ratio", "brightness", "saturation")}
    metrics["aspect"] = max(set(aspects), key=aspects.count)
    metrics["music"] = sum(1 for r in refs if r.get("music")) >= len(refs) / 2
    # intervalo entre estímulos visuais ~ duração média do plano (cortes + inserções)
    metrics["visual_interval"] = round(min(15.0, max(1.5, metrics["avg_shot"] or 6)), 2)

    fast = metrics["cuts_per_min"] >= 14 or metrics["wpm"] >= 170
    sat = metrics["saturation"] or 0
    look = "vivido" if sat > 60 else ("pb" if sat and sat < 12 else "none")
    settings = {
        "format": metrics["aspect"],
        "max_pause": 0.25 if fast else (0.4 if metrics["cuts_per_min"] >= 6 else 0.6),
        "pad": 0.05 if fast else 0.08,
        "transition": "zoom" if metrics["cuts_per_min"] >= 8 else ("fade" if metrics["avg_shot"] > 8 else "cut"),
        "captions": "clean",
        "look": look,
        "music_volume": 0.12 if metrics["music"] else 0.15,
    }
    fmt["metrics"] = metrics
    fmt["settings"] = settings
    ritmo = "muito acelerado" if fast else ("dinâmico" if metrics["cuts_per_min"] >= 6 else "calmo e respirado")
    hooks = "\n".join(f"  - \"{r['hook']}\"" for r in refs if r.get("hook"))
    fmt["brief"] = (
        f"Formato '{fmt['name']}' ({len(refs)} referência(s)). Ritmo {ritmo}: {metrics['cuts_per_min']} cortes/min, "
        f"plano médio de {metrics['avg_shot']}s, fala a {metrics['wpm']} palavras/min. "
        f"Proporção {metrics['aspect']}. {'Usa música de fundo. ' if metrics['music'] else ''}"
        f"Estímulo visual a cada ~{metrics['visual_interval']}s.\n"
        f"Ganchos usados nas referências:\n{hooks}\n"
        + (f"Observações de estilo: {fmt['notes']}\n" if fmt.get("notes") else ""))
    save(fmt)
    return fmt

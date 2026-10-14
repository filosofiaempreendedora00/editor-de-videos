"""Teste de SINCRONIA labial do render (exportação = prévia).

Troca a gravação do projeto por um vídeo sintético com um FLASH branco e um BIPE exatamente juntos a cada 0,5 s,
renderiza com os MESMOS cortes, zooms, tela verde (sem o print) e velocidade, e mede no MP4 a distância entre cada
flash e o seu bipe. Deriva ou valores > ~45 ms = a boca vai sair dessincronizada. Projeto temporário apagado no fim.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .media import FFMPEG
from .store import PROJECTS

TMP = "0000c0ffee"


def _measure(path, fps):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-vf", "scale=32:56,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    v = np.frombuffer(raw, np.uint8).reshape(-1, 32 * 56).astype(np.float32).mean(1)
    flashes = [i / fps for i in range(1, len(v)) if v[i] > 100 >= v[i - 1]]
    a = np.frombuffer(subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                                     capture_output=True).stdout, np.int16).astype(np.float32)
    e = np.array([np.abs(a[i * 48:(i + 1) * 48]).max() for i in range(len(a) // 48)])   # 1 ms
    th = e.max() * 0.3
    beeps = [i / 1000 for i in range(1, len(e)) if e[i] > th >= e[i - 1]]
    pairs = []
    for t in flashes:
        b = min(beeps, key=lambda x: abs(x - t)) if beeps else None
        if b is not None and abs(b - t) < 0.2:
            pairs.append((round(t, 2), round((t - b) * 1000)))
    return pairs


def run(pid):
    from . import render
    from .store import load
    src = load(pid)
    fps = float(src["source"].get("fps") or 30)
    dur = float(src["source"]["duration"])
    W, H = int(src["source"]["width"]), int(src["source"]["height"])
    d = PROJECTS / TMP
    shutil.rmtree(d, ignore_errors=True)
    (d / "assets").mkdir(parents=True)
    (d / "exports").mkdir()
    every = int(round(fps / 2))
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={fps}:d={dur}",
                    "-f", "lavfi", "-i", f"sine=f=1000:r=48000:d={dur}", "-filter_complex",
                    f"[0:v]drawbox=c=white:t=fill:enable='lt(mod(n,{every}),1)',format=yuv420p[v];"
                    f"[1:a]volume='if(lt(mod(t,{every / fps}),0.033),1,0)':eval=frame,aformat=channel_layouts=stereo[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-g", str(every * 2),
                    "-c:a", "aac", "-b:a", "128k", str(d / "source.mov")], check=True)
    for f in ("mask_fg.mp4", "mask.mp4"):
        if (PROJECTS / pid / f).exists():
            (d / f).symlink_to((PROJECTS / pid / f).resolve())
    p = json.loads(json.dumps(src))
    p.update(id=TMP, name="teste de sincronia", music=[])
    p["source"] = {**p["source"], "file": "source.mov", "hdr": None, "rotation": 0}
    keep = []
    for o in p.get("overlays", []):
        if o["type"] in ("zoom", "sfx"):
            keep.append(o)
        elif o["type"] == "greenscreen":
            keep.append({**o, "file": "inexistente.jpg"})     # mesmos planos parados, sem o print por cima
    p["overlays"] = keep
    p["settings"].update(captions="none", sfx_volume=0.0, bg_scene="none")
    (d / "project.json").write_text(json.dumps(p, ensure_ascii=False))
    out = d / "exports" / "sync.mp4"
    try:
        render.render(p, d.resolve(), out)
        pairs = _measure(out, fps)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    vals = [x for _, x in pairs]
    if not vals:
        return {"ok": False, "erro": "nenhum flash/bipe pareado"}
    half = len(vals) // 2
    drift = float(np.mean(vals[half:]) - np.mean(vals[:half]))
    return {"ok": max(abs(v) for v in vals) <= 45 and abs(drift) <= 15, "pares": len(vals),
            "min_ms": min(vals), "max_ms": max(vals), "media_ms": round(float(np.mean(vals)), 1),
            "deriva_ms": round(drift, 1)}

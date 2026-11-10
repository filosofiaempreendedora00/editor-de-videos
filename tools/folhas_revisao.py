"""Folhas de revisão de uma amostra: quadros na ENTRADA, no MEIO e no FIM de cada cena + instantes extras.
folhas_revisao.py <mp4> <pid> <pasta_saida> [t_extra ...]  (as cenas vêm da timeline do projeto, no tempo de saída)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def cenas(pid):
    from app import store, timeline
    p = store.load(pid)
    c = timeline.compute(p)
    spd = p["settings"].get("speed", 1.0) or 1.0
    rows = []
    for o in c["overlays"]:
        if o["type"] in ("media", "motion", "emphasis", "behind", "calor", "greenscreen"):
            lab = o.get("file") or (o.get("motion") or {}).get("template") or o.get("template") or o.get("text") or o.get("key") or ""
            rows.append((o["a"] / spd, o["b"] / spd, str(lab)[:18]))
    return sorted(rows)


def main():
    import imageio_ffmpeg
    F = imageio_ffmpeg.get_ffmpeg_exe()
    mp4, pid, outdir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    ts = [(0.05, "inicio")]
    for a, b, lab in cenas(pid):
        ts += [(a + 0.12, f"{lab} in"), ((a + b) / 2, f"{lab} meio"), (b - 0.12, f"{lab} fim")]
    ts += [(float(x), "extra") for x in sys.argv[4:]]
    ts.sort()
    frames = []
    for k, (t, lab) in enumerate(ts):
        f = outdir / f"q{k:03d}.jpg"
        txt = f"{t:.2f} {lab}".replace(":", " ").replace("'", "")
        subprocess.run([F, "-v", "error", "-y", "-ss", f"{max(0, t):.3f}", "-i", mp4, "-frames:v", "1", "-vf",
                        f"scale=270:-2,drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text='{txt}':"
                        "x=4:y=4:fontsize=13:fontcolor=yellow:box=1:boxcolor=black@0.6", str(f)])
        frames.append(f)
    for s in range(0, len(frames), 12):
        grp = [f for f in frames[s:s + 12] if f.exists()]
        cmd = [F, "-v", "error", "-y"]
        for f in grp:
            cmd += ["-i", str(f)]
        n = len(grp)
        while n < 12:
            cmd += ["-f", "lavfi", "-i", "color=black:s=270x480:d=1"]
            n += 1
        cmd += ["-filter_complex", "".join(f"[{i}]scale=270:480,setsar=1[v{i}];" for i in range(12))
                + "".join(f"[v{i}]" for i in range(12)) + "xstack=inputs=12:layout="
                + "|".join(f"{(i % 6) * 270}_{(i // 6) * 480}" for i in range(12)),
                "-frames:v", "1", str(outdir / f"folha_{s // 12:02d}.jpg")]
        subprocess.run(cmd)
    print(len(frames), "quadros;", (len(frames) + 11) // 12, "folhas em", outdir)


if __name__ == "__main__":
    main()

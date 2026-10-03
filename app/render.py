"""Exporta o vídeo final num único comando ffmpeg: cortes + zoom/transições +
inserções (imagem/vídeo) + legendas + texto na tela + música com ducking."""
import re
import shutil
import subprocess
from pathlib import Path

from . import timeline
from .media import FFMPEG, kind_of

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
SYSTEM_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
]

FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
ZOOM = 1.15


def ensure_fonts():
    FONT_DIR.mkdir(exist_ok=True)
    for f in SYSTEM_FONTS:
        if Path(f).exists() and not (FONT_DIR / Path(f).name).exists():
            shutil.copy(f, FONT_DIR)


def even(x):
    return int(x) // 2 * 2


def output_size(src, fmt):
    sw, sh = src["width"] or 1920, src["height"] or 1080
    if fmt in FORMATS:
        return FORMATS[fmt]
    scale = min(1.0, 1920 / max(sw, sh))
    return even(sw * scale), even(sh * scale)


def crop_box(src, W, H):
    """Maior retângulo do vídeo original com a proporção de saída (corte centralizado)."""
    sw, sh = src["width"] or W, src["height"] or H
    if sw / sh > W / H:
        return even(sh * W / H), even(sh)
    return even(sw), even(sw * H / W)


# ---------------------------------------------------------------- legendas (ASS)

def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(comp, W, H, path):
    s = comp["settings"]
    vertical = H > W
    cap_size = int(H * (0.052 if vertical else 0.075))
    cap_margin = int(H * (0.22 if vertical else 0.08))
    title_size = int(H * (0.045 if vertical else 0.065))
    outline = max(3, cap_size // 9)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Pop,Arial Black,{cap_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,{outline},2,2,60,60,{cap_margin},1",
        f"Style: Classic,Arial Black,{int(cap_size * 0.8)},&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,"
        f"0,0,0,0,100,100,0,0,3,{outline},0,2,60,60,{int(cap_margin * 0.6)},1",
        f"Style: Title,Arial Black,{title_size},&H00111111,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,"
        f"0,0,0,0,100,100,0,0,3,{max(10, title_size // 3)},0,8,80,80,{int(H * 0.09)},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    upper = s.get("uppercase", True)
    mode = s.get("captions", "pop")

    def fmt(w):
        return ass_escape(w.upper() if upper else w)

    if mode == "pop":
        for c in comp["captions"]:
            ws = c["words"]
            for k, w in enumerate(ws):
                a = w["a"]
                b = ws[k + 1]["a"] if k + 1 < len(ws) else c["b"]
                if b - a < 0.02:
                    continue
                parts = []
                for j, x in enumerate(ws):
                    if j == k:
                        parts.append("{\\c&H0000E6FF&\\fscx108\\fscy108}" + fmt(x["w"]) + "{\\r}")
                    else:
                        parts.append(fmt(x["w"]))
                lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Pop,,0,0,0,,{' '.join(parts)}")
    elif mode == "classic":
        for c in comp["captions"]:
            text = " ".join(fmt(w["w"]) for w in c["words"])
            lines.append(f"Dialogue: 0,{ass_time(c['a'])},{ass_time(c['b'])},Classic,,0,0,0,,{text}")

    for ov in comp["overlays"]:
        if ov.get("type") == "text" and ov.get("text"):
            text = ass_escape(ov["text"].upper() if upper else ov["text"])
            lines.append(f"Dialogue: 1,{ass_time(ov['a'])},{ass_time(ov['b'])},Title,,0,0,0,,"
                         f"{{\\fad(150,150)}}{text}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- filtro

def build_command(project, pdir, out_path):
    comp = timeline.compute(project)
    src = project["source"]
    s = comp["settings"]
    segs = comp["segments"]
    W, H = output_size(src, s.get("format", "original"))
    cw, ch = crop_box(src, W, H)
    fps = min(60.0, src.get("fps") or 30.0)
    total = comp["duration"]
    td = comp["transition_duration"]
    n = len(segs)
    if n == 0 or total <= 0:
        raise ValueError("Nada para exportar: todas as falas foram cortadas.")

    inputs = ["-i", str(pdir / project["source"]["file"])]
    f = []
    has_audio = src.get("has_audio", True)

    f.append(f"[0:v]split={n}" + "".join(f"[s{k}]" for k in range(n)))
    if has_audio:
        f.append(f"[0:a]asplit={n}" + "".join(f"[r{k}]" for k in range(n)))
    for k, sg in enumerate(segs):
        z = ZOOM if (s.get("transition") == "zoom" and k % 2 == 1) else 1.0
        zw, zh = even(cw / z), even(ch / z)
        # foco um pouco acima do centro, onde costuma estar o rosto
        f.append(
            f"[s{k}]trim=start={sg['start']}:end={sg['end']},setpts=PTS-STARTPTS,"
            f"crop={zw}:{zh}:(iw-{zw})/2:(ih-{zh})*0.4,scale={W}:{H}:flags=lanczos,"
            f"setsar=1,fps={fps},format=yuv420p[v{k}]")
        if has_audio:
            d = sg["end"] - sg["start"]
            f.append(
                f"[r{k}]atrim=start={sg['start']}:end={sg['end']},asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates=48000:channel_layouts=stereo,"
                f"afade=t=in:d=0.01,afade=t=out:st={max(0, d - 0.015):.3f}:d=0.015[a{k}]")

    if not has_audio:
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    if td > 0 and n > 1:
        prev_v, prev_a = "v0", "a0"
        for k in range(1, n):
            off = segs[k]["out"]
            f.append(f"[{prev_v}][v{k}]xfade=transition=fade:duration={td}:offset={off:.3f}[xv{k}]")
            prev_v = f"xv{k}"
            if has_audio:
                f.append(f"[{prev_a}][a{k}]acrossfade=d={td}[xa{k}]")
                prev_a = f"xa{k}"
        vlabel = prev_v
        alabel = prev_a if has_audio else "1:a"
    else:
        if has_audio:
            f.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
            alabel = "ac"
        else:
            f.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
            alabel = "1:a"
        vlabel = "vc"

    # inserções de imagem/vídeo
    idx = sum(1 for x in inputs if x == "-i")
    base = vlabel
    for j, ov in enumerate(comp["overlays"]):
        if ov.get("type") != "media" or not ov.get("file"):
            continue
        fpath = pdir / "assets" / ov["file"]
        if not fpath.exists():
            continue
        dur = max(0.3, ov["b"] - ov["a"])
        if kind_of(fpath) == "image":
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(fpath)]
        else:
            inputs += ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(fpath)]
        layout = ov.get("layout", "full")
        if layout == "pip":
            pw = even(W * (0.5 if W > H else 0.7))
            ph = even(pw * 9 / 16) if W > H else even(pw * 10 / 16)
            scale = f"scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph}"
            pos = f"x=(W-w)/2:y=H*0.12" if H > W else "x=W-w-48:y=48"
        else:
            scale = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
            pos = "x=0:y=0"
        f.append(f"[{idx}:v]{scale},setsar=1,fps={fps},format=yuva420p,"
                 f"fade=t=in:st=0:d=0.12:alpha=1,setpts=PTS-STARTPTS+{ov['a']:.3f}/TB[ov{j}]")
        f.append(f"[{base}][ov{j}]overlay={pos}:enable='between(t,{ov['a']:.3f},{ov['b']:.3f})'"
                 f":eof_action=pass[b{j}]")
        base = f"b{j}"
        idx += 1

    # legendas + títulos
    has_text = (s.get("captions") in ("pop", "classic") and comp["captions"]) or any(
        o.get("type") == "text" for o in comp["overlays"])
    if has_text:
        ensure_fonts()
        ass = pdir / "render.ass"
        build_ass(comp, W, H, ass)
        rel = ass.relative_to(ROOT).as_posix().replace("'", "\\'").replace(":", "\\:")
        f.append(f"[{base}]ass='{rel}':fontsdir=fonts[vt]")
        base = "vt"
    f.append(f"[{base}]null[vout]")

    # música de fundo com ducking (abaixa sozinha quando você fala)
    music = s.get("music")
    if music and (pdir / "assets" / music).exists():
        inputs += ["-stream_loop", "-1", "-i", str(pdir / "assets" / music)]
        vol = float(s.get("music_volume", 0.15))
        f.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},"
                 f"atrim=0:{total:.3f},afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        f.append(f"[{alabel}]asplit[voz][sc]")
        f.append("[mus][sc]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[duck]")
        f.append("[voz][duck]amix=inputs=2:duration=first:normalize=0[mix]")
        alabel = "mix"
        idx += 1
    f.append(f"[{alabel}]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    script = pdir / "render_filter.txt"
    script.write_text(";\n".join(f), encoding="utf-8")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
           *inputs, "-filter_complex_script", str(script),
           "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
           "-c:v", "h264_videotoolbox", "-b:v", "10M", "-allow_sw", "1", "-profile:v", "high",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    return cmd, total


def render(project, pdir, out_path, on_progress=None):
    cmd, total = build_command(project, pdir, out_path)
    try:
        _run(cmd, total, on_progress)
    except RuntimeError:
        # sem encoder de hardware disponível -> x264 por software
        i = cmd.index("h264_videotoolbox")
        cmd[i - 1:i + 7] = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-pix_fmt", "yuv420p"]
        _run(cmd, total, on_progress)


def _run(cmd, total, on_progress):
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
    for line in p.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and on_progress and total:
            on_progress(min(0.99, int(m.group(1)) / 1e6 / total))
    err = p.stderr.read()
    if p.wait() != 0:
        raise RuntimeError(err[-2000:] or "ffmpeg falhou")

"""Helpers de ffmpeg: descobrir metadados, extrair áudio, gerar miniaturas."""
import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def kind_of(path):
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return "unknown"


def probe(path, user_agent=None):
    """Lê duração, resolução, fps e rotação usando a saída do `ffmpeg -i`
    (o pacote imageio-ffmpeg não traz ffprobe). Aceita caminho local ou URL."""
    ua = ["-user_agent", user_agent] if user_agent else []
    out = subprocess.run([FFMPEG, "-hide_banner", *ua, "-i", str(path)],
                         capture_output=True, text=True, timeout=60).stderr
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 30.0,
            "has_audio": False, "has_video": False, "rotation": 0, "hdr": None}
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if m:
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    for line in out.splitlines():
        if "Stream #" in line and "Video:" in line and not info["has_video"]:
            info["has_video"] = True
            m = re.search(r", (\d{2,5})x(\d{2,5})", line)
            if m:
                info["width"], info["height"] = int(m.group(1)), int(m.group(2))
            if "arib-std-b67" in line:
                info["hdr"] = "hlg"
            elif "smpte2084" in line:
                info["hdr"] = "pq"
            m = re.search(r"([\d.]+) fps", line)
            if m:
                info["fps"] = float(m.group(1))
        if "Stream #" in line and "Audio:" in line:
            info["has_audio"] = True
    # Vídeos de celular gravados em pé vêm com metadado de rotação.
    m = re.search(r"rotat(?:e|ion of)\s*:?\s*(-?[\d.]+)", out)
    if m:
        info["rotation"] = int(round(float(m.group(1)))) % 360
    if m and abs(float(m.group(1))) % 180 == 90:
        info["width"], info["height"] = info["height"], info["width"]
    return info


def extract_audio(src, dst):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
                   check=True)


def thumbnail(src, dst, at=0.5):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(at),
                    "-i", str(src), "-frames:v", "1", "-vf", "scale=320:-2", str(dst)],
                   check=False)


def waveform_peaks(wav_path, buckets=2000):
    """Picos de volume normalizados (0..1) para desenhar a forma de onda na timeline."""
    import array
    import wave
    with wave.open(str(wav_path), "rb") as w:
        n = w.getnframes()
        data = array.array("h", w.readframes(n))
    if not data:
        return []
    step = max(1, len(data) // buckets)
    peaks = [max(abs(x) for x in data[i:i + step]) for i in range(0, len(data), step)]
    top = max(peaks) or 1
    return [round(p / top, 3) for p in peaks]


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


# HDR do iPhone (HLG/PQ) -> SDR com tone mapping suave (sem isso as cores saem lavadas)
TONEMAP = ("zscale=t=linear:npl=300,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:param=0.3:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,eq=saturation=0.9")


def make_proxy(src, out, hdr=None):
    """Cópia leve para a PRÉVIA no navegador: em pé, cor normal (HDR do iPhone convertido) e 720p.
    Sem isso, o navegador mostra HDR "estourado" quando a prévia aplica filtros de cor."""
    vf = (TONEMAP + "," if hdr else "") + \
        "scale='if(gt(ih,iw),-2,1280)':'if(gt(ih,iw),1280,-2)',format=yuv420p,sidedata=mode=delete:type=DISPLAYMATRIX"
    base = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf", vf,
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
    for enc in (["-c:v", "h264_videotoolbox", "-b:v", "5M"], ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]):
        r = subprocess.run(base[:7] + base[7:] + enc + [str(out)], capture_output=True)
        if r.returncode == 0:
            return out
    return None


def natural_key(name):
    """Ordem "natural" de nome de arquivo: IMG_2 antes de IMG_10 (câmeras numeram em ordem de gravação)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(name))]


def concat_takes(paths, out, on_progress=None):
    """Junta várias gravações (já na ordem certa) num vídeo só: mesma resolução/fps do 1º,
    HDR convertido para SDR, áudio estéreo 48 kHz (silêncio se uma tomada não tiver áudio)."""
    infos = [probe(p) for p in paths]
    best = max(infos, key=lambda i: i["width"] * i["height"])     # a gravação de maior resolução manda
    W, H = best["width"] or 1080, best["height"] or 1920
    W, H = W - W % 2, H - H % 2
    fps = infos[0]["fps"] or 30
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    for p in paths:
        cmd += ["-i", str(p)]
    parts, chain = [], []
    for i, info in enumerate(infos):
        tm = TONEMAP + "," if info.get("hdr") else ""
        parts.append(f"[{i}:v]{tm}scale={W}:{H}:force_original_aspect_ratio=decrease,"
                     f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[v{i}]")
        if info["has_audio"]:
            parts.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        else:
            parts.append(f"aevalsrc=0|0:s=48000:d={info['duration']:.3f},aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        chain.append(f"[v{i}][a{i}]")
    parts.append("".join(chain) + f"concat=n={len(paths)}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
            "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart"]
    err = b""
    for enc in (["-c:v", "h264_videotoolbox", "-b:v", "24M"], ["-c:v", "libx264", "-preset", "fast", "-crf", "16"]):
        r = subprocess.run(cmd + enc + [str(out)], capture_output=True)
        if r.returncode == 0:
            return out
        err = r.stderr
    raise RuntimeError("Falha ao juntar os vídeos: " + err.decode(errors="ignore")[-300:])

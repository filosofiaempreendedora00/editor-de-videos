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
            "has_audio": False, "has_video": False}
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
            m = re.search(r"([\d.]+) fps", line)
            if m:
                info["fps"] = float(m.group(1))
        if "Stream #" in line and "Audio:" in line:
            info["has_audio"] = True
    # Vídeos de celular gravados em pé vêm com metadado de rotação.
    m = re.search(r"rotat(?:e|ion of)\s*:?\s*(-?[\d.]+)", out)
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

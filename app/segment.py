"""Recorte de fundo (pessoa x fundo) com MediaPipe, rodando local.

Gera `mask.mp4`: um vídeo em tons de cinza do mesmo tamanho/tempo do original
(branco = pessoa). O render usa essa máscara para: texto atrás da pessoa, fundo
desfocado/escurecido e outros efeitos de composição.
"""
import subprocess
from pathlib import Path

import httpx
import numpy as np

from .media import FFMPEG, probe

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "selfie_segmenter.tflite"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
             "selfie_segmenter/float16/latest/selfie_segmenter.tflite")
MASK_WIDTH = 384  # resolução de análise (a máscara é suavizada e ampliada no render)


def ensure_model():
    if not MODEL.exists():
        MODEL.parent.mkdir(exist_ok=True)
        r = httpx.get(MODEL_URL, timeout=60, follow_redirects=True)
        r.raise_for_status()
        MODEL.write_bytes(r.content)
    return MODEL


def build_mask(src, out, on_progress=None):
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    info = probe(src)
    w = MASK_WIDTH
    h = int(round(info["height"] * w / info["width"] / 2)) * 2
    fps = info["fps"] or 30
    total = max(1, int(info["duration"] * fps))

    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_model())),
        running_mode=vision.RunningMode.VIDEO, output_confidence_masks=True))

    dec = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(src),
                            "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
                            "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
                            str(out)], stdin=subprocess.PIPE)
    size = w * h * 3
    prev = None
    k = 0
    try:
        while True:
            buf = dec.stdout.read(size)
            if len(buf) < size:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            res = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=frame),
                                        int(k * 1000 / fps))
            m = res.confidence_masks[0].numpy_view().astype(np.float32)
            if m.ndim == 3:
                m = m[..., 0]
            # suavização temporal para a borda não "tremer"
            prev = m if prev is None else prev * 0.35 + m * 0.65
            alpha = np.clip((prev - 0.25) / 0.5, 0, 1)
            enc.stdin.write((alpha * 255).astype(np.uint8).tobytes())
            k += 1
            if on_progress and k % 15 == 0:
                on_progress(min(0.99, k / total))
    finally:
        enc.stdin.close()
        enc.wait()
        dec.wait()
        seg.close()
    if enc.returncode != 0:
        raise RuntimeError("Falha ao gerar a máscara de recorte.")
    return out

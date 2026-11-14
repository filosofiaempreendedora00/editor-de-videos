"""🎙 Ditado (13/11 — "quero editar falando, não apenas escrevendo"): o áudio gravado no navegador (observação do
editor, 💬 comentário e 🎬 sugestão de edição no roteiro) vira texto aqui, 100% local, com o Whisper large-v3-turbo
na GPU do Mac — o mesmo das transcrições, com o vocabulário dele (nomes e marcas saem certos).
O modelo fica carregado enquanto ele dita e sai da memória depois de alguns minutos parado (Mac de 8 GB)."""
import subprocess
import threading
import time

import numpy as np

from . import transcribe
from .media import FFMPEG

SR = 16000
OCIOSO = 180            # s parado → o modelo sai da memória
_lock = threading.Lock()
_ultimo = [0.0]


def _decode(data):
    """webm/opus (Chrome), mp4/aac (Safari)… → float32 16 kHz mono."""
    r = subprocess.run([FFMPEG, "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
                       input=data, capture_output=True)
    if r.returncode != 0:
        raise ValueError("não consegui ler o áudio gravado: " + r.stderr.decode(errors="ignore")[-200:])
    return np.frombuffer(r.stdout, np.float32).copy()


def _fala(audio):
    """Tem voz? (ditado em silêncio faz o Whisper inventar "Obrigado." / "Legendas pela comunidade…")"""
    if len(audio) < SR * 0.3:
        return False
    win = SR // 50
    n = len(audio) // win
    rms = np.sqrt((audio[:n * win].reshape(n, win) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    return float(np.percentile(db, 95)) > -45 and float(np.percentile(db, 95) - np.percentile(db, 10)) > 12


def _libera_depois():
    def run():
        while True:
            time.sleep(30)
            with _lock:
                if _ultimo[0] and time.time() - _ultimo[0] > OCIOSO:
                    try:
                        from mlx_whisper.transcribe import ModelHolder
                        ModelHolder.model, ModelHolder.model_path = None, None
                        import gc

                        import mlx.core as mx
                        gc.collect()
                        (getattr(mx, "clear_cache", None) or mx.metal.clear_cache)()
                    except Exception:  # noqa: BLE001
                        pass
                    _ultimo[0] = 0.0
                    return
    threading.Thread(target=run, daemon=True).start()


def transcrever(data):
    """bytes do áudio → {"text": "…"} (vazio se não houver fala)."""
    audio = _decode(data)
    if not _fala(audio):
        return {"text": "", "aviso": "Não ouvi nada — confira o microfone e fale um pouco mais perto."}
    prompt = ("Observação de edição de vídeo, em português do Brasil, com pontuação. Jargão: tvzinha, tela dividida, "
              "B-roll, gancho, legenda, frase de destaque, motion, zoom, print, take, pós-hook, transição.")
    voc = transcribe.vocabulary()
    if voc:
        prompt += " Termos: " + ", ".join(voc[:60]) + "."
    with _lock:
        primeira = not _ultimo[0]
        if transcribe.engine() == "mlx":
            import mlx_whisper
            r = mlx_whisper.transcribe(audio, path_or_hf_repo=transcribe.MLX_REPOS.get(transcribe.MODEL_SIZE, transcribe.MODEL_SIZE),
                                       language="pt", condition_on_previous_text=False, initial_prompt=prompt,
                                       verbose=None, temperature=(0.0,), compression_ratio_threshold=2.2,
                                       hallucination_silence_threshold=1.0)
            segs = r.get("segments", [])
            text = " ".join(s["text"].strip() for s in segs if transcribe._good_segment(s))
        else:
            words = transcribe._fw_words(audio, "small", "pt", prompt)
            text = "".join(w[0] for w in words)
        _ultimo[0] = time.time()
    if primeira:
        _libera_depois()
    return {"text": _grafia(" ".join(text.split()), voc)}


JARGAO = [(r"\b(?:ti|te)\s?v[ieê]\s?zinha\b", "tvzinha"), (r"\bt\.?\s?v\.?\s?zinha\b", "tvzinha"),
          (r"\bb[iy]?[\s-]?r[oó]l+s?\b", "B-roll"), (r"\bp[oó]s[\s-]?(?:h|r)[oóu]+(?:ck|k|que)\b", "pós-hook")]


def _grafia(text, voc):
    """Jargão de edição e nomes do vocabulário com a grafia certa ("liquid death" → "Liquid Death")."""
    import re
    for pat, rep in JARGAO:
        text = re.sub(pat, rep, text, flags=re.I)
    for t in sorted(voc, key=len, reverse=True):
        if len(t) < 3 or (t.isupper() and len(t) > 3):       # "SÉRIA" (ênfase) não vira regra de grafia
            continue
        text = re.sub(r"(?<![\wÀ-ÿ])" + re.escape(t) + r"(?![\wÀ-ÿ])", t, text, flags=re.I)
    return text

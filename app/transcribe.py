"""Transcrição local com timestamps por palavra.

Usa o Whisper large-v3-turbo na GPU do Mac (mlx-whisper) — preciso e rápido.
Sem Apple Silicon/mlx, cai para o faster-whisper na CPU.
O vocabulário (vocabulario.txt + do projeto) orienta nomes, marcas e termos.
"""
import os
import re
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VOCAB_FILE = ROOT / "vocabulario.txt"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "large-v3-turbo")

MLX_REPOS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "tiny": "mlx-community/whisper-tiny-mlx",
}

_fw_models = {}


def engine():
    try:
        import mlx.core  # noqa: F401
        import mlx_whisper  # noqa: F401
        return "mlx"
    except Exception:  # noqa: BLE001
        return "faster-whisper"


def vocabulary(extra=None):
    terms = []
    if VOCAB_FILE.exists():
        terms += [t.strip() for t in re.split(r"[\n,;]+", VOCAB_FILE.read_text(encoding="utf-8")) if t.strip()]
    terms += list(extra or [])
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def add_vocabulary(terms):
    cur = vocabulary()
    low = {t.lower() for t in cur}
    new = [t for t in terms if t and t.lower() not in low]
    if new:
        VOCAB_FILE.write_text("\n".join(cur + new) + "\n", encoding="utf-8")
    return new


def _prompt(vocab):
    # Um prompt curto e natural em PT: melhora pontuação e grafia de termos sem induzir alucinação.
    base = "Transcrição fiel, com pontuação, de um vídeo em português do Brasil."
    if vocab:
        base += " Termos: " + ", ".join(vocab[:60]) + "."
    return base


def _load_wav(path):
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def transcribe(wav_path, language="pt", size=None, on_progress=None, vocab=None):
    size = size or MODEL_SIZE
    prompt = _prompt(vocabulary(vocab)) if (language or "pt") == "pt" else None
    if engine() == "mlx":
        import mlx_whisper
        if on_progress:
            on_progress(0.1)
        r = mlx_whisper.transcribe(_load_wav(wav_path), path_or_hf_repo=MLX_REPOS.get(size, size),
                                   language=language or None, word_timestamps=True,
                                   condition_on_previous_text=False, initial_prompt=prompt, verbose=None)
        raw = [(w["word"], float(w["start"]), float(w["end"]), float(w.get("probability", 1)))
               for s in r["segments"] for w in s.get("words", [])]
    else:
        from faster_whisper import WhisperModel
        if size not in _fw_models:
            _fw_models[size] = WhisperModel(size, device="cpu", compute_type="int8")
        segments, info = _fw_models[size].transcribe(
            str(wav_path), language=language or None, word_timestamps=True, beam_size=5,
            vad_filter=False, condition_on_previous_text=False, initial_prompt=prompt)
        raw = []
        for seg in segments:
            raw += [(w.word, w.start, w.end, w.probability) for w in seg.words or []]
            if on_progress and info.duration:
                on_progress(min(0.99, seg.end / info.duration))
    words = []
    for text, a, b, p in raw:
        text = text.strip()
        if text:
            words.append({"w": text, "start": round(a, 3), "end": round(b, 3), "p": round(p, 2)})
    for i, w in enumerate(words):
        w["i"] = i
    if on_progress:
        on_progress(1.0)
    return words


def replace_text(words, i0, i1, text):
    """Troca o texto das palavras i0..i1 mantendo os índices (e portanto cortes e inserções).
    Se o texto novo tiver mais palavras, as extras ficam juntas na última posição;
    se tiver menos, as posições que sobram ficam vazias (somem da legenda)."""
    toks = text.split()
    slots = list(range(i0, i1 + 1))
    if len(toks) >= len(slots):
        parts = toks[:len(slots) - 1] + [" ".join(toks[len(slots) - 1:])]
    else:
        parts = toks + [""] * (len(slots) - len(toks))
    for i, t in zip(slots, parts):
        words[i]["w"] = t
        words[i]["p"] = 1.0
        words[i]["edited"] = True
    return words

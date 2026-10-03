"""Transcrição local com timestamps por palavra (faster-whisper, roda offline)."""
import os

_models = {}

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")


def _model(size):
    if size not in _models:
        from faster_whisper import WhisperModel
        _models[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _models[size]


def transcribe(wav_path, language="pt", size=None, on_progress=None):
    model = _model(size or MODEL_SIZE)
    segments, info = model.transcribe(
        str(wav_path),
        language=language or None,
        word_timestamps=True,
        vad_filter=False,
        # evita que o Whisper entre em loop repetindo frases em trechos difíceis
        condition_on_previous_text=False,
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            words.append({"w": text, "start": round(w.start, 3), "end": round(w.end, 3)})
        if on_progress and info.duration:
            on_progress(min(0.99, seg.end / info.duration))
    for i, w in enumerate(words):
        w["i"] = i
    return words

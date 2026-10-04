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


# ------------------------------------------------------------------ análise do áudio

FRAME = 0.02  # 20 ms


def energy(audio, sr=16000):
    fr = int(sr * FRAME)
    n = len(audio) // fr
    return np.sqrt((audio[:n * fr].reshape(n, fr) ** 2).mean(1) + 1e-12)


def voice_activity(audio, sr=16000):
    """Máscara de "há som de voz" por quadro de 20 ms, com limiar adaptado ao volume da gravação."""
    rms = energy(audio, sr)
    if not len(rms):
        return rms > 0, rms, 0.0
    noise = np.percentile(rms, 10)
    loud = np.percentile(rms, 90)
    thr = max(noise * 2.5, noise + (loud - noise) * 0.12)
    voiced = rms > thr
    # tapa buracos curtos (< 200 ms) e ignora estalos (< 120 ms)
    v = voiced.copy()
    runs = _runs(v)
    for a, b, val in runs:
        if not val and (b - a) * FRAME < 0.2 and a > 0 and b < len(v):
            v[a:b] = True
    for a, b, val in _runs(v):
        if val and (b - a) * FRAME < 0.12:
            v[a:b] = False
    return v, rms, thr


def _runs(mask):
    out, start = [], 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            out.append((start, i, bool(mask[start])))
            start = i
    return out


def speech_regions(mask, max_len=10.0, join_gap=0.45, pad=0.3, total=None):
    """Junta quadros com voz em trechos de até ~24 s, cortando sempre em pausas.
    Trechos curtos (< 1,8 s) sempre se juntam ao vizinho: sozinhos o Whisper erra por falta de contexto."""
    regs = [(a * FRAME, b * FRAME) for a, b, val in _runs(mask) if val]
    out = []
    for a, b in regs:
        if out:
            gap = a - out[-1][1]
            short = (out[-1][1] - out[-1][0] < 1.8) or (b - a < 1.8)
            if (gap < join_gap or (short and gap < 1.6)) and b - out[-1][0] <= max_len:
                out[-1] = (out[-1][0], b)
                continue
        out.append((a, b))
    end = total if total else (len(mask) * FRAME)
    return [(max(0.0, a - pad), min(end, b + pad)) for a, b in out]


def silences(wav_path, min_len=0.25):
    """Trechos sem voz (silêncio/respiração fraca) — usados para cortar pausas que o Whisper "cobriu"."""
    audio = _load_wav(wav_path)
    mask, _, _ = voice_activity(audio)
    return [[round(a * FRAME, 2), round(b * FRAME, 2)] for a, b, val in _runs(mask)
            if not val and (b - a) * FRAME >= min_len]


# ------------------------------------------------------------------ transcrição

HALLUCINATIONS = {"tchau", "tchau tchau", "obrigado", "obrigada", "valeu", "legendas pela comunidade amara.org",
                  "inscreva-se", "até a próxima", "e aí", "sous-titres", "amara.org", "amém", "música"}


def _good_segment(seg):
    """Descarta o que o Whisper "inventa" em ruído: repetição em loop, baixa confiança, frases-fantasma."""
    text = seg.get("text", "").strip().lower().strip(".!?,")
    if seg.get("compression_ratio", 0) > 2.2:
        return False
    if seg.get("avg_logprob", 0) < -1.0 and seg.get("no_speech_prob", 0) > 0.4:
        return False
    if seg.get("avg_logprob", 0) < -1.4:
        return False
    if text in HALLUCINATIONS and seg.get("avg_logprob", 0) < -0.5:
        return False
    toks = text.split()
    if len(toks) >= 6 and len(set(toks)) <= 2:
        return False
    return True


def _mlx_words(audio, size, language, prompt):
    import mlx_whisper
    r = mlx_whisper.transcribe(audio, path_or_hf_repo=MLX_REPOS.get(size, size),
                               language=language or None, word_timestamps=True,
                               condition_on_previous_text=False, initial_prompt=prompt, verbose=None,
                               temperature=(0.0,), compression_ratio_threshold=2.2,
                               hallucination_silence_threshold=1.0)
    return [(w["word"], float(w["start"]), float(w["end"]), float(w.get("probability", 1)))
            for s in r["segments"] if _good_segment(s) for w in s.get("words", [])]


def _fw_words(audio, size, language, prompt):
    from faster_whisper import WhisperModel
    if size not in _fw_models:
        _fw_models[size] = WhisperModel(size, device="cpu", compute_type="int8")
    segments, _ = _fw_models[size].transcribe(audio, language=language or None, word_timestamps=True,
                                              beam_size=5, vad_filter=False, condition_on_previous_text=False,
                                              initial_prompt=prompt, hallucination_silence_threshold=1.0)
    return [(w.word, w.start, w.end, w.probability) for seg in segments
            if _good_segment({"text": seg.text, "compression_ratio": seg.compression_ratio,
                              "avg_logprob": seg.avg_logprob, "no_speech_prob": seg.no_speech_prob})
            for w in seg.words or []]


def transcribe(wav_path, language="pt", size=None, on_progress=None, vocab=None):
    """Transcreve trecho de fala por trecho de fala. Assim o Whisper não "engole" frases
    repetidas (regravações) nem perde falas depois de pausas longas."""
    size = size or MODEL_SIZE
    prompt = _prompt(vocabulary(vocab)) if (language or "pt") == "pt" else None
    audio = _load_wav(wav_path)
    sr = 16000
    mask, _, _ = voice_activity(audio, sr)
    regions = speech_regions(mask, total=len(audio) / sr) or [(0.0, len(audio) / sr)]
    run = _mlx_words if engine() == "mlx" else _fw_words
    raw = []
    for n, (a, b) in enumerate(regions):
        chunk = audio[int(a * sr):int(b * sr)]
        if len(chunk) < sr * 0.2:
            continue
        for text, s0, s1, p in run(chunk, size, language, prompt):
            raw.append((text, a + s0, a + s1, p))
        if on_progress:
            on_progress((n + 1) / len(regions))
    raw.sort(key=lambda x: x[1])
    # rede de segurança: trecho com voz (≥ 0,8 s) que ficou sem nenhuma palavra é transcrito de novo, sozinho
    covered = np.zeros(len(mask), bool)
    for _, s0, s1, _ in raw:
        covered[int(s0 / FRAME):int(s1 / FRAME) + 1] = True
    for a, b, val in _runs(mask & ~covered):
        if val and (b - a) * FRAME >= 0.8:
            t0, t1 = max(0.0, a * FRAME - 0.3), min(len(audio) / sr, b * FRAME + 0.3)
            for text, s0, s1, p in run(audio[int(t0 * sr):int(t1 * sr)], size, language, prompt):
                raw.append((text, t0 + s0, t0 + s1, p))
    raw.sort(key=lambda x: x[1])
    words = []
    for text, a, b, p in raw:
        text = text.strip()
        if not text:
            continue
        if words and a < words[-1]["end"] - 0.05 and text == words[-1]["w"]:
            continue  # duplicata na fronteira de dois trechos
        words.append({"w": text, "start": round(a, 3), "end": round(max(b, a + 0.05), 3), "p": round(p, 2)})
    words = _drop_loops(words)
    _trim_stretched(words, mask)
    words = _main_voice_pass(words, audio, sr, run, size, language, prompt)
    for i, w in enumerate(words):
        w["i"] = i
    return words


def _level_db(rms, t0, t1):
    a, b = int(t0 / FRAME), max(int(t0 / FRAME) + 1, int(t1 / FRAME))
    seg = rms[a:b]
    # pico "sustentado" (95%): palavras esticadas sobre silêncio não ficam artificialmente baixas
    return float(20 * np.log10(np.percentile(seg, 95) + 1e-9)) if len(seg) else -99.0


def _main_voice_pass(words, audio, sr, run, size, language, prompt):
    """Separa a voz principal (perto do microfone) de vozes de fundo (alguém falando longe,
    soprando o texto, comentando). Marca cada palavra com o nível em dB e com `bg` quando ela
    está bem abaixo da voz principal; depois transcreve de novo trechos ALTOS (voz principal)
    que ficaram sem palavras — o Whisper costuma pular a repetição de uma frase recém-dita."""
    if not words:
        return words
    rms = energy(audio, sr)
    for w in words:
        w["db"] = round(_level_db(rms, w["start"], w["end"]), 1)
    main = voice_level(words)
    if main is None:
        return words
    loud_thr = 10 ** ((main - 9) / 20)
    loud = rms > loud_thr
    # tapa buracos curtos
    for a, b, val in _runs(loud):
        if not val and (b - a) * FRAME < 0.25:
            loud[a:b] = True
    covered = np.zeros(len(loud), bool)
    for w in words:
        if w["db"] >= main - 9:
            covered[int(w["start"] / FRAME):int(w["end"] / FRAME) + 1] = True
    extra = []
    for a, b, val in _runs(loud & ~covered):
        if val and (b - a) * FRAME >= 0.6:
            t0, t1 = max(0.0, a * FRAME - 0.25), min(len(audio) / sr, b * FRAME + 0.25)
            for text, s0, s1, p in run(audio[int(t0 * sr):int(t1 * sr)], size, language, prompt):
                text = text.strip()
                if not text:
                    continue
                w = {"w": text, "start": round(t0 + s0, 3), "end": round(max(t0 + s1, t0 + s0 + 0.05), 3),
                     "p": round(p, 2), "recovered": True}
                w["db"] = round(_level_db(rms, w["start"], w["end"]), 1)
                # descarta o que só repete palavras que já existem no mesmo instante
                if not any(abs(x["start"] - w["start"]) < 0.15 and x["w"].lower() == text.lower() for x in words):
                    extra.append(w)
    words = sorted(words + extra, key=lambda x: x["start"])
    for w in words:
        w["bg"] = w["db"] < main - 9
    return words


def voice_level(words):
    """Nível (dB) típico da voz principal: o patamar das palavras mais altas."""
    levels = sorted(w["db"] for w in words if w.get("db", -99) > -90)
    if len(levels) < 8:
        return None
    return float(np.percentile(levels, 75))


def _drop_loops(words):
    out = []
    for w in words:
        if len(out) >= 3 and all(x["w"].lower() == w["w"].lower() for x in out[-3:]):
            continue
        out.append(w)
    # se sobrou um "rabo" de 3 iguais seguidos, também sai
    clean, k = [], 0
    while k < len(out):
        j = k
        while j + 1 < len(out) and out[j + 1]["w"].lower() == out[k]["w"].lower():
            j += 1
        if j - k + 1 >= 3:
            k = j + 1
            continue
        clean.extend(out[k:j + 1])
        k = j + 1
    return clean


def _trim_stretched(words, mask):
    """O Whisper às vezes estica uma palavra por cima de um "hmmm"/silêncio. Se a palavra durar
    muito mais que o normal, encolhe a ponta que não tem voz (ou a sobra do fim)."""
    for w in words:
        expected = 0.08 * len(w["w"]) + 0.25
        dur = w["end"] - w["start"]
        if dur < max(0.8, expected * 2.2):
            continue
        a, b = int(w["start"] / FRAME), int(w["end"] / FRAME)
        seg = mask[a:b]
        if seg.any():
            first = int(np.argmax(seg))
            last = len(seg) - int(np.argmax(seg[::-1]))
            w["start"] = round((a + first) * FRAME, 3)
            w["end"] = round((a + last) * FRAME, 3)
        if w["end"] - w["start"] > expected * 2.2:
            w["end"] = round(w["start"] + expected * 1.6, 3)
            w["stretched"] = True


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

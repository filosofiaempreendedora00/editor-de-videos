"""CLONE — o áudio final da fala, com o "som da sala" dele: o que mais denuncia voz de IA é ela ser limpa demais e no
ritmo errado. Emenda as frases com pausas naturais, acerta a velocidade pelo ritmo REAL dele (medido nas gravações),
casa o timbre do microfone/sala (equalização pelo espectro médio da voz dele) e põe por baixo o ruído de fundo real do
ambiente das gravações, no mesmo nível. Roda no .venv-clone.

Uso: .venv-clone/bin/python tools/clone/audio.py <pasta_da_voz> <saida.wav> <gravação.mov> [<gravação2.mov> …]
"""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import librosa
import numpy as np
import soundfile as sf
from scipy.signal import istft, stft

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 48000


def ler(path, sr=SR, ss=None, t=None):
    cmd = [FFMPEG, "-v", "error"] + (["-ss", f"{ss}"] if ss else []) + (["-t", f"{t}"] if t else []) + \
        ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).copy()


def quadros_rms(x, n=2048, h=512):
    fr = librosa.util.frame(np.pad(x, (n // 2, n // 2)), frame_length=n, hop_length=h)
    return np.sqrt((fr ** 2).mean(0) + 1e-12)


def perfil(gravacoes, seg=40.0):
    """Da voz REAL dele: espectro médio da fala, nível da fala, um leito de ruído de fundo e o ritmo (palavras/s)."""
    fala, ruido, piso = [], [], []
    for g in gravacoes:
        x = ler(g, ss=20, t=seg)
        if len(x) < SR:
            continue
        r = quadros_rms(x)
        lim_f, lim_r = np.percentile(r, 60), np.percentile(r, 15)
        piso.append(np.percentile(r, 10))
        hop = 512
        k = 0
        while k < len(r):
            if r[k] >= lim_f:
                fala.append(x[k * hop:k * hop + hop])
                k += 1
                continue
            j = k
            while j < len(r) and r[j] <= lim_r:
                j += 1
            if j - k >= 12:                         # silêncio contínuo de verdade (≥ ~130 ms): vira leito de ruído
                ruido.append(x[k * hop + 256:j * hop - 256])
            k = max(j, k + 1)
    fala = np.concatenate(fala)
    cf = int(0.02 * SR)
    bed = np.zeros(0, np.float32)
    for seg_ in ruido:                              # emenda com fusão curta (sem estalo entre os pedaços)
        if len(seg_) <= 2 * cf:
            continue
        if len(bed) > cf:
            w = np.linspace(0, 1, cf, dtype=np.float32)
            bed[-cf:] = bed[-cf:] * (1 - w) + seg_[:cf] * w
            bed = np.concatenate([bed, seg_[cf:]])
        else:
            bed = seg_.copy()
    return fala, bed, float(np.median(piso)) if piso else 0.0


def espectro(x):
    f, _, Z = stft(x, SR, nperseg=4096, noverlap=3072)
    return f, 20 * np.log10(np.abs(Z).mean(1) + 1e-9)


def suave_oitava(f, db, frac=3):
    out = np.empty_like(db)
    for i, fi in enumerate(f):
        lo, hi = fi * 2 ** (-0.5 / frac), fi * 2 ** (0.5 / frac)
        m = (f >= lo) & (f <= hi)
        out[i] = db[m].mean() if m.any() else db[i]
    return out


def main():
    pasta, saida, gravs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    meta = json.loads((pasta / "frases.json").read_text())
    partes = []
    for fr in meta["frases"]:
        y, _ = librosa.load(str(pasta / fr["file"]), sr=SR, mono=True)
        y, _ = librosa.effects.trim(y, top_db=38, frame_length=1024, hop_length=256)
        fade = int(0.012 * SR)
        if len(y) > 2 * fade:
            y[:fade] *= np.linspace(0, 1, fade)
            y[-fade:] *= np.linspace(1, 0, fade)
        partes += [y, np.zeros(int(fr.get("pausa", 0.25) * SR), np.float32)]
    voz = np.concatenate(partes[:-1] + [np.zeros(int(0.35 * SR), np.float32)])
    # ritmo: palavras por segundo de FALA (sem as pausas) da gravação real × da voz gerada
    alvo = float(meta.get("ritmo_alvo") or 0)
    if alvo:
        palavras = sum(len(fr["text"].split()) for fr in meta["frases"])
        falado = sum(len(p) for p in partes[0::2]) / SR
        k = float(np.clip(alvo / max(0.1, palavras / falado), 0.88, 1.28))
        if abs(k - 1) > 0.02:                       # atempo (WSOLA, sem mudar o tom)
            tmp = saida.with_suffix(".tmp.wav")
            sf.write(tmp, voz, SR)
            r = subprocess.run([FFMPEG, "-v", "error", "-i", str(tmp), "-af", f"atempo={k:.4f}", "-ac", "1", "-ar", str(SR),
                                "-f", "f32le", "-"], capture_output=True)
            voz = np.frombuffer(r.stdout, np.float32).copy()
            tmp.unlink(missing_ok=True)
        print(f"audio: ritmo {palavras / falado:.2f} → {alvo:.2f} palavras/s (×{k:.2f})", flush=True)
    fala, ruido, piso = perfil(gravs)
    # timbre do microfone/sala: corrige o espectro médio da voz gerada para o da voz real (±10 dB, 1/3 de oitava)
    f, db_real = espectro(fala)
    _, db_gen = espectro(voz)
    corr = np.clip(suave_oitava(f, db_real - db_gen), -10, 10)
    corr -= np.median(corr[(f > 300) & (f < 3000)])
    corr[f < 60] = np.minimum(corr[f < 60], 0)
    _, _, Z = stft(voz, SR, nperseg=4096, noverlap=3072)
    Z *= (10 ** (corr / 20))[:, None]
    _, voz = istft(Z, SR, nperseg=4096, noverlap=3072)
    voz = voz.astype(np.float32)
    # nível: a fala no mesmo RMS da fala real; o ruído de fundo no mesmo nível relativo
    rms = lambda a: float(np.sqrt((a ** 2).mean() + 1e-12))        # noqa: E731
    r_gen = quadros_rms(voz)
    voz *= rms(fala) / max(1e-6, float(np.sqrt((r_gen[r_gen > np.percentile(r_gen, 60)] ** 2).mean())))
    if len(ruido) > SR // 2:                        # o ruído real do ambiente por baixo, no nível da gravação
        bed = np.resize(ruido, len(voz)).astype(np.float32)
        p10 = float(np.percentile(quadros_rms(voz + bed), 10))
        if piso and p10 > 0:                         # o "silêncio" da gravação real tem respiro e cauda da sala: casa o piso
            bed *= float(np.clip(piso / p10, 1.0, 2.0))
        voz = voz + bed
    pico = float(np.abs(voz).max())
    if pico > 0.95:
        voz *= 0.95 / pico
    sf.write(str(saida), voz, SR, subtype="PCM_24")
    print(f"audio: ok {saida} {len(voz) / SR:.1f}s", flush=True)


if __name__ == "__main__":
    main()

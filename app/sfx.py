"""Biblioteca de efeitos sonoros.

Os efeitos padrão são sintetizados com ffmpeg na primeira execução — sem
download, sem licença de terceiros. Para usar efeitos próprios, basta jogar
arquivos .wav/.mp3 na pasta `sfx/` (o nome do arquivo vira o nome do efeito).
"""
import re
import subprocess
from pathlib import Path

from .media import AUDIO_EXT, FFMPEG

ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = ROOT / "sfx"

# nome: (descrição, filtro lavfi)
BUILTIN = {
    "whoosh": ("Whoosh — passagem/transição",
               "anoisesrc=d=0.75:c=pink:a=0.9,highpass=f=350,lowpass=f=3800,"
               "afade=t=in:d=0.32:curve=qsin,afade=t=out:st=0.32:d=0.43:curve=exp,"
               "flanger=delay=4:depth=6:speed=1.2,volume=1.6"),
    "swish": ("Swish — curto e agudo, para texto entrando",
              "anoisesrc=d=0.32:c=white:a=0.7,highpass=f=1800,lowpass=f=7000,"
              "afade=t=in:d=0.12:curve=qsin,afade=t=out:st=0.12:d=0.2:curve=exp,volume=1.1"),
    "pop": ("Pop — elemento aparecendo",
            "aevalsrc='0.9*sin(2*PI*(950-650*t/0.09)*t)*exp(-t*42)':d=0.14:s=48000"),
    "ding": ("Ding — ideia, acerto, número importante",
             "aevalsrc='0.45*sin(2*PI*1568*t)*exp(-3*t)+0.22*sin(2*PI*3136*t)*exp(-5*t)"
             "+0.08*sin(2*PI*4704*t)*exp(-8*t)':d=1.4:s=48000"),
    "impacto": ("Impacto — frase forte, revelação",
                "aevalsrc='0.95*sin(2*PI*(90*exp(-t*4)+36)*t)*exp(-t*3.2)"
                "+0.25*(random(0)*2-1)*exp(-t*28)':d=1.3:s=48000,lowpass=f=2500,alimiter=limit=0.9"),
    "click": ("Click — clique de mouse/botão",
              "aevalsrc='0.8*(random(0)*2-1)*exp(-t*350)+0.4*sin(2*PI*2400*t)*exp(-t*200)':d=0.05:s=48000"),
    "digitando": ("Digitando — teclado",
                  "aevalsrc='0.55*(random(0)*2-1)*exp(-mod(t+0.03*sin(t*37),0.105)*260)':d=1.1:s=48000,"
                  "highpass=f=900,afade=t=out:st=0.9:d=0.2"),
    "riser": ("Riser — tensão crescendo antes de uma revelação",
              "aevalsrc='(0.18*sin(2*PI*(180*t+260*t*t)*1)+0.22*(random(0)*2-1))*pow(t/1.6,2)':d=1.6:s=48000,"
              "highpass=f=250"),
    "camera": ("Câmera — foto/print aparecendo",
               "aevalsrc='0.8*(random(0)*2-1)*(exp(-t*120)+0.7*exp(-abs(t-0.09)*160))':d=0.25:s=48000,"
               "highpass=f=600"),
}


def ensure_library():
    SFX_DIR.mkdir(exist_ok=True)
    for name, (_, filt) in BUILTIN.items():
        out = SFX_DIR / f"{name}.wav"
        if out.exists():
            continue
        raw = SFX_DIR / f".{name}.raw.wav"
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", filt,
                        "-ac", "2", "-ar", "48000", str(raw)], check=False)
        # normaliza o pico em -3 dB para todos terem volume parecido
        info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(raw), "-af", "volumedetect",
                               "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.search(r"max_volume: (-?[\d.]+) dB", info)
        gain = -3.0 - float(m.group(1)) if m else 0.0
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
                        "-af", f"volume={gain:.1f}dB", str(out)], check=False)
        raw.unlink(missing_ok=True)


def library():
    ensure_library()
    items = []
    for f in sorted(SFX_DIR.iterdir()):
        if f.suffix.lower() in AUDIO_EXT:
            desc = BUILTIN.get(f.stem, ("Efeito próprio",))[0]
            items.append({"name": f.stem, "file": f.name, "desc": desc})
    return items


def path_of(name):
    for f in SFX_DIR.iterdir():
        if f.stem == name and f.suffix.lower() in AUDIO_EXT:
            return f
    return None

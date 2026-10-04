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


# Biblioteca curada (pesquisa de out/2026: sons que editores de Reels/TikTok usam em vídeo falado).
# Licenças livres para uso comercial em vídeo: Mixkit Free License e Freesound CC0.
CATALOG = [
 {
  "name": "reverse_expectativa",
  "cat": "Riser & reverse",
  "desc": "Expectativa pós-hook — sino ao contrário que cresce e para seco no corte (padrão dos hooks)",
  "url": None,
  "source": "Sintetizado no editor (livre)",
  "lead": 2.3,
  "gain": -9,
  "maxdur": None
 },
 {
  "name": "reverse_expectativa_longo",
  "cat": "Riser & reverse",
  "desc": "Expectativa longa — mesma ideia, 3,2 s de subida",
  "url": None,
  "source": "Sintetizado no editor (livre)",
  "lead": 3.2,
  "gain": -9,
  "maxdur": None
 },
 {
  "name": "whoosh_ar_leve",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh de ar leve — troca de assunto",
  "url": "https://cdn.freesound.org/previews/701/701104_13504080-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.19,
  "gain": -8,
  "maxdur": 0.9
 },
 {
  "name": "whoosh_ar_in",
  "cat": "Ar (whoosh)",
  "desc": "Sopro de ar curto — texto/destaque entrando",
  "url": "https://cdn.freesound.org/previews/817/817958_6068155-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.1,
  "gain": -7,
  "maxdur": 0.5
 },
 {
  "name": "whoosh_ar_out",
  "cat": "Ar (whoosh)",
  "desc": "Sopro de ar curto — saindo",
  "url": "https://cdn.freesound.org/previews/817/817959_6068155-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.11,
  "gain": -7,
  "maxdur": 0.5
 },
 {
  "name": "whoosh_bambu",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh orgânico (bambu) — corte rápido",
  "url": "https://cdn.freesound.org/previews/719/719637_15601358-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.035,
  "gain": -7,
  "maxdur": 0.5
 },
 {
  "name": "swipe_rapido",
  "cat": "Ar (whoosh)",
  "desc": "Swipe — print/card deslizando",
  "url": "https://cdn.freesound.org/previews/515/515625_6769489-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.08,
  "gain": -6,
  "maxdur": 0.6
 },
 {
  "name": "whoosh_tecido",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh de tecido, grave e macio — zoom/entrada sutil",
  "url": "https://cdn.freesound.org/previews/496/496188_3910073-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.06,
  "gain": -6,
  "maxdur": 0.5
 },
 {
  "name": "whoosh_bambu_lento",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh grave lento — transição de seção",
  "url": "https://cdn.freesound.org/previews/855/855719_5287430-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.15,
  "gain": -7,
  "maxdur": 0.9
 },
 {
  "name": "whoosh_grave_curto",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh grave e escuro — troca de assunto forte",
  "url": "https://cdn.freesound.org/previews/523/523978_1187042-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.55,
  "gain": -8,
  "maxdur": 1.5
 },
 {
  "name": "whoosh_grave_baixo",
  "cat": "Ar (whoosh)",
  "desc": "Swoosh grave — punch-in de zoom",
  "url": "https://cdn.freesound.org/previews/475/475135_2927958-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.11,
  "gain": -8,
  "maxdur": 0.8
 },
 {
  "name": "whoosh_baixo",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh grave curto — jump cut leve",
  "url": "https://cdn.freesound.org/previews/830/830856_10956972-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.09,
  "gain": -8,
  "maxdur": 0.5
 },
 {
  "name": "whoosh_cinematico",
  "cat": "Ar (whoosh)",
  "desc": "Whoosh cinematográfico — abertura/título",
  "url": "https://cdn.freesound.org/previews/812/812684_8698658-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.105,
  "gain": -8,
  "maxdur": 1.2
 },
 {
  "name": "sub_drop_suave",
  "cat": "Grave",
  "desc": "Sub drop suave — número/revelação",
  "url": "https://cdn.freesound.org/previews/428/428073_4067257-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.0,
  "gain": -4,
  "maxdur": 1.2
 },
 {
  "name": "impacto_grave",
  "cat": "Grave",
  "desc": "Impacto bem grave — frase-chave",
  "url": "https://cdn.freesound.org/previews/541/541029_8698658-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.0,
  "gain": -5,
  "maxdur": 1.5
 },
 {
  "name": "thump_grave",
  "cat": "Grave",
  "desc": "Thump grave — ênfase em palavra",
  "url": "https://cdn.freesound.org/previews/630/630030_9129912-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.02,
  "gain": -4,
  "maxdur": 0.8
 },
 {
  "name": "thump_curto",
  "cat": "Grave",
  "desc": "Thump curto — ênfase discreta",
  "url": "https://cdn.freesound.org/previews/332/332670_950925-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.006,
  "gain": -4,
  "maxdur": 0.3
 },
 {
  "name": "riser_sutil",
  "cat": "Riser & reverse",
  "desc": "Riser sutil — antes da revelação",
  "url": "https://cdn.freesound.org/previews/859/859482_18689440-hq.mp3",
  "source": "Freesound CC0",
  "lead": 3.0,
  "gain": -10,
  "maxdur": 3.0
 },
 {
  "name": "riser_curto",
  "cat": "Riser & reverse",
  "desc": "Riser curto — antes de número",
  "url": "https://cdn.freesound.org/previews/685/685256_12265588-hq.mp3",
  "source": "Freesound CC0",
  "lead": 2.1,
  "gain": -10,
  "maxdur": 3.0
 },
 {
  "name": "reverse_crash_grave",
  "cat": "Riser & reverse",
  "desc": "Crash invertido grave — entrada de seção",
  "url": "https://cdn.freesound.org/previews/674/674292_3130497-hq.mp3",
  "source": "Freesound CC0",
  "lead": 2.7,
  "gain": -10,
  "maxdur": 2.7
 },
 {
  "name": "reverse_cymbal",
  "cat": "Riser & reverse",
  "desc": "Prato invertido — pré-corte",
  "url": "https://cdn.freesound.org/previews/23/23127_135910-hq.mp3",
  "source": "Freesound CC0",
  "lead": 2.0,
  "gain": -10,
  "maxdur": 2.0
 },
 {
  "name": "rewind_escuro",
  "cat": "Riser & reverse",
  "desc": "Rewind escuro — \"volta\"",
  "url": "https://cdn.freesound.org/previews/842/842582_16682330-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.18,
  "gain": -8,
  "maxdur": 0.6
 },
 {
  "name": "click_classico",
  "cat": "Clique & UI",
  "desc": "Clique — sequência de prints/fotos (o que você aprovou)",
  "url": "https://assets.mixkit.co/active_storage/sfx/1117/1117-preview.mp3",
  "source": "Mixkit (licença livre)",
  "lead": 0.0,
  "gain": -6,
  "maxdur": 0.4
 },
 {
  "name": "click_mouse",
  "cat": "Clique & UI",
  "desc": "Clique de mouse real — sequência de prints",
  "url": "https://cdn.freesound.org/previews/678/678248_7806746-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.09,
  "gain": -6,
  "maxdur": 0.3
 },
 {
  "name": "digitando_rapido",
  "cat": "Clique & UI",
  "desc": "Teclado real — texto sendo digitado",
  "url": "https://cdn.freesound.org/previews/813/813214_7987620-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.0,
  "gain": -9,
  "maxdur": 2.1
 },
 {
  "name": "snap_suave",
  "cat": "Clique & UI",
  "desc": "Snap suave — palavra-chave entrando",
  "url": "https://cdn.freesound.org/previews/388/388958_4385633-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.025,
  "gain": -5,
  "maxdur": 0.3
 },
 {
  "name": "pop_seco",
  "cat": "Clique & UI",
  "desc": "Pop seco discreto — palavra-chave",
  "url": "https://cdn.freesound.org/previews/253/253956_1196472-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.0,
  "gain": -6,
  "maxdur": 0.4
 },
 {
  "name": "camera_mirrorless",
  "cat": "Câmera & papel",
  "desc": "Obturador real (mirrorless) — foto/print",
  "url": "https://cdn.freesound.org/previews/249/249750_2896261-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.007,
  "gain": -6,
  "maxdur": 0.5
 },
 {
  "name": "camera_dslr",
  "cat": "Câmera & papel",
  "desc": "Obturador DSLR — foto",
  "url": "https://cdn.freesound.org/previews/661/661279_3040688-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.23,
  "gain": -6,
  "maxdur": 0.95
 },
 {
  "name": "papel_slide",
  "cat": "Câmera & papel",
  "desc": "Papel deslizando — card/print entrando",
  "url": "https://cdn.freesound.org/previews/464/464302_775844-hq.mp3",
  "source": "Freesound CC0",
  "lead": 1.0,
  "gain": -7,
  "maxdur": 1.6
 },
 {
  "name": "papel_swipe",
  "cat": "Câmera & papel",
  "desc": "Papel (swipe) — prints em sequência",
  "url": "https://cdn.freesound.org/previews/147/147286_2627742-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.44,
  "gain": -6,
  "maxdur": 1.2
 },
 {
  "name": "glitch_curto",
  "cat": "Glitch",
  "desc": "Glitch de ruído — dado/erro/tecnologia",
  "url": "https://cdn.freesound.org/previews/458/458065_1316332-hq.mp3",
  "source": "Freesound CC0",
  "lead": 0.19,
  "gain": -9,
  "maxdur": 0.5
 },
 {
  "name": "whoosh_ar_mixkit",
  "cat": "Ar (whoosh)",
  "desc": "Swell de ar longo — transição",
  "url": "https://assets.mixkit.co/active_storage/sfx/1489/1489-preview.mp3",
  "source": "Mixkit (licença livre)",
  "lead": 0.41,
  "gain": -9,
  "maxdur": 1.5
 },
 {
  "name": "whoosh_impacto_grave",
  "cat": "Grave",
  "desc": "Whoosh + impacto grave — título/revelação",
  "url": "https://assets.mixkit.co/active_storage/sfx/1143/1143-preview.mp3",
  "source": "Mixkit (licença livre)",
  "lead": 0.28,
  "gain": -7,
  "maxdur": 2.0
 }
]

# nomes antigos/genéricos -> efeito padrão da biblioteca
# arquivos da biblioteca anterior (datada) — não aparecem mais na lista
RETIRED = {"whoosh_rapido", "swoosh_curto", "swoosh_sweep", "whoosh_zoom", "pop_longo", "pop_bolha",
           "pop_whoosh_leve", "click_ui", "boom_grave", "boom_c", "impacto_trailer", "impacto_whoosh",
           "camera_click", "camera_digital", "digitando_curto", "notif_msg", "notif_positiva", "kaching",
           "moedas", "ding_balcao", "ding_conquista", "ding_correto", "scratch_vinil", "buzzer_errado",
           "badum_tss", "boing", "grilo", "brilho", "brilho_transicao", "tic_tac", "rebobinar",
           "batida_coracao", "papel_slide_old"}

# --- sons SINTETIZADOS aqui (sem download, sem licença de terceiros) -------------------------------------
# "reverse_expectativa": recriado a partir da análise do Reel de referência (instagram.com/p/Dd4qhPrBCgr):
# um sino/nota metálica tocado AO CONTRÁRIO — os parciais graves entram primeiro (~1,1 kHz e 1,4 kHz), os agudos
# vão entrando (1,8 → 2,2 → 2,6 → 3,1 kHz), o volume sobe sem parar e tudo PARA SECO no corte pós-hook.
# (frequência Hz, nível dB no fim, quanto tempo antes do fim o parcial "aparece" — a -45 dB, medido na referência)
_REVERSE_BELL = [(528, -16, 1.6), (786, -5, 1.45), (1082, 0, 2.15), (1424, -2.5, 1.85), (1801, -7, 1.15),
                 (2207, -9, 0.65), (2646, -12, 0.35), (3110, -14, 0.28), (3400, -15, 0.25), (5752, -22, 0.15)]


def _synth_reverse_bell(dur=2.3, sr=48000, air=0.06):
    import numpy as np
    n = int(dur * sr)
    u = (n - np.arange(n)) / sr                     # segundos que faltam para o fim
    rng = np.random.default_rng(7)
    out = np.zeros((n, 2))
    for k, (fr, lvl, appear) in enumerate(_REVERSE_BELL):
        tau = appear / (45 / 8.686)                 # constante de tempo: -45 dB em `appear` s antes do fim
        env = 10 ** (lvl / 20) * np.exp(-u / tau)
        for ch, det in enumerate((-0.6, 0.6)):      # leve desafinação L/R = largura e brilho
            ph = rng.uniform(0, 2 * np.pi)
            out[:, ch] += env * np.sin(2 * np.pi * (fr + det) * (dur - u) + ph)
    # "ar" invertido bem baixinho (tipo prato ao contrário), só nos agudos
    noise = rng.standard_normal((n, 2))
    noise = np.diff(noise, axis=0, prepend=0)       # puxa para os agudos
    out += air * noise * np.exp(-u / 0.35)[:, None]
    fade_in = np.minimum(1, (dur - u) / 0.05)
    fade_out = np.minimum(1, u / 0.006)             # corte seco, sem estalo
    out *= (fade_in * fade_out)[:, None]
    return out / np.abs(out).max() * 0.7


def _write_wav(path, data, sr=48000):
    import wave
    import numpy as np
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


SYNTH = {"reverse_expectativa": lambda: _synth_reverse_bell(2.3),
         "reverse_expectativa_longo": lambda: _synth_reverse_bell(3.2)}


def ensure_synth():
    SFX_DIR.mkdir(exist_ok=True)
    for name, fn in SYNTH.items():
        out = SFX_DIR / f"{name}.wav"
        if not out.exists():
            raw = SFX_DIR / f".{name}.raw.wav"
            _write_wav(raw, fn())
            _normalize(raw, out, keep_start=True)
            raw.unlink(missing_ok=True)


# nomes antigos (biblioteca anterior, datada) -> equivalente moderno
ALIASES = {"whoosh": "whoosh_ar_leve", "whoosh_rapido": "whoosh_ar_leve", "whoosh_cinematico": "whoosh_cinematico",
           "swish": "whoosh_ar_in", "swoosh_curto": "whoosh_ar_in", "swoosh_sweep": "whoosh_ar_in",
           "whoosh_ar": "whoosh_ar_in", "whoosh_zoom": "whoosh_grave_baixo", "pop": "snap_suave",
           "pop_bolha": "snap_suave", "pop_longo": "snap_suave", "pop_whoosh_leve": "whoosh_ar_in",
           "ding": "snap_suave", "ding_balcao": "snap_suave", "ding_conquista": "thump_curto", "ding_correto": "snap_suave",
           "impacto": "thump_grave", "boom_grave": "thump_grave", "boom_c": "thump_curto", "impacto_trailer": "impacto_grave",
           "impacto_whoosh": "whoosh_impacto_grave", "click": "click_classico", "click_ui": "click_classico",
           "digitando": "digitando_rapido", "digitando_curto": "digitando_rapido", "riser": "riser_curto",
           "camera": "camera_mirrorless", "camera_click": "camera_mirrorless", "camera_digital": "camera_mirrorless",
           "kaching": "thump_curto", "moedas": "thump_curto", "notif_msg": "snap_suave", "notif_positiva": "snap_suave",
           "rebobinar": "rewind_escuro"}
CATEGORY_ORDER = ["Ar (whoosh)", "Clique & UI", "Grave", "Riser & reverse", "Câmera & papel", "Glitch", "Seus efeitos"]


def _normalize(raw, out, maxdur=None, keep_start=False):
    """Deixa todos com o mesmo pico (-3 dB), apara a duração e tira o silêncio inicial
    (exceto risers/reverses, cujo começo silencioso faz parte do efeito)."""
    tmp = out.with_suffix(".tmp.wav")
    af = "afade=t=in:d=0.005" if keep_start else "silenceremove=start_periods=1:start_threshold=-50dB,afade=t=in:d=0.005"
    if maxdur:
        af += f",atrim=0:{maxdur},afade=t=out:st={max(0, maxdur - 0.12):.2f}:d=0.12"
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af", af,
                    "-ac", "2", "-ar", "48000", str(tmp)], check=False)
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(tmp), "-af", "volumedetect", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    m = re.search(r"max_volume: (-?[\d.]+) dB", info)
    gain = -3.0 - float(m.group(1)) if m else 0.0
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(tmp),
                    "-af", f"volume={gain:.1f}dB", str(out)], check=False)
    tmp.unlink(missing_ok=True)


def download_catalog():
    import httpx
    SFX_DIR.mkdir(exist_ok=True)
    for item in CATALOG:
        out = SFX_DIR / f"{item['name']}.wav"
        if out.exists() or not item.get("url"):
            continue
        try:
            r = httpx.get(item["url"], timeout=30, follow_redirects=True,
                          headers={"User-Agent": "EditorDeVideos/0.3"})
            r.raise_for_status()
            raw = SFX_DIR / f".{item['name']}.download"
            raw.write_bytes(r.content)
            _normalize(raw, out, item.get("maxdur"), keep_start=item["lead"] >= 1.0)
            raw.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001  (sem internet: fica com os sintetizados)
            pass


def ensure_library():
    SFX_DIR.mkdir(exist_ok=True)
    ensure_synth()
    return  # os sons sintetizados antigos foram aposentados (soavam datados); fica só a biblioteca curada
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
    meta = {c["name"]: c for c in CATALOG}
    items = []
    for f in sorted(SFX_DIR.iterdir()):
        if f.suffix.lower() not in AUDIO_EXT or f.name.startswith("."):
            continue
        if f.stem in meta:
            c = meta[f.stem]
            items.append({"name": f.stem, "file": f.name, "desc": c["desc"], "cat": c["cat"],
                          "license": c["source"], "lead": c["lead"], "gain": c["gain"]})
        elif f.stem in BUILTIN or f.stem in RETIRED:
            continue
        else:
            items.append({"name": f.stem, "file": f.name, "desc": "Efeito seu", "cat": "Seus efeitos", "license": ""})
    order = {c: n for n, c in enumerate(CATEGORY_ORDER)}
    items.sort(key=lambda x: (order.get(x["cat"], 99), x["name"]))
    return items


def meta_of(name):
    for cand in (name, ALIASES.get(name)):
        for c in CATALOG:
            if c["name"] == cand:
                return c
    return {"lead": 0.0, "gain": -6}


def path_of(name):
    for cand in (name, ALIASES.get(name)):
        if cand and (SFX_DIR / f"{cand}.wav").exists():
            return SFX_DIR / f"{cand}.wav"
    for f in SFX_DIR.iterdir():
        if f.stem == name and f.suffix.lower() in AUDIO_EXT:
            return f
    return None

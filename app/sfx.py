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
  "name": "whoosh_rapido",
  "cat": "Whoosh",
  "desc": "Whoosh rápido — jump cut, troca de cena",
  "url": "https://assets.mixkit.co/active_storage/sfx/1490/1490-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "whoosh_cinematico",
  "cat": "Whoosh",
  "desc": "Whoosh cinematográfico — transição forte",
  "url": "https://assets.mixkit.co/active_storage/sfx/1492/1492-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "whoosh_ar",
  "cat": "Whoosh",
  "desc": "Whoosh de ar — texto/card deslizando",
  "url": "https://assets.mixkit.co/active_storage/sfx/1489/1489-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "whoosh_zoom",
  "cat": "Whoosh",
  "desc": "Whip zoom — punch-in de zoom",
  "url": "https://cdn.freesound.org/previews/486/486234_7254895-hq.mp3",
  "source": "Freesound CC0"
 },
 {
  "name": "swoosh_curto",
  "cat": "Whoosh",
  "desc": "Swoosh curto — troca rápida",
  "url": "https://assets.mixkit.co/active_storage/sfx/3115/3115-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "swoosh_sweep",
  "cat": "Whoosh",
  "desc": "Sweep leve — transição suave",
  "url": "https://assets.mixkit.co/active_storage/sfx/166/166-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "pop_longo",
  "cat": "Pop",
  "desc": "Pop — palavra-chave/emoji aparecendo",
  "url": "https://assets.mixkit.co/active_storage/sfx/2358/2358-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "pop_seco",
  "cat": "Pop",
  "desc": "Pop seco — texto de destaque",
  "url": "https://assets.mixkit.co/active_storage/sfx/2364/2364-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "pop_bolha",
  "cat": "Pop",
  "desc": "Pop bolha — sticker/ícone",
  "url": "https://assets.mixkit.co/active_storage/sfx/2357/2357-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "pop_whoosh_leve",
  "cat": "Pop",
  "desc": "Pop + whoosh leve — texto em explicação",
  "url": "https://assets.mixkit.co/active_storage/sfx/3005/3005-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "click_classico",
  "cat": "Click",
  "desc": "Click — item de lista, cursor",
  "url": "https://assets.mixkit.co/active_storage/sfx/1117/1117-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "click_ui",
  "cat": "Click",
  "desc": "Click de interface — print de tela",
  "url": "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "boom_grave",
  "cat": "Impacto",
  "desc": "Boom grave — frase de efeito (estilo \"vine boom\", livre)",
  "url": "https://assets.mixkit.co/active_storage/sfx/2299/2299-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "boom_c",
  "cat": "Impacto",
  "desc": "Boom seco — ênfase",
  "url": "https://cdn.freesound.org/previews/350/350977_5450487-hq.mp3",
  "source": "Freesound CC0"
 },
 {
  "name": "impacto_trailer",
  "cat": "Impacto",
  "desc": "Impacto de trailer — número grande, título",
  "url": "https://assets.mixkit.co/active_storage/sfx/2908/2908-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "impacto_whoosh",
  "cat": "Impacto",
  "desc": "Whoosh + impacto — entrada dramática",
  "url": "https://assets.mixkit.co/active_storage/sfx/1143/1143-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "riser_curto",
  "cat": "Riser",
  "desc": "Riser — tensão antes da revelação",
  "url": "https://assets.mixkit.co/active_storage/sfx/790/790-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "camera_click",
  "cat": "Câmera",
  "desc": "Câmera — print, foto, flash",
  "url": "https://assets.mixkit.co/active_storage/sfx/1133/1133-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "camera_digital",
  "cat": "Câmera",
  "desc": "Câmera digital — screenshot",
  "url": "https://assets.mixkit.co/active_storage/sfx/1432/1432-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "digitando_curto",
  "cat": "Digitação",
  "desc": "Digitando — texto sendo escrito",
  "url": "https://assets.mixkit.co/active_storage/sfx/1397/1397-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "notif_msg",
  "cat": "Notificação",
  "desc": "Notificação de mensagem — print de DM/comentário",
  "url": "https://assets.mixkit.co/active_storage/sfx/2354/2354-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "notif_positiva",
  "cat": "Notificação",
  "desc": "Notificação positiva — conquista, resultado",
  "url": "https://assets.mixkit.co/active_storage/sfx/951/951-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "kaching",
  "cat": "Dinheiro",
  "desc": "Ka-ching — faturamento, preço",
  "url": "https://cdn.freesound.org/previews/351/351304_96253-hq.mp3",
  "source": "Freesound CC0"
 },
 {
  "name": "moedas",
  "cat": "Dinheiro",
  "desc": "Moedas — lucro, economia",
  "url": "https://assets.mixkit.co/active_storage/sfx/1993/1993-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "ding_balcao",
  "cat": "Ding",
  "desc": "Sino de balcão — acerto, dica",
  "url": "https://assets.mixkit.co/active_storage/sfx/931/931-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "ding_conquista",
  "cat": "Ding",
  "desc": "Sino de conquista — número, meta",
  "url": "https://assets.mixkit.co/active_storage/sfx/600/600-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "ding_correto",
  "cat": "Ding",
  "desc": "Resposta certa — \"isso!\"",
  "url": "https://assets.mixkit.co/active_storage/sfx/2870/2870-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "glitch_curto",
  "cat": "Glitch",
  "desc": "Glitch — virada, erro, tecnologia",
  "url": "https://assets.mixkit.co/active_storage/sfx/2595/2595-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "scratch_vinil",
  "cat": "Humor",
  "desc": "Disco arranhado — \"pera aí\", quebra de expectativa",
  "url": "https://assets.mixkit.co/active_storage/sfx/702/702-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "buzzer_errado",
  "cat": "Humor",
  "desc": "Buzzer de erro — \"errado\", mito",
  "url": "https://assets.mixkit.co/active_storage/sfx/950/950-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "badum_tss",
  "cat": "Humor",
  "desc": "Ba-dum-tss — piada",
  "url": "https://assets.mixkit.co/active_storage/sfx/579/579-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "boing",
  "cat": "Humor",
  "desc": "Boing — algo absurdo",
  "url": "https://assets.mixkit.co/active_storage/sfx/2894/2894-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "grilo",
  "cat": "Humor",
  "desc": "Grilo — silêncio constrangedor",
  "url": "https://assets.mixkit.co/active_storage/sfx/1927/1927-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "brilho",
  "cat": "Brilho",
  "desc": "Brilho mágico — dica de ouro, antes/depois",
  "url": "https://assets.mixkit.co/active_storage/sfx/3062/3062-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "brilho_transicao",
  "cat": "Brilho",
  "desc": "Brilho curto — transição \"clean\"",
  "url": "https://assets.mixkit.co/active_storage/sfx/3060/3060-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "tic_tac",
  "cat": "Tempo",
  "desc": "Tic-tac — urgência, prazo",
  "url": "https://assets.mixkit.co/active_storage/sfx/1063/1063-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "rebobinar",
  "cat": "Tempo",
  "desc": "Rebobinar — flashback, \"volta\"",
  "url": "https://assets.mixkit.co/active_storage/sfx/1092/1092-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "batida_coracao",
  "cat": "Suspense",
  "desc": "Batida de coração — tensão",
  "url": "https://assets.mixkit.co/active_storage/sfx/490/490-preview.mp3",
  "source": "Mixkit"
 },
 {
  "name": "papel_slide",
  "cat": "Whoosh",
  "desc": "Papel deslizando — card/documento entrando",
  "url": "https://assets.mixkit.co/active_storage/sfx/1530/1530-preview.mp3",
  "source": "Mixkit"
 }
]

# nomes antigos/genéricos -> efeito padrão da biblioteca
ALIASES = {"whoosh": "whoosh_rapido", "swish": "swoosh_curto", "pop": "pop_seco", "ding": "ding_balcao",
           "impacto": "boom_grave", "click": "click_ui", "digitando": "digitando_curto", "riser": "riser_curto",
           "camera": "camera_click"}
CATEGORY_ORDER = ["Whoosh", "Pop", "Impacto", "Ding", "Click", "Câmera", "Riser", "Notificação", "Dinheiro",
                  "Digitação", "Glitch", "Brilho", "Humor", "Tempo", "Suspense", "Sintetizados", "Seus efeitos"]


def _normalize(raw, out):
    """Tira o silêncio do começo e deixa todos com o mesmo pico (-3 dB)."""
    tmp = out.with_suffix(".tmp.wav")
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,afade=t=in:d=0.005",
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
        if out.exists():
            continue
        try:
            r = httpx.get(item["url"], timeout=30, follow_redirects=True,
                          headers={"User-Agent": "EditorDeVideos/0.3"})
            r.raise_for_status()
            raw = SFX_DIR / f".{item['name']}.download"
            raw.write_bytes(r.content)
            _normalize(raw, out)
            raw.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001  (sem internet: fica com os sintetizados)
            pass


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
    meta = {c["name"]: c for c in CATALOG}
    items = []
    for f in sorted(SFX_DIR.iterdir()):
        if f.suffix.lower() not in AUDIO_EXT or f.name.startswith("."):
            continue
        if f.stem in meta:
            c = meta[f.stem]
            items.append({"name": f.stem, "file": f.name, "desc": c["desc"], "cat": c["cat"],
                          "license": c["source"]})
        elif f.stem in BUILTIN:
            items.append({"name": f.stem, "file": f.name, "desc": BUILTIN[f.stem][0], "cat": "Sintetizados",
                          "license": "gerado localmente"})
        else:
            items.append({"name": f.stem, "file": f.name, "desc": "Efeito seu", "cat": "Seus efeitos", "license": ""})
    order = {c: n for n, c in enumerate(CATEGORY_ORDER)}
    items.sort(key=lambda x: (order.get(x["cat"], 99), x["name"]))
    return items


def path_of(name):
    for cand in (name, ALIASES.get(name)):
        if cand and (SFX_DIR / f"{cand}.wav").exists():
            return SFX_DIR / f"{cand}.wav"
    for f in SFX_DIR.iterdir():
        if f.stem == name and f.suffix.lower() in AUDIO_EXT:
            return f
    return None

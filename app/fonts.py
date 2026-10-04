"""Fontes usadas nas legendas (Google Fonts, licença OFL — livres para uso comercial).

A legenda padrão usa Montserrat Alternates: geométrica, "a" de um andar, a mais próxima
da referência de estilo. Baixada uma vez para `fonts/`, usada pelo render (libass) e
servida para a prévia no navegador.
"""
import shutil
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserratalternates/"
GOOGLE = ["MontserratAlternates-SemiBold.ttf", "MontserratAlternates-Bold.ttf",
          "MontserratAlternates-ExtraBold.ttf"]
SYSTEM = ["/System/Library/Fonts/Supplemental/Arial Black.ttf",
          "/System/Library/Fonts/Supplemental/Impact.ttf"]

CAPTION_FONT = "Montserrat Alternates"


def ensure():
    FONT_DIR.mkdir(exist_ok=True)
    for name in GOOGLE:
        f = FONT_DIR / name
        if not f.exists():
            try:
                r = httpx.get(BASE + name, timeout=30, follow_redirects=True)
                r.raise_for_status()
                f.write_bytes(r.content)
            except Exception:  # noqa: BLE001  (sem internet: libass cai na fonte padrão)
                pass
    for f in SYSTEM:
        if Path(f).exists() and not (FONT_DIR / Path(f).name).exists():
            shutil.copy(f, FONT_DIR)
    return FONT_DIR

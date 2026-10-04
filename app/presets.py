"""Identidades visuais (paleta + tratamento de cor). Cada uma é um JSON em app/presets/.
A identidade escolhida como padrão vale para os vídeos novos (config.json na raiz)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = Path(__file__).resolve().parent / "presets"
CONFIG = ROOT / "config.json"

BASE = {  # "Padrão" do editor (sem identidade)
    "name": "Padrão do editor", "description": "Legenda branca, destaque dourado amarronzado.",
    "palette": {}, "rules": [],
    "settings": {"look": "none", "caption_color": "#FFFFFF", "caption_outline": "#000000", "caption_box": False,
                 "caption_box_color": "#000000", "caption_box_opacity": 0.6, "accent": "#C29A5B",
                 "panel_color": "#FFFFFF", "panel_line": "#C29A5B", "panel_text": "#111111",
                 "progress_color": "#C29A5B", "flashes": True},
}


def all_presets():
    out = {"padrao": BASE}
    for f in sorted(DIR.glob("*.json")):
        out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return out


def get(slug):
    return all_presets().get(slug or "padrao", BASE)


def default_slug():
    try:
        return json.loads(CONFIG.read_text()).get("style", "padrao")
    except Exception:  # noqa: BLE001
        return "padrao"


def set_default(slug):
    cfg = {}
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text())
    cfg["style"] = slug
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))


def settings_for(slug):
    return {**get(slug)["settings"], "style": slug or "padrao"}


# preferências que o usuário escolhe no editor e que passam a valer para os vídeos novos
STICKY = ("hook_sfx", "hook_transition")


def user_defaults():
    try:
        return json.loads(CONFIG.read_text()).get("defaults", {})
    except Exception:  # noqa: BLE001
        return {}


def remember(settings):
    keep = {k: v for k, v in settings.items() if k in STICKY}
    if not keep:
        return
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    cfg["defaults"] = {**cfg.get("defaults", {}), **keep}
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))

"""Aplica um plano (de qualquer motor) ao projeto: cortes + inserções."""
import time
import uuid

from . import sources


def new_id():
    return uuid.uuid4().hex[:8]


def item_to_overlay(it):
    base = {"id": new_id(), "w0": it["start"], "w1": it["end"], "auto": True, "reason": it.get("reason", "")}
    kind = it.get("kind")
    if kind == "text":
        if not it.get("text"):
            return None
        return {**base, "type": "text", "style": it.get("style") or "title", "text": it["text"]}
    if kind == "sfx" and it.get("sfx"):
        from .sfx import ALIASES
        return {**base, "type": "sfx", "sfx": ALIASES.get(it["sfx"], it["sfx"]), "w1": it["start"]}
    if kind == "zoom":
        return {**base, "type": "zoom"}
    if kind == "transition" and it.get("transition", "flash") == "flash":
        return {**base, "type": "flash", "w1": it["start"]}
    if kind == "emphasis":
        return {**base, "type": "emphasis", "key": it.get("text", "")}
    if kind == "behind" and it.get("text"):
        return {**base, "type": "behind", "text": it["text"]}
    if kind == "perspective":
        return {**base, "type": "perspective"}
    if kind == "broll":
        return {**base, "type": "media", "file": None, "query": it.get("query") or it.get("text", ""),
                "source": it.get("source") or "commons", "layout": it.get("layout") or "full",
                "desc": it.get("text", "")}
    if kind == "motion" and it.get("template"):
        return {**base, "type": "motion", "template": it["template"], "params": it.get("params") or {}}
    return None


# Enquanto B-roll/inserções visuais estão "em pausa", o plano só aplica cortes, legendas de destaque,
# efeitos sonoros, zooms e flashes.
LIGHT_KINDS = {"emphasis", "sfx", "zoom", "transition"}


def apply(project, result, engine, apply_cuts=True):
    """Substitui as inserções automáticas anteriores (as que você editou ficam)."""
    if not project.get("settings", {}).get("inserts", False):
        result = {**result, "items": [it for it in result.get("items", []) if it.get("kind") in LIGHT_KINDS
                                      and it.get("reason") != "foto aparecendo"]}
    words = project.get("words", [])
    from .transcribe import replace_text
    for f in result.get("fixes", []):
        if not any(words[i].get("edited") for i in range(f["start"], f["end"] + 1)):  # não desfaz edição sua
            replace_text(words, f["start"], f["end"], f["text"])
            for i in range(f["start"], f["end"] + 1):
                words[i]["fixed"] = f.get("reason", "corrigido pela IA")
    if apply_cuts:
        dl = set(project.get("deleted", []))
        for c in result.get("cuts", []):
            dl.update(range(c["start"], c["end"] + 1))
        project["deleted"] = sorted(dl)
        project["ai_cuts"] = result.get("cuts", [])
    kept = [o for o in project.get("overlays", []) if not o.get("auto")]
    new = [o for o in (item_to_overlay(it) for it in result.get("items", [])) if o]
    # não deixa inserções novas caírem em palavras cortadas
    deleted = set(project.get("deleted", []))
    for o in new:
        while o["w0"] in deleted and o["w0"] < min(o["w1"], len(words) - 1):
            o["w0"] += 1
    project["overlays"] = kept + new
    project["plan"] = {"engine": engine, "created": time.time(), "analysis": result.get("analysis", {})}
    return project


def ensure_ids(project):
    for o in project.get("overlays", []):
        o.setdefault("id", new_id())


def add_credit(project, result, file):
    project.setdefault("credits", []).append({
        "file": file, "credit": result.get("credit", ""), "license": result.get("license", ""),
        "page_url": result.get("page_url", ""), "source": result.get("source", "")})


PREFERRED_KIND = {"wikipedia": "image", "commons": "image", "arquivo": "video", "nasa": "video",
                  "noticias": "page", "site": "page"}


def autofill(project, assets_dir, on_progress=None):
    """Para cada B-roll sem arquivo, busca na fonte sugerida e usa o melhor resultado."""
    pending = [o for o in project.get("overlays", []) if o.get("type") == "media" and not o.get("file")
               and o.get("source") not in (None, "proprio") and o.get("query")]
    done, errors = 0, []
    for n, o in enumerate(pending):
        if on_progress:
            on_progress(n / max(1, len(pending)), f"Buscando: {o['query']}")
        try:
            results = sources.search(o["source"], o["query"], project.get("language") or "pt")
            want = PREFERRED_KIND.get(o["source"])
            results.sort(key=lambda r: r["kind"] != want)
            if not results and o["source"] != "commons":
                results = sources.search("commons", o["query"])
            if not results:
                errors.append(f"nada encontrado para '{o['query']}'")
                continue
            r = results[0]
            words = project["words"]
            dur = words[min(o["w1"], len(words) - 1)]["end"] - words[o["w0"]]["start"] + 1
            got = sources.fetch(r, assets_dir, start=10.0, length=max(3.0, min(12.0, dur)))
            o["file"] = got["file"]
            if got.get("print"):
                o["print"] = True
                if o.get("layout") == "full":
                    o["layout"] = "card"
            o["found"] = r.get("title", "")
            add_credit(project, r, got["file"])
            done += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{o['query']}: {e}")
    return {"filled": done, "pending": len(pending), "errors": errors}

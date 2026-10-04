"""Banco simples de referências: links (Instagram, TikTok, YouTube…) salvos num arquivo JSON.

Sem banco de dados: `referencias/links.json` é a fonte; `referencias/links.md` é uma cópia legível,
regerada a cada alteração, para consultar em qualquer editor de texto.
"""
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "referencias"
DB = DIR / "links.json"
MD = DIR / "links.md"

KIND_LABEL = {"perfil": "Perfil", "reel": "Reel", "post": "Post", "story": "Story",
              "video": "Vídeo", "link": "Link"}
IG_RESERVED = {"p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct", "about", "legal"}


def normalize(url):
    url = url.strip().strip("<>\"'")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    u = urlparse(url)
    host = re.sub(r"^(www\.|m\.)", "", u.netloc.lower())
    path = re.sub(r"/+$", "", u.path) or ""
    # parâmetros de rastreio (igsh, utm…) não fazem parte do link; YouTube precisa do ?v=
    query = u.query if "youtube.com" in host else ""
    return f"https://{host}{path}" + (f"?{query}" if query else "") + ("/" if "instagram.com" in host else "")


def classify(url):
    """→ (kind, handle, code, site)"""
    u = urlparse(url)
    host = u.netloc
    parts = [p for p in u.path.split("/") if p]
    if "instagram.com" in host:
        if parts and parts[0] in ("reel", "reels", "tv"):
            return "reel", None, parts[1] if len(parts) > 1 else None, "instagram"
        if parts and parts[0] == "p":
            return "post", None, parts[1] if len(parts) > 1 else None, "instagram"
        if parts and parts[0] == "stories":
            return "story", parts[1] if len(parts) > 1 else None, None, "instagram"
        if len(parts) >= 3 and parts[1] in ("reel", "p", "tv"):          # instagram.com/<user>/reel/<code>
            return ("post" if parts[1] == "p" else "reel"), parts[0], parts[2], "instagram"
        if parts and parts[0] not in IG_RESERVED:
            return "perfil", parts[0], None, "instagram"
        return "link", None, None, "instagram"
    if "tiktok.com" in host:
        if len(parts) >= 3 and parts[1] == "video":
            return "video", parts[0].lstrip("@"), parts[2], "tiktok"
        if parts and parts[0].startswith("@"):
            return "perfil", parts[0][1:], None, "tiktok"
        return "video", None, None, "tiktok"
    if "youtube.com" in host or "youtu.be" in host:
        if parts and (parts[0].startswith("@") or parts[0] in ("c", "channel", "user")):
            return "perfil", parts[-1].lstrip("@"), None, "youtube"
        return "video", None, None, "youtube"
    return "link", None, None, host


THUMBS = DIR / "thumbs"
OEMBED = {
    "instagram": "https://www.instagram.com/api/v1/oembed/?url={url}",
    "tiktok": "https://www.tiktok.com/oembed?url={url}",
    "youtube": "https://www.youtube.com/oembed?url={url}&format=json",
}


def enrich(r):
    """Descobre quem é o autor (@), o texto do post e uma miniatura — pelos oEmbed públicos (sem login).
    A miniatura fica em referencias/thumbs/ (vai junto para o GitHub; os links de imagem do IG expiram)."""
    import httpx
    api = OEMBED.get(r.get("site"))
    if not api or r["kind"] == "perfil" and r.get("handle"):
        return r
    try:
        d = httpx.get(api.format(url=r["url"]), timeout=10, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"}).json()
    except Exception:  # noqa: BLE001  (offline, post privado/apagado: fica sem)
        return r
    author = d.get("author_unique_id") or d.get("author_name") or ""
    if r["site"] == "instagram" and r["kind"] == "post" and "/reel/" in (d.get("html") or ""):
        r["kind"] = "reel"                          # link /p/ que na verdade é um Reel
    if r["site"] == "youtube":
        author = (d.get("author_url") or "").rstrip("/").split("/")[-1].lstrip("@") or author
    if author and not r.get("handle"):
        r["handle"] = author.lstrip("@")
    if d.get("title") and not r.get("caption"):
        r["caption"] = re.sub(r"\s+", " ", d["title"]).strip()[:280]
    if d.get("thumbnail_url") and not r.get("thumb"):
        try:
            img = httpx.get(d["thumbnail_url"], timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if img.status_code == 200 and img.content:
                THUMBS.mkdir(parents=True, exist_ok=True)
                (THUMBS / f"{r['id']}.jpg").write_bytes(img.content)
                r["thumb"] = f"thumbs/{r['id']}.jpg"
        except Exception:  # noqa: BLE001
            pass
    return r


def load():
    if not DB.exists():
        return []
    return json.loads(DB.read_text(encoding="utf-8"))


def _save(items):
    DIR.mkdir(exist_ok=True)
    # grava num temporário e troca: um travamento no meio nunca corrompe o arquivo
    fd, tmp = tempfile.mkstemp(dir=DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, DB)
    MD.write_text(markdown(items), encoding="utf-8")
    sync_github()


# ---------------------------------------------------------------- cópia no GitHub (sem banco de dados)
_sync = {"state": "idle", "at": None, "msg": ""}
_sync_lock = threading.Lock()


def sync_status():
    return dict(_sync)


def sync_github(wait=False):
    """Commita SÓ a pasta referencias/ e dá push, em segundo plano. Se falhar (sem internet), tenta de novo
    na próxima alteração — o arquivo local já está salvo de qualquer jeito."""
    def run():
        with _sync_lock:
            _sync.update(state="sending", msg="")
            git = ["git", "-C", str(ROOT)]
            try:
                subprocess.run(git + ["add", "--", "referencias"], check=True, capture_output=True, timeout=30)
                pending = subprocess.run(git + ["diff", "--cached", "--quiet", "--", "referencias"], timeout=30).returncode
                if pending:
                    subprocess.run(git + ["commit", "-q", "-m", "Referências: atualiza links salvos", "--", "referencias"],
                                   check=True, capture_output=True, timeout=30)
                r = subprocess.run(git + ["push", "-q"], capture_output=True, text=True, timeout=90)
                if r.returncode:
                    raise RuntimeError(r.stderr.strip()[-200:] or "push falhou")
                _sync.update(state="ok", at=time.strftime("%Y-%m-%dT%H:%M:%S"))
            except Exception as e:  # noqa: BLE001
                _sync.update(state="error", msg=str(e)[-200:])
    t = threading.Thread(target=run, daemon=True)
    t.start()
    _threads.append(t)
    if wait:
        t.join()


_threads = []


def wait_sync():
    """Para a linha de comando: espera o envio terminar antes de o processo acabar."""
    for t in list(_threads):
        t.join()


def markdown(items):
    out = ["# Referências", "", f"{len(items)} links · gerado automaticamente a partir de `links.json`", ""]
    for r in sorted(items, key=lambda r: r["added"], reverse=True):
        who = f" @{r['handle']}" if r.get("handle") else ""
        tags = " ".join(f"#{t}" for t in r.get("tags", []))
        out.append(f"- **{KIND_LABEL.get(r['kind'], r['kind'])}{who}** ({r['site']}) — {r['url']}")
        if r.get("caption"):
            out.append(f"  - “{r['caption'][:160]}”")
        if r.get("note"):
            out.append(f"  - nota: {r['note']}")
        for l in r.get("learned", []):
            out.append(f"  - ✓ aprendido: {l}")
        if tags:
            out.append(f"  - {tags}")
        out.append(f"  - salvo em {r['added'][:10]}")
    return "\n".join(out) + "\n"


def _tags(tags):
    if isinstance(tags, str):
        tags = re.split(r"[,\s]+", tags)
    return sorted({t.strip().lstrip("#").lower() for t in tags or [] if t.strip().lstrip("#")})


def add(text, note="", tags=None):
    """Aceita um ou vários links (separados por espaço/linha). Repetidos não duplicam: atualizam nota/etiquetas."""
    items = load()
    urls = re.findall(r"(?:https?://)?(?:www\.)?[\w.-]+\.[a-z]{2,}/\S*", text or "")
    added, updated = [], []
    for raw in urls:
        url = normalize(raw)
        old = next((r for r in items if r["url"] == url), None)
        if old:
            if note:
                old["note"] = note
            old["tags"] = _tags(old.get("tags", []) + _tags(tags))
            updated.append(old)
            continue
        kind, handle, code, site = classify(url)
        r = {"id": uuid.uuid4().hex[:8], "url": url, "kind": kind, "handle": handle, "code": code,
             "site": site, "note": note or "", "tags": _tags(tags),
             "added": time.strftime("%Y-%m-%dT%H:%M:%S")}
        items.append(enrich(r))
        added.append(r)
    _save(items)
    return {"added": added, "updated": updated}


def edit(rid, changes):
    items = load()
    for r in items:
        if r["id"] == rid:
            if "note" in changes:
                r["note"] = str(changes["note"])
            if "tags" in changes:
                r["tags"] = _tags(changes["tags"])
            if "learned" in changes:
                r["learned"] = [str(x) for x in changes["learned"]]
            if "handle" in changes:
                r["handle"] = str(changes["handle"]).strip().lstrip("@") or None
            _save(items)
            return r
    raise KeyError(rid)


def remove(rid):
    items = load()
    rest = [r for r in items if r["id"] != rid]
    if len(rest) == len(items):
        raise KeyError(rid)
    (THUMBS / f"{rid}.jpg").unlink(missing_ok=True)
    _save(rest)

"""Busca de materiais na internet — só fontes gratuitas, sem chave de API,
e de preferência fora dos bancos de imagem clichê:

  wikipedia  fotos reais de pessoas, lugares, empresas, eventos + "print" do artigo
  commons    Wikimedia Commons: fotos históricas, documentos, mapas, vídeos
  arquivo    Internet Archive: filmes antigos de domínio público (Prelinger etc.)
  nasa       imagens e vídeos da NASA (domínio público)
  noticias   manchetes recentes (Google Notícias) -> print da matéria
  site       qualquer URL -> print da página

Cada resultado guarda autor/licença; a exportação gera um creditos.txt.
"""
import re
import shutil
import subprocess
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from .media import FFMPEG, probe

UA = "EditorDeVideos/0.2 (https://github.com/filosofiaempreendedora00/editor-de-videos)"
TIMEOUT = 20

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

SOURCES = {
    "wikipedia": "Wikipedia",
    "commons": "Wikimedia Commons",
    "arquivo": "Internet Archive (filmes antigos)",
    "nasa": "NASA",
    "noticias": "Notícias (print da matéria)",
    "site": "Print de site (cole a URL)",
}


def _get(url, **params):
    r = httpx.get(url, params=params or None, headers={"User-Agent": UA}, timeout=TIMEOUT,
                  follow_redirects=True)
    r.raise_for_status()
    return r


def _clean_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


WM_SIZES = (3840, 2560, 1920, 1280, 960, 500)


def _wm_big(thumb_url, original_url, original_width):
    """Versão grande de uma imagem do Wikimedia (só aceita larguras padronizadas)."""
    if not thumb_url or "/thumb/" not in thumb_url:
        return original_url
    for w in WM_SIZES:
        if w <= min(original_width or 0, 1920):
            return re.sub(r"/(\d+)px-", f"/{w}px-", thumb_url, count=1)
    return original_url


# ---------------------------------------------------------------- buscas

def search(source, query, lang="pt"):
    fn = {
        "wikipedia": _wikipedia, "commons": _commons, "arquivo": _archive, "nasa": _nasa,
"noticias": _news, "site": _site,
    }.get(source)
    if not fn:
        raise ValueError(f"fonte desconhecida: {source}")
    return fn(query, lang)


def _wikipedia(query, lang):
    out = []
    for lg in dict.fromkeys([lang or "pt", "en"]):
        data = _get(f"https://{lg}.wikipedia.org/w/api.php", action="query", generator="search",
                    gsrsearch=query, gsrlimit=8, prop="pageimages|info|extracts", exintro=1,
                    explaintext=1, exchars=200, piprop="thumbnail|original", pithumbsize=480,
                    inprop="url", format="json").json()
        pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        for p in pages:
            title, url = p["title"], p.get("fullurl")
            if p.get("original"):
                out.append({
                    "id": f"wp-img-{lg}-{p['pageid']}", "source": "wikipedia", "kind": "image",
                    "title": title, "thumb": p["thumbnail"]["source"],
                    "url": _wm_big(p["thumbnail"]["source"], p["original"]["source"], p["original"]["width"]),
                    "page_url": url, "credit": f"Imagem do artigo '{title}' (Wikipedia/Wikimedia Commons)",
                    "license": "ver página do arquivo"})
            out.append({
                "id": f"wp-page-{lg}-{p['pageid']}", "source": "wikipedia", "kind": "page",
                "title": f"Print do artigo: {title}", "desc": p.get("extract", ""),
                "thumb": p.get("thumbnail", {}).get("source"), "url": url, "page_url": url,
                "credit": f"Wikipedia — {title}", "license": "CC BY-SA"})
        if out:
            break
    return out


def _commons(query, lang):
    out = []
    for ftype, kind in (("bitmap", "image"), ("video", "video")):
        data = _get("https://commons.wikimedia.org/w/api.php", action="query", generator="search",
                    gsrsearch=f"{query} filetype:{ftype}", gsrnamespace=6,
                    gsrlimit=18 if kind == "image" else 8, prop="imageinfo",
                    iiprop="url|size|mime|extmetadata", iiurlwidth=480,
                    iiextmetadatafilter="Artist|LicenseShortName|ImageDescription",
                    format="json").json()
        pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii.get("url"):
                continue
            meta = ii.get("extmetadata", {})
            artist = _clean_html(meta.get("Artist", {}).get("value", ""))
            lic = meta.get("LicenseShortName", {}).get("value", "")
            title = p["title"].removeprefix("File:").removeprefix("Arquivo:")
            url = ii["url"]
            if kind == "image":
                url = _wm_big(ii.get("thumburl"), url, ii.get("width"))
            out.append({
                "id": f"cm-{p['pageid']}", "source": "commons", "kind": kind, "title": title,
                "thumb": ii.get("thumburl"), "url": url, "page_url": ii.get("descriptionurl"),
                "duration": ii.get("duration"),
                "credit": f"{title} — {artist or 'autor desconhecido'} (Wikimedia Commons)", "license": lic})
    return out


def _archive(query, lang):
    # Prelinger = filmes institucionais/educativos/publicitários antigos, ótimos como B-roll
    # com cara de arquivo. Depois, outros acervos de domínio público.
    fields = {"fl[]": ["identifier", "title", "year", "licenseurl", "description"]}
    match = f"(title:({query}) OR subject:({query}) OR description:({query}))"
    docs, seen = [], set()
    for coll in ("collection:prelinger",
                 "(collection:publicdomainmovies OR collection:classic_tv_commercials OR licenseurl:*publicdomain*)"):
        data = _get("https://archive.org/advancedsearch.php", q=f"{match} AND mediatype:movies AND {coll}",
                    rows=16, output="json", **fields).json()
        for d in data.get("response", {}).get("docs", []):
            if d["identifier"] not in seen:
                seen.add(d["identifier"])
                docs.append(d)
    out = []
    for d in docs:
        ident = d["identifier"]
        title = d.get("title", ident)
        if isinstance(title, list):
            title = title[0]
        desc = d.get("description", "")
        if isinstance(desc, list):
            desc = desc[0]
        out.append({
            "id": f"ia-{ident}", "source": "arquivo", "kind": "video",
            "title": f"{title}" + (f" ({d['year']})" if d.get("year") else ""),
            "desc": _clean_html(desc)[:200],
            "thumb": f"https://archive.org/services/img/{ident}", "url": None, "ref": ident,
            "page_url": f"https://archive.org/details/{ident}",
            "credit": f"{title} — Internet Archive", "license": d.get("licenseurl") or "domínio público (Prelinger)"})
    return out


def _nasa(query, lang):
    data = _get("https://images-api.nasa.gov/search", q=query, media_type="image,video").json()
    out = []
    for it in data.get("collection", {}).get("items", [])[:30]:
        d = it["data"][0]
        thumb = next((l["href"] for l in it.get("links", []) if l.get("render") == "image"), None)
        kind = "video" if d.get("media_type") == "video" else "image"
        out.append({
            "id": f"nasa-{d['nasa_id']}", "source": "nasa", "kind": kind, "title": d.get("title", ""),
            "desc": (d.get("description") or "")[:200], "thumb": thumb, "url": None, "ref": d["nasa_id"],
            "page_url": f"https://images.nasa.gov/details/{urllib.parse.quote(d['nasa_id'])}",
            "credit": f"{d.get('title', '')} — NASA", "license": "domínio público (NASA)"})
    return out


def _news(query, lang):
    # RSS do Bing Notícias traz o link direto da matéria. Atenção: os termos do RSS
    # permitem uso pessoal; para uso comercial, prefira colar a URL da matéria.
    mkt = "pt-BR" if (lang or "pt") == "pt" else "en-US"
    xml = _get("https://www.bing.com/news/search", q=query, format="rss", setlang=mkt,
               cc=mkt[-2:]).text
    out = []
    for item in ET.fromstring(xml).iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        real = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [link])[0]
        host = urllib.parse.urlparse(real).netloc.removeprefix("www.")
        out.append({
            "id": f"news-{uuid.uuid5(uuid.NAMESPACE_URL, real).hex[:12]}",
            "source": "noticias", "kind": "page", "title": title,
            "desc": f"{host} · {(item.findtext('description') or '')[:160]}",
            "thumb": None, "url": real, "page_url": real,
            "credit": f"{title} — {host}", "license": "citação jornalística"})
        if len(out) >= 15:
            break
    return out


def _site(query, lang):
    url = query.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    return [{"id": f"site-{uuid.uuid5(uuid.NAMESPACE_URL, url).hex[:12]}", "source": "site",
             "kind": "page", "title": f"Print de {urllib.parse.urlparse(url).netloc}", "thumb": None,
             "url": url, "page_url": url, "credit": f"Print de {url}", "license": "citação"}]


# ---------------------------------------------------------------- resolver / baixar

def resolve_video(result):
    """URL de vídeo tocável (mp4/webm) para pré-visualizar e recortar."""
    if result.get("url"):
        return result["url"]
    if result["source"] == "nasa":
        items = _get(f"https://images-api.nasa.gov/asset/{urllib.parse.quote(result['ref'])}").json()
        hrefs = [i["href"] for i in items["collection"]["items"]]
        for pref in ("~medium.mp4", "~small.mp4", "~mobile.mp4", "~orig.mp4", ".mp4"):
            for h in hrefs:
                if h.endswith(pref):
                    return h.replace("http://", "https://")
        imgs = [h for h in hrefs if h.endswith((".jpg", ".png"))]
        if imgs:
            return imgs[0].replace("http://", "https://")
    if result["source"] == "arquivo":
        meta = _get(f"https://archive.org/metadata/{result['ref']}").json()
        files = [f for f in meta.get("files", []) if f.get("name", "").lower().endswith(".mp4")]
        if files:
            # prefere h.264 (o mais leve), depois MPEG4
            files.sort(key=lambda f: (0 if f.get("format") == "h.264" else 1 if "MPEG4" in f.get("format", "") else 2,
                                      int(f.get("size", 0) or 0)))
            return f"https://archive.org/download/{result['ref']}/{urllib.parse.quote(files[0]['name'])}"
    raise RuntimeError("Não consegui encontrar um arquivo de vídeo para esse resultado.")


def fetch(result, assets_dir, start=0.0, length=8.0, mode="card", explicit_start=False):
    """Baixa o material para a pasta de assets do projeto. Retorna {file, kind}."""
    assets_dir = Path(assets_dir)
    slug = re.sub(r"[^\w]+", "_", result.get("title", "material"))[:40].strip("_") or "material"
    base = f"{uuid.uuid4().hex[:6]}_{result['source']}_{slug}"
    kind = result["kind"]

    if kind == "page":
        out = assets_dir / f"{base}.png"
        if mode == "print":
            screenshot(result["url"], out)
        else:
            headline_card(result["url"], out, result.get("title"))
        return {"file": out.name, "kind": "image", "print": True}

    if result["source"] == "nasa" and kind == "image":
        url = resolve_video(result)  # o manifesto também lista as imagens
        if url.endswith(".mp4"):
            kind = "video"
    else:
        url = result.get("url") or resolve_video(result)

    if kind == "image":
        r = _get(url)
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(
            r.headers.get("content-type", "").split(";")[0], ".jpg")
        raw = assets_dir / f"{base}.raw{ext}"
        raw.write_bytes(r.content)
        # achata transparência sobre fundo escuro (PNG recortado viraria "fantasma" no vídeo)
        out = assets_dir / f"{base}.jpg"
        p = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(raw), "-filter_complex",
                            "color=c=0x101114:s=16x16[c];[c][0:v]scale2ref[c2][i];[c2][i]overlay=format=auto,format=yuv420p",
                            "-frames:v", "1", "-q:v", "2", str(out)], capture_output=True)
        if p.returncode != 0 or not out.exists():
            out = assets_dir / f"{base}{ext}"
            raw.replace(out)
        else:
            raw.unlink()
        return {"file": out.name, "kind": "image"}

    out = assets_dir / f"{base}.mp4"
    dur = probe(url, user_agent=UA).get("duration") or 0
    length = min(length, dur) if dur else length
    # tenta o ponto pedido; se o trecho vier escuro (fade, tela preta, cartela), tenta outros pontos
    starts = [start] + ([dur * f for f in (0.3, 0.5, 0.7, 0.15)] if dur and not explicit_start else [])
    last_err = None
    for st in starts:
        st = max(0.0, min(st, dur - length)) if dur else st
        try:
            clip_remote_video(url, out, st, length)
        except Exception as e:  # noqa: BLE001
            last_err = e
            out.unlink(missing_ok=True)
            continue
        if dark_ratio(out) < 0.2 or st == starts[-1]:
            return {"file": out.name, "kind": "video", "clip_from": round(st, 2)}
    raise last_err or RuntimeError("Não consegui recortar esse vídeo.")


def dark_ratio(path):
    """Fração do clipe que é praticamente preta."""
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.05:pix_th=0.12",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    black = sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", p.stderr))
    return black / (probe(path)["duration"] or 1)


def clip_remote_video(url, out, start, length):
    """Recorta só o trecho necessário direto da URL (sem baixar o filme inteiro)."""
    base = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-user_agent", UA,
            "-ss", f"{max(0.0, float(start)):.2f}", "-i", url, "-t", f"{float(length):.2f}", "-an",
            "-vf", "scale='min(1920,iw)':-2,fps=30,format=yuv420p"]
    for enc in (["-c:v", "h264_videotoolbox", "-b:v", "10M"], ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast"]):
        p = subprocess.run(base + enc + ["-movflags", "+faststart", str(out)], capture_output=True, text=True,
                           timeout=240)
        if p.returncode == 0 and out.exists() and probe(out)["duration"] > 0.3:
            return
    raise RuntimeError("Falha ao recortar o vídeo: " + (p.stderr or "")[-400:])


def chrome():
    for c in CHROME_PATHS:
        if Path(c).exists():
            return c
    return shutil.which("google-chrome") or shutil.which("chromium")


def _run_chrome(args, out, timeout=45):
    exe = chrome()
    if not exe:
        raise RuntimeError("Para prints e cards, instale o Google Chrome.")
    tmp = Path(out).with_suffix(".tmp.png")
    profile = Path(out).parent / ".chrome-profile"
    cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
           "--no-first-run", "--disable-extensions", f"--user-data-dir={profile}",
           "--disable-notifications", "--lang=pt-BR", f"--screenshot={tmp}", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # o Chrome às vezes demora para fechar depois de salvar: encerra assim que o arquivo estabiliza
    t0, last = time.time(), -1
    while p.poll() is None and time.time() - t0 < timeout:
        time.sleep(0.4)
        size = tmp.stat().st_size if tmp.exists() else -1
        if size > 0 and size == last:
            break
        last = size
    if p.poll() is None:
        p.kill()
        p.wait()
    if not tmp.exists():
        raise RuntimeError("Não consegui gerar a imagem dessa página.")
    tmp.replace(out)


def screenshot(url, out, width=1280, height=860):
    """Print cru de uma página usando o Chrome instalado (modo invisível)."""
    _run_chrome(["--force-device-scale-factor=2", f"--window-size={width},{height}",
                 "--timeout=12000", f"--user-agent={_browser_ua()}", url], out)


def _meta(html, *names):
    for n in names:
        m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']+)' % re.escape(n), html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']%s["\']' % re.escape(n), html, re.I)
        if m:
            import html as h
            return h.unescape(m.group(1)).strip()
    return ""


def headline_card(url, out, fallback_title=""):
    """Card de manchete limpo (logo do site, título, data e foto), sem banners de cookies."""
    import html as h
    try:
        r = httpx.get(url, headers={"User-Agent": _browser_ua(), "Accept-Language": "pt-BR,pt;q=0.9"},
                      timeout=TIMEOUT, follow_redirects=True)
        page = r.text[:600000]
        final = str(r.url)
    except Exception:
        page, final = "", url
    title = _meta(page, "og:title", "twitter:title") or fallback_title or url
    site = _meta(page, "og:site_name") or urllib.parse.urlparse(final).netloc.removeprefix("www.")
    image = _meta(page, "og:image", "twitter:image", "twitter:image:src")
    date = _meta(page, "article:published_time", "og:updated_time", "date")
    desc = _meta(page, "og:description", "description")
    host = urllib.parse.urlparse(final).netloc
    if image.startswith("//"):
        image = "https:" + image
    elif image.startswith("/"):
        image = f"https://{host}{image}"
    date_txt = ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date)
    if m:
        date_txt = f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    card = CARD_HTML.format(
        site=h.escape(site), title=h.escape(title), desc=h.escape(desc[:220]),
        date=h.escape(date_txt), favicon=f"https://www.google.com/s2/favicons?domain={host}&sz=128",
        image=(f'<div class="img" style="background-image:url(\'{h.escape(image)}\')"></div>' if image else ""))
    html_file = Path(out).with_suffix(".card.html")
    html_file.write_text(card, encoding="utf-8")
    try:
        _run_chrome(["--force-device-scale-factor=2", "--window-size=1080,940", "--timeout=5000",
                     html_file.as_uri()], out, timeout=30)
    finally:
        html_file.unlink(missing_ok=True)


CARD_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;background:transparent}}
.card{{position:absolute;inset:0;background:#fff;overflow:hidden;
  font-family:Georgia,'Times New Roman',serif;display:flex;flex-direction:column}}
.top{{display:flex;align-items:center;gap:14px;padding:30px 40px 0;font:600 24px -apple-system,Helvetica,sans-serif;color:#333}}
.top img{{width:40px;height:40px;border-radius:8px}}
.top .d{{margin-left:auto;color:#888;font-weight:500;font-size:20px}}
h1{{font-size:50px;line-height:1.12;margin:22px 40px 12px;color:#111;letter-spacing:-.01em}}
p{{font:400 23px/1.4 -apple-system,Helvetica,sans-serif;color:#555;margin:0 40px 26px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.img{{flex:1;min-height:200px;background:#ddd center/cover}}
</style></head><body><div class="card">
<div class="top"><img src="{favicon}"><span>{site}</span><span class="d">{date}</span></div>
<h1>{title}</h1><p>{desc}</p>{image}</div></body></html>"""


def _browser_ua():
    return ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

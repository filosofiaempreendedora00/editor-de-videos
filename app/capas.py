"""CAPAS dos vídeos (03/11, pedido dele): para cada card, 3 opções de capa no formato do vídeo (9:16), cada uma com um
quadro em que o rosto dele saiu melhor + a HEADLINE (o gancho do vídeo), para usar no Instagram, Shorts e TikTok.

Princípio da referência (@fernandomiranda777): capa DIVIDIDA — em cima uma imagem do ASSUNTO da história, embaixo ele
falando, e uma pergunta/gancho na emenda que dá curiosidade. O que ele NÃO quer copiar: letra pequena e sem estética.
Aqui: tipografia grande (Anton) em creme sobre ônix, palavra-chave em dourado (paleta Kronos), assinatura discreta.

- Quadros: a gravação CRUA do projeto (sem legenda queimada), só nos trechos que ficaram no corte; o Apple Vision dá
  a "qualidade de captura do rosto" de cada quadro (olhos abertos, foco, pose — o mesmo critério da melhor foto de uma
  rajada no iPhone); ficam os 3 melhores, separados por ≥ 4 s.
- Imagem do assunto: o 1º ativo visual do gancho (overlay media dos primeiros 15 s). Sem ativo → modelo "retrato".
- Tudo que importa (rosto, headline) fica dentro do recorte 3:4 do grid do Instagram/TikTok (y 240–1680 de 1920).
- `*palavra*` na headline = dourado; sem marcação, escolhe a palavra-chave do destaque do vídeo (ou a mais longa).
Arquivos em roteiros/capas/<código>/; o estado fica no card (`r["capa"]`).
"""
import html
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import roteiros, timeline
from .media import FFMPEG, probe
from .store import PROJECTS, load as load_project

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "roteiros" / "capas"
FONTS = ROOT / "fonts"
W, H = 1080, 1920
SEGURO = (240, 1680)              # faixa que o grid 3:4 mostra (o resto só aparece no Reels/Shorts aberto)
MODELOS = ("dividida", "retrato")
OLHO_ABERTO = 0.28                # abertura do olho (altura/largura): semicerrado 0,26 × aberto 0,31 (calibrado no V018)
PARADAS = {"para", "pela", "pelo", "como", "mais", "muito", "porque", "quando", "sobre", "você", "voce", "esse", "essa",
           "isso", "aquilo", "nosso", "nossa", "dessa", "desse", "também", "ainda", "então", "sempre", "nunca", "todos"}


def pasta(code):
    d = DIR / code
    d.mkdir(parents=True, exist_ok=True)
    return d


def _card(code):
    r = next((x for x in roteiros.load() if x["code"] == code), None)
    if not r:
        raise KeyError(code)
    return r


def projeto(code):
    """O projeto da gravação do card: o que gerou o final entregue (`entregue.origem`), senão o mais novo com o código."""
    r = _card(code)
    orig = (r.get("entregue") or {}).get("origem")
    if orig and (PROJECTS / Path(orig).parent.parent.name / "project.json").exists():
        return Path(orig).parent.parent.name
    cands = []
    for f in PROJECTS.glob("*/project.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if p.get("roteiro") == code and not any(w in (p.get("name") or "").lower() for w in ("ensaio", "montador")):
            cands.append((f.stat().st_mtime, f.parent.name))
    if r.get("project"):
        cands.append((0, r["project"]))
    if not cands:
        raise RuntimeError(f"{code}: não achei o projeto da gravação.")
    return max(cands)[1]


# ---------------------------------------------------------------- quadros com o melhor rosto
def _rosto(jpg):
    """Maior rosto do quadro + a qualidade de captura (0..1) do Apple Vision. Caixa normalizada, y de cima para baixo."""
    import objc
    import Vision
    from Foundation import NSURL
    with objc.autorelease_pool():
        h = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(jpg)), None)
        req = Vision.VNDetectFaceCaptureQualityRequest.alloc().init()
        marcos = Vision.VNDetectFaceLandmarksRequest.alloc().init()
        ok, _ = h.performRequests_error_([req, marcos], None)
        res = list(req.results() or []) if ok else []
        if not res:
            return None
        o = max(res, key=lambda r: r.boundingBox().size.height)
        bb = o.boundingBox()
        q = o.faceCaptureQuality()
        # boca: abertura dos lábios internos (altura/largura). Quadro no meio de uma sílaba ("boca aberta") fica feio
        boca, largura = 0.0, 0.0
        lm = next((m for m in (marcos.results() or []) if abs(m.boundingBox().origin.x - bb.origin.x) < 0.05), None)
        if lm is not None and lm.landmarks() is not None and lm.landmarks().innerLips() is not None:
            reg = lm.landmarks().innerLips()
            pts = [reg.normalizedPoints()[i] for i in range(reg.pointCount())]
            xs, ys = [p.x for p in pts], [p.y for p in pts]
            boca = (max(ys) - min(ys)) / max(1e-3, max(xs) - min(xs))
            ext = lm.landmarks().outerLips()
            if ext is not None:                         # largura da boca na largura do rosto: o sorriso alarga a boca
                xo = [ext.normalizedPoints()[i].x for i in range(ext.pointCount())]
                largura = max(xo) - min(xo)
        olhos = 1.0                                     # abertura do olho mais fechado (altura/largura): semicerrado < 0,22
        if lm is not None and lm.landmarks() is not None:
            ab = []
            for reg in (lm.landmarks().leftEye(), lm.landmarks().rightEye()):
                if reg is not None and reg.pointCount():
                    pts = [reg.normalizedPoints()[i] for i in range(reg.pointCount())]
                    xs, ys = [p.x for p in pts], [p.y for p in pts]
                    ab.append((max(ys) - min(ys)) / max(1e-3, max(xs) - min(xs)))
            olhos = min(ab) if ab else 1.0
        return {"q": float(q) if q is not None else 0.0, "x": float(bb.origin.x), "w": float(bb.size.width),
                "y": float(1 - bb.origin.y - bb.size.height), "h": float(bb.size.height), "boca": round(float(boca), 3),
                "sorriso": round(float(largura), 3), "olhos": round(float(olhos), 3)}


def _nota(r):
    """Calibrado no V018 (03/11): sorriso = boca mais LARGA (0,365 × 0,30 neutro/franzido); boca escancarada no meio da
    palavra = abertura > 0,5; olho semicerrado < 0,28. Rosto maior ganha um pouco."""
    return r["q"] + 0.15 * min(1.0, r["h"] / 0.22) + 1.2 * (r["sorriso"] - 0.32) - 0.5 * max(0.0, r["boca"] - 0.5) \
        - 2.0 * max(0.0, OLHO_ABERTO - r["olhos"])


def melhores_quadros(code, n=3, progresso=None):
    pid = projeto(code)
    p = load_project(pid)
    src = PROJECTS / pid / p["source"]["file"] if isinstance(p.get("source"), dict) and p["source"].get("file") else \
        next((PROJECTS / pid).glob("source.*"))
    trechos = [(c["start"], c["end"]) for c in timeline.compute(p)["cuts"]]
    passo = 0.5
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([FFMPEG, "-v", "error", "-i", str(src), "-vf", f"fps={1 / passo},scale=360:-2", "-q:v", "3",
                        f"{tmp}/f_%05d.jpg"], check=True, timeout=600)
        fotos = sorted(Path(tmp).glob("f_*.jpg"))
        cands = []
        for i, f in enumerate(fotos):
            t = i * passo
            if not any(a + 0.4 <= t <= b - 0.4 for a, b in trechos):     # só o que ficou no corte, longe da emenda
                continue
            r = _rosto(f)
            if progresso and i % 20 == 0:
                progresso(0.1 + 0.6 * i / max(1, len(fotos)), f"procurando o melhor rosto ({i}/{len(fotos)})")
            if not r or r["h"] < 0.09 or not 0.2 < r["x"] + r["w"] / 2 < 0.8:
                continue
            cands.append({"t": round(t, 2), "nota": round(_nota(r), 4), "rosto": r})
    escolhidos = []
    for c in sorted(cands, key=lambda c: -c["nota"]):
        if all(abs(c["t"] - e["t"]) >= 4 for e in escolhidos):
            escolhidos.append(c)
        if len(escolhidos) == n:
            break
    d = pasta(code)
    for k, c in enumerate(escolhidos):
        # o quadro amostrado (fps=2) e o extraído podem diferir em 1 quadro — o bastante para pegar uma piscada:
        # pontua o quadro EXATO de cada vizinho (±0,2 s) e fica com o melhor
        dst = d / f"quadro_{k}.jpg"
        melhor = None
        for dt in (0.0, -0.07, 0.07, -0.13, 0.13, -0.2, 0.2):
            t = max(0.0, c["t"] + dt)
            tmp = d / f".viz_{k}.jpg"
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                            "-q:v", "2", str(tmp)], check=True, timeout=120)
            r = _rosto(tmp)
            if not r:
                continue
            nota = _nota(r)
            if not melhor or nota > melhor[0]:
                melhor = (nota, t, r)
                tmp.replace(dst)
        (d / f".viz_{k}.jpg").unlink(missing_ok=True)
        if melhor:
            c.update(nota=round(melhor[0], 4), t=round(melhor[1], 3), rosto=melhor[2])
        c["arquivo"] = dst.name
        info = probe(dst)
        c["wh"] = [info["width"], info["height"]]
    return pid, escolhidos


# ---------------------------------------------------------------- imagem do assunto (1º ativo do gancho)
def contexto(code, pid=None):
    pid = pid or projeto(code)
    p = load_project(pid)
    ovs = sorted([o for o in timeline.compute(p)["overlays"] if o["type"] == "media" and o.get("file") and o["a"] < 15],
                 key=lambda o: o["a"])
    for o in ovs:
        f = PROJECTS / pid / "assets" / o["file"]
        if not f.exists():
            continue
        dst = pasta(code) / "contexto.jpg"
        if f.suffix.lower() in (".mp4", ".mov", ".m4v", ".webm"):
            t = float(o.get("clip_start") or 0) + min(1.5, max(0.2, (o["b"] - o["a"]) / 2))
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(f), "-frames:v", "1", "-q:v", "2",
                            str(dst)], timeout=120)
        else:
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(f), "-frames:v", "1", "-q:v", "2", str(dst)], timeout=120)
        if dst.exists():
            return {"arquivo": dst.name, "fonte": o["file"]}
    return None


# ---------------------------------------------------------------- headline
def headline_padrao(code):
    hook = re.sub(r"\s+", " ", re.sub(r"\*\*", "", _card(code).get("hook") or "")).strip()
    if len(hook) > 80:                                     # capa: a 1ª frase do gancho (mantém o "…" da curiosidade)
        m = re.search(r"^(.{25,80}?(?:…|\.\.\.|[.!?]))(\s|$)", hook)
        hook = m.group(1) if m else hook[:80].rsplit(" ", 1)[0] + "…"
    return hook


def _palavra_chave(code, pid, texto):
    if "*" in texto:
        return texto
    chaves = []
    try:
        chaves = [str(o.get("key") or "") for o in load_project(pid).get("overlays", []) if o.get("type") == "emphasis"]
    except (OSError, KeyError, ValueError):
        pass
    palavras = re.findall(r"[\wÀ-ÿ]+", texto)
    alvo = next((p for k in chaves for p in palavras if k and p.lower() == k.lower().strip()), None)
    if not alvo:
        longas = [p for p in palavras if len(p) >= 6 and p.lower() not in PARADAS and not p.isdigit()]
        alvo = max(longas, key=len) if longas else None
    return re.sub(rf"\b({re.escape(alvo)})\b", r"*\1*", texto, count=1) if alvo else texto


def _hl_html(texto):
    partes = re.split(r"(\*[^*]+\*)", texto)
    return "".join(f'<b>{html.escape(p[1:-1])}</b>' if p.startswith("*") and p.endswith("*") else html.escape(p)
                   for p in partes)


# ---------------------------------------------------------------- desenho (HTML → Chrome → JPG)
def _pos(rosto, wh, alvo_h, topo_alvo=None, centro_alvo=None, area=(0, H)):
    """Onde pôr o quadro (zoom e deslocamento) para o rosto ficar do tamanho e na altura certos, cobrindo a área."""
    sw, sh = wh
    esc = W / sw                                            # quadro → largura da capa
    face_h = rosto["h"] * sh * esc
    z = max(1.0, min(1.75, alvo_h / max(1, face_h)))
    iw, ih = W * z, sh * esc * z
    cx = (rosto["x"] + rosto["w"] / 2) * iw
    left = min(0, max(W - iw, W / 2 - cx))
    ftop = rosto["y"] * ih
    top = (topo_alvo - ftop) if topo_alvo is not None else (centro_alvo - (ftop + rosto["h"] * ih / 2))
    a0, a1 = area
    top = min(a0, max(a1 - ih, top))
    queixo = top + (rosto["y"] + rosto["h"]) * ih
    return {"left": round(left), "top": round(top), "w": round(iw), "h": round(ih), "queixo": round(queixo)}


CSS = """
@font-face { font-family: Anton; src: url('%(fonts)s/Anton-Regular.ttf'); }
@font-face { font-family: Mont; src: url('%(fonts)s/MontserratAlternates-SemiBold.ttf'); }
* { margin: 0; box-sizing: border-box; }
html, body { width: 1080px; height: 1920px; overflow: hidden; background: #150C06; }
.cv { position: relative; width: 1080px; height: 1920px; overflow: hidden; background: #150C06; }
.img { position: absolute; display: block; filter: saturate(.94) contrast(1.05) sepia(.07); }
.topo { position: absolute; left: 0; right: 0; top: 0; overflow: hidden; }
.topo .ctx { position: absolute; inset: 0; width: 100%%; height: 100%%; object-fit: cover; object-position: 50%% 38%%;
  filter: saturate(.86) contrast(1.06) brightness(.8) sepia(.16); }
.topo::after { content: ''; position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(21,12,6,.10) 0%%, rgba(21,12,6,0) 40%%, rgba(21,12,6,.55) 100%%); }
.base { position: absolute; left: 0; right: 0; bottom: 0; overflow: hidden; }
.sombra { position: absolute; inset: 0; pointer-events: none; }
.hl { position: absolute; left: 50%%; transform: translateX(-50%%); width: 960px; text-align: center;
  font-family: Anton, Impact, sans-serif; text-transform: uppercase; color: #F5EFE6; letter-spacing: .012em;
  line-height: 1.04; }
.hl b { color: #E0BB6A; font-weight: normal; }
.painel { position: absolute; left: 50%%; transform: translateX(-50%%); width: 980px; border-radius: 30px;
  background: rgba(21,12,6,.93); box-shadow: 0 24px 70px rgba(0,0,0,.5), inset 0 0 0 1.5px rgba(224,187,106,.22);
  padding: 34px 40px 38px; }
.painel .hl { position: static; transform: none; width: 100%%; }
.fio { width: 76px; height: 3px; background: #E0BB6A; border-radius: 2px; margin: 0 auto 22px; }
.assin { position: absolute; left: 0; right: 0; text-align: center; font-family: Mont, sans-serif; font-size: 25px;
  letter-spacing: .34em; color: rgba(245,239,230,.88); text-transform: uppercase; text-shadow: 0 2px 14px rgba(0,0,0,.7); }
.assin i { display: inline-block; width: 7px; height: 7px; border-radius: 50%%; background: #E0BB6A; margin: 0 16px 5px; }
"""

FIT = """
<script>
document.fonts.ready.then(() => {
  const h = document.querySelector('.hl'); const max = %(maxh)d; let s = %(s0)d;
  const ok = () => h.scrollWidth <= h.clientWidth + 1 && h.offsetHeight <= max;
  h.style.fontSize = s + 'px';
  while (!ok() && s > %(smin)d) { s -= 2; h.style.fontSize = s + 'px'; }
  const pn = document.querySelector('.painel');
  if (pn && pn.dataset.centro) pn.style.top = (+pn.dataset.centro - pn.offsetHeight / 2) + 'px';
  document.body.dataset.pronto = '1';
});
</script>"""


def _html(modelo, quadro, rosto, wh, headline, ctx=None, assinatura="Roberto Fachetti"):
    fonts = FONTS.as_uri()
    css = CSS % {"fonts": fonts}
    hl = _hl_html(headline)
    assin = f'<div class="assin" style="top:{SEGURO[1] - 64}px">{html.escape(assinatura)}</div>' if assinatura else ""
    if modelo == "dividida" and ctx:
        emenda = 830
        p = _pos(rosto, wh, alvo_h=400, topo_alvo=emenda + 250, area=(emenda, H))   # folga p/ o cabelo abaixo do painel
        corpo = f"""
<div class="topo" style="height:{emenda}px"><img class="ctx" src="{ctx}"></div>
<div class="base" style="top:{emenda}px"><img class="img" src="{quadro}" style="left:{p['left']}px;top:{p['top'] - emenda}px;
  width:{p['w']}px;height:{p['h']}px"></div>
<div class="sombra" style="background:linear-gradient(180deg, rgba(21,12,6,0) 72%, rgba(21,12,6,.62) 100%)"></div>
<div class="painel" data-centro="{emenda}"><div class="hl">{hl}</div></div>{assin}"""
        fit = FIT % {"maxh": 330, "s0": 104, "smin": 56}
    else:
        p = _pos(rosto, wh, alvo_h=440, centro_alvo=720)
        topo_txt = max(p["queixo"] + 70, 1090)
        corpo = f"""
<img class="img" src="{quadro}" style="left:{p['left']}px;top:{p['top']}px;width:{p['w']}px;height:{p['h']}px">
<div class="sombra" style="background:linear-gradient(180deg, rgba(21,12,6,0) {max(40, (topo_txt - 260) * 100 // H)}%,
  rgba(21,12,6,.72) {min(80, (topo_txt + 60) * 100 // H)}%, rgba(21,12,6,.94) 100%)"></div>
<div class="hl" style="top:{topo_txt + 25}px"><div class="fio"></div>{hl}</div>{assin}"""
        fit = FIT % {"maxh": SEGURO[1] - 150 - topo_txt, "s0": 128, "smin": 60}     # folga para a assinatura
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body><div class='cv'>{corpo}</div>" \
           f"{fit}</body></html>"


def desenhar(code, modelo, k, headline):
    from .sources import _run_chrome
    r = _card(code)
    c = r.get("capa") or {}
    q = c["quadros"][k]
    d = pasta(code)
    ctx = (d / c["contexto"]["arquivo"]).as_uri() if c.get("contexto") else None
    pagina = d / f".capa_{k}.html"
    pagina.write_text(_html(modelo if ctx else "retrato", (d / q["arquivo"]).as_uri(), q["rosto"], q["wh"], headline, ctx),
                      encoding="utf-8")
    png = d / f".capa_{k}.png"
    _run_chrome(["--force-device-scale-factor=1", f"--window-size={W},{H}", "--virtual-time-budget=5000",
                 "--allow-file-access-from-files", pagina.as_uri()], png)
    jpg = d / f"capa_{k}.jpg"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(png), "-q:v", "2", str(jpg)], check=True, timeout=60)
    png.unlink(missing_ok=True)
    return jpg.name


# ---------------------------------------------------------------- o fluxo
def gerar(code, headline=None, modelo=None, refazer_quadros=False, progresso=None):
    """Gera (ou refaz) as 3 opções. Quadros e imagem do assunto ficam em cache; mudar headline/modelo só redesenha."""
    r = _card(code)
    c = dict(r.get("capa") or {})
    if refazer_quadros or not c.get("quadros"):
        progresso and progresso(0.05, "lendo a gravação")
        pid, quadros = melhores_quadros(code, progresso=progresso)
        if not quadros:
            raise RuntimeError(f"{code}: não achei quadros com o rosto bem visível.")
        c.update(projeto=pid, quadros=quadros, contexto=contexto(code, pid))
    pid = c.get("projeto") or projeto(code)
    texto = (headline if headline is not None else c.get("headline")) or headline_padrao(code)
    texto = _palavra_chave(code, pid, texto.strip())
    modelo = modelo if modelo in MODELOS else (c.get("modelo") or ("dividida" if c.get("contexto") else "retrato"))
    c.update(headline=texto, modelo=modelo)
    roteiros.edit(code, {"capa": c})
    capas = []
    for k in range(len(c["quadros"])):
        progresso and progresso(0.72 + 0.26 * k / len(c["quadros"]), f"desenhando a opção {k + 1}")
        capas.append(desenhar(code, modelo, k, texto))
    c.update(capas=capas, gerado=time.strftime("%Y-%m-%dT%H:%M:%S"), versao=int(time.time()))
    if c.get("escolhida") is not None and c["escolhida"] >= len(capas):
        c["escolhida"] = None
    roteiros.edit(code, {"capa": c})
    return c


def escolher(code, k):
    r = _card(code)
    c = dict(r.get("capa") or {})
    if not c.get("capas") or not 0 <= int(k) < len(c["capas"]):
        raise ValueError("Opção inválida.")
    c["escolhida"] = int(k)
    shutil.copyfile(pasta(code) / c["capas"][int(k)], pasta(code) / "capa.jpg")
    roteiros.edit(code, {"capa": c})
    from . import agenda                                  # Shorts já agendados no YouTube: o relógio manda a capa nova
    for p in agenda.load():
        e = (p.get("redes") or {}).get("yt") or {}
        if p.get("code") == code and e.get("id_rede") and e.get("status") == "na_rede":
            agenda._set_rede(p["id"], "yt", capa_pendente=True, capa_tentou="", _log="capa nova escolhida: vai para o YouTube")
    return c


def escolhida(code):
    """Caminho da capa escolhida (para o YouTube usar como miniatura), ou None."""
    try:
        c = _card(code).get("capa") or {}
    except KeyError:
        return None
    f = DIR / code / "capa.jpg"
    return str(f) if c.get("escolhida") is not None and f.exists() else None


def lista():
    out = []
    for r in roteiros.load():
        if r.get("archived") or r["status"] not in ("gravado", "editado", "publicado", "destaque"):
            continue
        c = r.get("capa") or {}
        out.append({"code": r["code"], "title": r.get("title") or "", "status": r["status"], "hook": r.get("hook") or "",
                    "capa": c, "headline_padrao": headline_padrao(r["code"])})
    return sorted(out, key=lambda x: roteiros._num(x["code"]), reverse=True)

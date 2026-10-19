"""Roteiro aprovado → vídeo quase pronto, sem a gravação dele (ensaio) — e o MESMO plano aplicado depois na gravação real.

Fluxo:
  1. `montar-roteiro V010`  → voz clonada do Roberto (voz/<code>/*.wav, tools/voz_tts.py) + apresentador provisório
     (stand-in, vídeo de banco) → MP4 de ensaio → projeto no editor (mesmo pipeline de uma gravação: transcrição,
     cortes, legendas, destaques, sons do hook) → `aplicar-edicao`.
  2. `aplicar-edicao <projeto> V010` → lê `roteiros/edicao/V010.json` (o plano de edição do roteiro, ancorado em
     FRASES do texto, não em tempo) e cria as inserções no projeto: B-rolls, tvzinha, prints, motions, destaques,
     música. Funciona igual no ensaio e na gravação real (as frases são achadas na fala com tolerância).

Plano (`roteiros/edicao/<code>.json`, ativos em `roteiros/edicao/<code>/`):
  {"musica": {"file": "lib:<slug>", "vol": 0.12},
   "config": {...},                       # opcional
   "overlays": [{"type": "media", "layout": "viral", "file": "x.mp4", "em": "trecho do roteiro", "ate": "outro",
                 "click": true, ...demais campos do overlay}, ...]}
  `em` = onde começa (1ª palavra do trecho), `ate` = onde termina (última palavra; padrão = fim do `em`).
  Em motions, `params.items[].em` vira `w`. Todo media/motion ganha um CLIQUE ao brotar (regra dele), salvo click=false.
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

from . import roteiros
from .media import FFMPEG, probe
from .store import PROJECTS, load, update

ROOT = Path(__file__).resolve().parent.parent
VOZ = ROOT / "voz"
EDICAO = roteiros.DIR / "edicao"
# AVATAR PROVISÓRIO = o próprio Roberto (gravação do V001, sem som): fica claro o que é ELE e o que é B-roll, e os
# zooms/cortes de ritmo agem nele como no vídeo real (pedido dele). Antes era um rapaz de banco (Mixkit 41272).
STAND_IN = ROOT / "projects" / "5cdb9b27b3" / "source.mov"
STAND_IN_WIN = (0.5, 97.5)


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-800:])
    return r


# ---------------------------------------------------------------- 1. voz
def falas(code):
    """Divide o roteiro (sem marcas de negrito) em falas de até ~230 caracteres, por parágrafo."""
    import re
    r = next(x for x in roteiros.load() if x["code"] == code)
    out = []
    for k in ("hook", "body", "cta"):
        for p in re.split(r"\n\s*\n", roteiros.plain(r.get(k, "")).strip()):
            p = " ".join(p.split())
            if not p:
                continue
            cur = ""
            for s in re.split(r"(?<=[.!?…])\s+", p):
                if cur and len(cur) + len(s) > 230:
                    out.append({"text": cur, "par_end": False})
                    cur = s
                else:
                    cur = (cur + " " + s).strip()
            if cur:
                out.append({"text": cur, "par_end": True})
    return out


def voz_rapida(code):
    """PADRÃO (pedido dele: produtividade): voz de IA pronta (edge-tts, grátis, segundos) só para dar o TEMPO e o
    ritmo da fala — a prévia é descartada quando chega a gravação dele. A voz clonada (gerar_voz) fica opcional."""
    import asyncio
    import edge_tts
    d = VOZ / f"{code}_rapida"
    d.mkdir(parents=True, exist_ok=True)
    texto = "\n\n".join(f["text"] for f in falas(code))
    mp3, out = d / "narracao.mp3", d / "narracao.wav"
    asyncio.run(edge_tts.Communicate(texto, "pt-BR-AntonioNeural", rate="+8%").save(str(mp3)))
    _run([FFMPEG, "-v", "error", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(out)])
    return out


def gerar_voz(code, ref=None):
    """Voz CLONADA dele (Chatterbox, ~8× o tempo real no processador): só quando ele pedir. Cache por texto."""
    import hashlib
    d = VOZ / code
    d.mkdir(parents=True, exist_ok=True)
    meta, jobs = [], []
    for i, f in enumerate(falas(code)):
        h = hashlib.md5(f["text"].encode()).hexdigest()[:8]
        name = f"{i:03d}_{h}.wav"
        meta.append({"i": i, **f, "file": name})
        if not (d / name).exists():
            jobs.append({"text": f["text"], "out": str(d / name)})
    (d / "falas.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    if jobs:
        jf = d / "jobs.json"
        jf.write_text(json.dumps(jobs, ensure_ascii=False))
        _run([str(ROOT / ".venv-voz/bin/python"), str(ROOT / "tools/voz_tts.py"), str(ref or VOZ / "ref_roberto.wav"),
              "x", "@" + str(jf)])
    # narração: cada fala sem silêncio nas pontas + pausa curta entre frases e maior entre parágrafos
    parts = []
    for m in meta:
        t = d / f"t_{m['file']}"
        _run([FFMPEG, "-v", "error", "-y", "-i", str(d / m["file"]), "-af",
              "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
              "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,"
              f"apad=pad_dur={0.42 if m['par_end'] else 0.2}", "-ar", "48000", "-ac", "1", str(t)])
        parts.append(t)
    lst = d / "lista.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    out = d / "narracao.wav"
    _run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-af",
          "loudnorm=I=-16:TP=-1.5:LRA=9", "-ar", "48000", "-ac", "1", str(out)])
    for p in parts:
        p.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------- 2. ensaio (voz + apresentador provisório)
def ensaio(code, stand_in=None, voz="rapida"):
    d = VOZ / code
    d.mkdir(parents=True, exist_ok=True)
    narr = gerar_voz(code) if voz == "clonada" or (VOZ / code / "falas.json").exists() else voz_rapida(code)
    dur = probe(narr)["duration"]
    src = Path(stand_in or STAND_IN)
    a, b = STAND_IN_WIN if src == STAND_IN else (0, probe(src)["duration"])
    pp = VOZ / "stand_in" / f"{src.parent.name}_{src.stem}_{a:g}-{b:g}.mp4"
    if not pp.exists():
        crop = "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos,fps=30"
        # trecho curto: vai-e-volta (o loop não "pula"); longo: repete direto (reverse guardaria tudo na memória)
        fc = f"[0:v]{crop},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1" if b - a <= 20 else f"[0:v]{crop}"
        _run([FFMPEG, "-v", "error", "-y", "-ss", f"{a}", "-t", f"{b - a}", "-i", str(src), "-filter_complex", fc,
              "-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", str(pp)])
    out = d / f"{code}_ensaio.mp4"
    _run([FFMPEG, "-v", "error", "-y", "-stream_loop", "-1", "-i", str(pp), "-i", str(narr), "-map", "0:v", "-map", "1:a",
          "-t", f"{dur + 0.3:.2f}", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)])
    return out


def criar_projeto(mp4, nome):
    """Sobe o ensaio pelo mesmo caminho de uma gravação (servidor local) e espera ficar pronto."""
    import httpx
    with open(mp4, "rb") as fh:
        r = httpx.post("http://127.0.0.1:8765/api/projects", files={"file": (Path(mp4).name, fh, "video/mp4")},
                       data={"language": "pt", "engine": "regras"}, timeout=600)
    r.raise_for_status()
    pid = r.json()["project"]["id"]
    for _ in range(600):
        p = load(pid)
        if p.get("status") == "ready":
            break
        if p.get("status") == "error":
            raise RuntimeError(f"projeto {pid} deu erro no processamento")
        time.sleep(2)
    update(pid, lambda pp: pp.__setitem__("name", nome))
    return pid



def corrigir_pelo_roteiro(pid, code):
    """O texto do roteiro é a verdade: palavras transcritas parecidas com as do roteiro (mesma posição no alinhamento)
    viram a grafia do roteiro ("Hitz-Carlton" → "Ritz-Carlton"). Só troca 1↔1 e com semelhança mínima — o que ele
    improvisou na gravação fica como foi falado."""
    import re
    from difflib import SequenceMatcher
    r = next(x for x in roteiros.load() if x["code"] == code)
    script = re.findall(r"\S+", " ".join(roteiros.plain(r.get(k, "")) for k in ("hook", "body", "cta")))
    st = [(roteiros._toks(w) or [""])[0] for w in script]
    p = load(pid)
    wt = [(roteiros._toks(w["w"]) or [""])[0] for w in p["words"]]
    fixes = {}
    for op, a0, a1, b0, b1 in SequenceMatcher(None, wt, st, autojunk=False).get_opcodes():
        if op == "replace" and a1 - a0 == b1 - b0:
            for i, j in zip(range(a0, a1), range(b0, b1)):
                # palavra curta só troca se for a mesma ("no" → "o" mudava o que ele falou); correção à mão (`texto`)
                # nunca é desfeita
                if min(len(wt[i]), len(st[j])) <= 2 or p["words"][i].get("manual_txt"):
                    continue
                if SequenceMatcher(None, wt[i], st[j]).ratio() >= 0.6:
                    fixes[i] = script[j]
        elif op == "replace" and a1 - a0 == 1 and 2 <= b1 - b0 <= 3 and not p["words"][a0].get("manual_txt"):
            # uma palavra transcrita = duas/três do roteiro ("liquidate" → "Liquid Death")
            if SequenceMatcher(None, wt[a0], "".join(st[b0:b1])).ratio() >= 0.7:
                fixes[a0] = " ".join(script[b0:b1])
    if fixes:
        def f(pp):
            for i, w in fixes.items():
                pp["words"][i]["w"] = w
        update(pid, f)
    return {i: w for i, w in fixes.items()}


# ---------------------------------------------------------------- 3. plano do roteiro → inserções
def _find(words, phrase, after=0):
    hit = roteiros.match_highlights(words[after:], [phrase])[0] if after else roteiros.match_highlights(words, [phrase])[0]
    if hit[1] is None:
        return None
    return hit[1] + after, hit[2] + after


def kind_of_video(name):
    return Path(name).suffix.lower() in (".mp4", ".mov", ".m4v", ".webm")


def head_top(src, t):
    """Onde começa o alto da sua cabeça (0..1 da altura) no quadro original, no instante t — recorte do Vision."""
    import numpy as np
    from . import estalo
    info = probe(src)
    w = 540
    h = int(round(info["height"] * w / info["width"] / 2) * 2)
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(src), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(r.stdout) < w * h * 3:
        return None
    m = estalo.raw_mask(np.frombuffer(r.stdout[:w * h * 3], np.uint8).reshape(h, w, 3).copy())
    rows = np.where((m > 0.5).mean(1) > 0.03)[0]
    return round(float(rows[0]) / h, 4) if len(rows) else None


def face_bottom(src, t):
    """Onde termina o rosto (queixo, 0..1 da altura) no quadro original no instante t — detector de rosto do Vision
    (local). None se não achar rosto."""
    import numpy as np
    import Vision
    from . import estalo
    info = probe(src)
    w = 540
    h = int(round(info["height"] * w / info["width"] / 2) * 2)
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(src), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(r.stdout) < w * h * 3:
        return None
    rgb = np.frombuffer(r.stdout[:w * h * 3], np.uint8).reshape(h, w, 3).copy()
    req = Vision.VNDetectFaceRectanglesRequest.alloc().init()
    hd = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(estalo._cg(rgb), None)
    ok, _ = hd.performRequests_error_([req], None)
    faces = list(req.results() or []) if ok else []
    if not faces:
        return None
    f = max(faces, key=lambda x: x.boundingBox().size.width * x.boundingBox().size.height)
    bb = f.boundingBox()                       # normalizado, origem embaixo à esquerda
    return round(1.0 - float(bb.origin.y), 4)


def cortes_do_roteiro(pid, code, minimo=3):
    """O corte automático às vezes toma uma frase do ROTEIRO por regravação (no Jung: "Nos dias de música francesa…
    vendeu CINCO vezes mais" sumiu porque a frase seguinte começa igual). Trechos cortados de ≥ `minimo` palavras que
    estão no texto do roteiro: no ENSAIO (voz de IA, não existe regravação) voltam sozinhos; na gravação real, avisa."""
    from difflib import SequenceMatcher
    r = next((x for x in roteiros.load() if x["code"] == code), None)
    p = load(pid)
    if not r:
        return []
    script = roteiros._toks(" ".join(roteiros.plain(r.get(k) or "") for k in ("hook", "body", "cta")))
    sj = " ".join(script)
    words, dl = p["words"], set(p.get("deleted", []))
    runs, s0 = [], None
    for i in range(len(words) + 1):
        if i < len(words) and i in dl:
            s0 = i if s0 is None else s0
        elif s0 is not None:
            runs.append((s0, i - 1)); s0 = None
    ensaio = "ensaio" in (p.get("name") or "").lower()
    out, back = [], []
    for a, b in runs:
        toks = [t for w in words[a:b + 1] for t in roteiros._toks(w["w"])]
        if len(toks) < minimo:
            continue
        frag = " ".join(toks)
        m = SequenceMatcher(None, sj, frag, autojunk=False).find_longest_match(0, len(sj), 0, len(frag))
        if m.size >= 0.85 * len(frag):
            if ensaio:
                back.append((a, b))
            out.append(("↺ restaurado" if ensaio else "⚠ cortado mas está no roteiro (confira se não é regravação)")
                       + f": [{a}-{b}] {' '.join(w['w'] for w in words[a:b + 1])!r}")
    if back:
        def f(pp):
            keep = set(pp.get("deleted", []))
            for a, b in back:
                keep -= set(range(a, b + 1))
            pp["deleted"] = sorted(keep)
        update(pid, f)
    return out


def _sem_acento(t):
    import re
    import unicodedata
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def fim_do_plano(path, start, janela=14.0, limiar=0.30):
    """Instante (s, no arquivo) em que o PLANO que começa em `start` termina (próximo corte de cena do comercial).
    None se o plano continua por toda a janela."""
    import re
    r = subprocess.run([FFMPEG, "-hide_banner", "-ss", f"{start:.2f}", "-t", f"{janela:.1f}", "-i", str(path),
                        "-vf", f"scale=160:-2,select='gt(scene,{limiar})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    ts = [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    ts = [t for t in ts if t > 0.4]
    return round(start + ts[0], 3) if ts else None


CENA = {"full": "b-roll", "viral": "tvzinha", "topo": "dividida 1", "meio": "dividida 2", "duo": "dois ativos", "tv": "tv"}
WHOOSH = ["camera_mirrorless", "click_mouse"]     # sons de câmera/clique (ele não gosta de "vento"/whoosh)
EMPH_MAX = 10         # palavras numa frase de destaque (mais que isso vira texto miúdo e ilegível)
SOLO_MIN_W = 24      # palavras: menos que isso (~7 s no vídeo final) entre dois ativos = emenda, ele não volta sozinho


def cenas_e_transicoes(new, code):
    """REGRA DELE (universal): 5 tipos de cena — só ele · B-roll vertical · tvzinha · tela dividida 1 · tela dividida 2.
    Em TODA troca de tipo de cena entra transição (desfoque rápido) + som curto (whoosh); dentro da mesma cena
    (fotos em sequência na tvzinha) continua o clique. Voltar para ele também é troca de cena."""
    import uuid
    media = sorted([o for o in new if o.get("type") == "media"], key=lambda o: o["w0"])
    # imagens quase encostadas (≤ 2 palavras): emenda — senão, na pausa entre elas você aparecia por 1–3 quadros
    for a_, b_ in zip(media, media[1:]):
        if b_["w0"] <= a_["w1"] + 2:
            a_["chain"] = True
    clicks = {o["w0"]: o for o in new if o.get("type") == "sfx" and o.get("reason") == "imagem entrando"}
    extra, k = [], 0

    def add(w, sfx_name, why):
        nonlocal k
        extra.append({"id": uuid.uuid4().hex[:8], "type": "transition", "style": "desfoque", "scene": True, "w0": w, "w1": w,
                      "reason": f"troca de cena: {why}", "plano": code})
        if sfx_name:
            extra.append({"id": uuid.uuid4().hex[:8], "type": "sfx", "sfx": sfx_name, "w0": w, "w1": w, "offset": 0,
                          "reason": f"troca de cena: {why}", "plano": code})
        k += 1
    for n, o in enumerate(media):
        prev = media[n - 1] if n else None
        nxt = media[n + 1] if n + 1 < len(media) else None
        junto_prev = prev and (prev.get("chain") or prev["w1"] >= o["w0"] - 2)
        cena, cena_prev = CENA.get(o.get("layout", "full"), "b-roll"), (CENA.get(prev.get("layout", "full"), "b-roll") if junto_prev else "você")
        if cena != cena_prev:
            clicks.pop(o["w0"], None)
            add(o["w0"], WHOOSH[k % 2], f"{cena_prev} → {cena}")
        elif junto_prev and o.get("layout", "full") in ("full", "viral"):
            # REGRA DELE (Epicteto): animação também ENTRE os B-rolls — desfoque rápido na troca (o som fica por conta
            # do clique de quando a imagem brota); dentro do 50/50 a troca continua limpa
            extra.append({"id": uuid.uuid4().hex[:8], "type": "transition", "style": "desfoque", "scene": True,
                          "w0": o["w0"], "w1": o["w0"], "reason": "animação entre B-rolls", "plano": code})
        junto_next = nxt and (o.get("chain") or nxt["w0"] <= o["w1"] + 2)
        if not junto_next:     # voltar para ele = transição com som (pedido dele: "não só eu preencher a tela toda")
            add(o["w1"] + 1, "click_classico", f"{cena} → você")
    # clique só quando FOTOS se sucedem na tvzinha; trocas dentro de bloco 50/50 ou de B-roll são silenciosas
    lay_at = {o["w0"]: o.get("layout", "full") for o in media}
    clicks = {w: c for w, c in clicks.items() if lay_at.get(w) == "viral"}
    keep_click = set(id(c) for c in clicks.values())
    out = [o for o in new if not (o.get("type") == "sfx" and o.get("reason") == "imagem entrando" and id(o) not in keep_click)]
    return out + extra


def aplicar(pid, code, plano=None):
    """Aplica `roteiros/edicao/<code>.json` ao projeto (ensaio ou gravação real). Devolve o relatório."""
    import uuid
    plano = plano or json.loads((EDICAO / f"{code}.json").read_text(encoding="utf-8"))
    corrigir_pelo_roteiro(pid, code)
    update(pid, lambda pp: pp.__setitem__("roteiro", code))      # navegação roteiro ↔ edição
    rep_cut = cortes_do_roteiro(pid, code)
    p = load(pid)
    words = p["words"]
    adir = PROJECTS / pid / "assets"
    rep, new = list(rep_cut), []
    n_split = 0
    for ov in plano.get("overlays", []):
        ov = dict(ov)
        em, ate = ov.pop("em", None), ov.pop("ate", None)
        click = ov.pop("click", ov.get("type") in ("media", "motion", "greenscreen"))
        a = _find(words, em) if em else None
        if not a:
            rep.append(f"✗ não achei na fala: {em!r} ({ov.get('type')})")
            continue
        w0, w1 = a
        from difflib import SequenceMatcher as _SM
        _got = [t for w in words[w0:a[1] + 1] for t in roteiros._toks(w["w"])]
        _sim = _SM(None, " ".join(roteiros._toks(em)), " ".join(_got)).ratio()
        if _sim < 0.7:                    # o casamento tolerante às vezes pega outra frase ("o seu argumento" → "o Joshie
            rep.append(f"⚠ âncora duvidosa ({_sim:.2f}): {em!r} → {' '.join(w['w'] for w in words[w0:a[1] + 1])!r}")
        if ate:
            b = _find(words, ate, w0)
            w1 = b[1] if b else w1
        ov.update(w0=w0, w1=max(w0, w1))
        for it in (ov.get("params") or {}).get("items", []) if isinstance(ov.get("params"), dict) else []:
            if isinstance(it, dict) and it.get("em"):
                h = _find(words, it.pop("em"), w0)
                if h:
                    it["w"] = h[0]
        for k in ("file", "file2"):
            if ov.get(k) and not (adir / ov[k]).exists() and (EDICAO / code / ov[k]).exists():
                shutil.copy2(EDICAO / code / ov[k], adir / ov[k])
        if ov.get("type") == "media" and ov.get("layout") == "viral" and ov.get("file") and (adir / ov["file"]).exists():
            i = probe(adir / ov["file"])
            if i.get("width") and i.get("height"):
                ov["ar"] = round(i["width"] / i["height"], 3)
                if ov["ar"] > 1.35 and kind_of_video(ov["file"]):
                    ov["layout"] = "meio"
        # REGRA DELE: tela cheia SÓ com ativo VERTICAL. Horizontal → tela dividida (`topo`: ativo em cima, ele
        # embaixo) — ou a tvzinha (`viral`), se o plano pediu. Nunca um horizontal esticado/cortado na tela toda.
        if ov.get("type") == "media" and ov.get("layout", "full") == "full" and not ov.get("crop_ok") and ov.get("file") and (adir / ov["file"]).exists():
            i = probe(adir / ov["file"])
            if (i.get("width") or 0) > (i.get("height") or 1) * 1.05:
                if kind_of_video(ov["file"]):
                    ov["layout"] = "meio"
                else:                    # foto horizontal: tvzinha na proporção dela (nunca foto cortada)
                    ov["layout"] = "viral"
                    ov["ar"] = round(i["width"] / i["height"], 3)
            elif kind_of_video(ov["file"]) is False and (i.get("width") or 0) > (i.get("height") or 1) * 0.7:
                # foto quase quadrada em tela cheia ficava cortada (a Terra no Joshie): tvzinha
                ov["layout"] = "viral"
                ov["ar"] = round(i["width"] / i["height"], 3)
        # REGRA DELE (18/10): a tela dividida "cabeça invadindo" (`topo`) saiu — a cabeça dele nunca invade a parte de
        # cima; toda tela dividida é o 45/55 (`meio`), sempre o mesmo layout num bloco
        if ov.get("type") == "media" and ov.get("layout") == "topo":
            ov["layout"] = "meio"
        if isinstance(ov.get("params"), dict):
            for f in ov["params"].get("files", []):
                if not (adir / f).exists() and (EDICAO / code / f).exists():
                    shutil.copy2(EDICAO / code / f, adir / f)
        ov.setdefault("reason", f"plano do roteiro {code}")
        ov["id"] = uuid.uuid4().hex[:8]
        ov["plano"] = code
        new.append(ov)
        if click:
            new.append({"id": uuid.uuid4().hex[:8], "type": "sfx", "sfx": "click_classico", "w0": w0, "w1": w0,
                        "offset": 0, "reason": "imagem entrando", "plano": code})
        rep.append(f"✓ [{w0}-{ov['w1']}] {ov.get('type')} {ov.get('layout') or ov.get('template') or ov.get('style') or ''}"
                   f" {ov.get('file') or ov.get('key') or ''} ← {em!r}")

    # REGRA DELE (Epicteto, 18/10): frase de destaque é CURTA — uma frase inteira virava 7–10 linhas miúdas
    # ("legenda ficou muito ruim"). Fica no máximo EMPH_MAX palavras, terminando na palavra-chave (ou no fim)
    for o in new:
        n_real = sum(1 for i in range(o["w0"], o["w1"] + 1) if words[i]["w"].strip()) if o.get("type") == "emphasis" else 0
        if o.get("type") == "emphasis" and n_real > EMPH_MAX:
            key = _sem_acento(o.get("key") or "")
            hit = [i for i in range(o["w0"], o["w1"] + 1) if key and key in _sem_acento(words[i]["w"])]
            end = hit[-1] if hit else o["w1"]          # termina NA palavra-chave
            start, n = end, 0                          # conta só palavras de verdade (sem as vazias da transcrição)
            while start > o["w0"] and n < EMPH_MAX:
                n += 1 if words[start]["w"].strip() else 0
                if n < EMPH_MAX:
                    start -= 1
            while start < end and not words[start]["w"].strip():
                start += 1
            for i in range(end - 1, start - 1, -1):    # começa depois de uma pontuação, se houver no caminho
                if words[i]["w"].strip() and words[i]["w"].rstrip()[-1] in ".,:;!?…":
                    start = i + 1
                    break
            o["w0"], o["w1"] = start, end
            rep.append(f"↳ destaque encurtado: {' '.join(w['w'] for w in words[start:end + 1])!r}")

    # REGRA DELE: nada de vaivém. Ativos horizontais em sequência viram UM bloco de tela dividida (50/50): ele fica
    # embaixo e os ativos vão trocando em cima, sem transição nem barulho entre eles
    sp_ = sorted([o for o in new if o.get("type") == "media"], key=lambda o: o["w0"])
    emph = [(o["w0"], o["w1"]) for o in new if o.get("type") == "emphasis"]
    for a_, b_ in zip(sp_, sp_[1:]):
        if any(a_["w1"] < e1 and e0 < b_["w0"] for e0, e1 in emph):
            continue                 # uma frase de destaque no meio é volta para ele COM motivo (não é "do nada")
        if a_.get("layout") in ("topo", "meio") and b_.get("layout") in ("topo", "meio") and b_["w0"] - a_["w1"] <= SOLO_MIN_W:
            a_["chain"] = True
            a_["layout"] = b_["layout"] = "meio"
        # REGRA DELE PARA SEMPRE: a cara dele "solo" nunca fica entre B-rolls nem entre telas divididas ("broll broll
        # broll, ou dividida dividida dividida"). Ele só volta sozinho se for ficar ~7 s ou mais (um bloco de fala
        # dele de verdade); senão o ativo atual fica até o próximo chegar
        elif b_["w0"] - a_["w1"] <= SOLO_MIN_W:
            a_["chain"] = True
    # telas divididas: mede a altura real da sua cabeça em cada trecho (prévia e render posicionam você por ela)
    src = PROJECTS / pid / p["source"]["file"]
    for o in new:
        if o.get("type") == "media" and o.get("layout") in ("topo", "meio") and o.get("file") and (adir / o["file"]).exists():
            i_ = probe(adir / o["file"])
            if i_.get("width") and i_.get("height"):
                o["ar"] = round(i_["width"] / i_["height"], 3)
        if o.get("type") == "media" and o.get("layout") == "tv":
            sala = Path(__file__).resolve().parent.parent / "backgrounds" / "tv_sala.mp4"
            if sala.exists() and not (adir / "tv_sala.mp4").exists():
                shutil.copy2(sala, adir / "tv_sala.mp4")
        if o.get("type") == "media" and o.get("layout") in ("topo", "meio", "tv"):
            try:
                o["head"] = head_top(src, words[o["w0"]]["start"] + 0.2)
            except Exception:  # noqa: BLE001
                pass
    # REGRA DELE: o vídeo de apoio mostra SÓ o plano escolhido (a lata), nunca escorrega para a cena seguinte do
    # comercial (a viatura) — guarda onde o plano acaba; prévia e render seguram nele
    for o in new:
        if o.get("type") == "media" and o.get("file") and "shot_end" not in o and kind_of_video(o["file"]) \
                and (adir / o["file"]).exists() and o.get("layout") != "duo":
            se = fim_do_plano(adir / o["file"], float(o.get("clip_start") or 0))
            if se:
                o["shot_end"] = se
        elif o.get("shot_end") is False:
            o.pop("shot_end")
    # FRASE DE DESTAQUE nunca no rosto (regra máxima): mede onde termina o rosto dele em cada uma (o enquadramento da
    # gravação real muda — no Joshie o queixo chegava a ~66% no gancho); o layout começa o bloco abaixo disso
    for o in new:
        if o.get("type") == "emphasis" or (o.get("type") == "motion" and o.get("template") in ("riscados", "acronimo", "cerebro")):
            try:
                fb = [x for x in (face_bottom(src, words[i]["start"] + 0.1) for i in (o["w0"], (o["w0"] + o["w1"]) // 2, o["w1"])) if x]
                if fb:
                    o["chin"] = max(fb)
            except Exception:  # noqa: BLE001
                pass
    new = cenas_e_transicoes(new, code)

    def f(pp):
        # com plano de edição, quem decide o que é LISTA é o plano: os "tópicos" automáticos saem (no Epicteto ele viu
        # "o humor…, a opinião…, uma crise…" virar lista — "não é uma listagem aqui, tem que ser legenda normal")
        keep = [o for o in pp["overlays"] if o.get("plano") != code and not (o.get("auto") and o.get("template") == "bullets")]
        # um destaque/mídia do plano substitui o automático que cair no mesmo trecho
        def clash(o):
            return o.get("auto") and o["type"] == "emphasis" and any(
                n["type"] in ("emphasis", "media", "motion") and not (n["w1"] < o["w0"] or n["w0"] > o["w1"]) for n in new)
        own_emph = any(n["type"] == "emphasis" for n in new)
        pp["overlays"] = [o for o in keep if not clash(o) and not (own_emph and o["type"] == "emphasis" and not o.get("plano"))] + new
        pp["settings"].update(plano.get("config", {}))
        if plano.get("musica"):
            m = plano["musica"]
            pp["music"] = [{"id": "plano", "file": m["file"], "title": m.get("title", m["file"]), "start": 0, "in": m.get("in", 0),
                            "dur": 9999, "vol": m.get("vol", 0.12), "fade": 1.5}]
    update(pid, f)
    if plano.get("musica"):                          # música do tamanho do vídeo editado
        from . import timeline
        dur = timeline.compute(load(pid))["duration"]
        update(pid, lambda pp: pp["music"][0].__setitem__("dur", round(dur, 2)))
    hl = roteiros.apply_highlights(pid, code)
    # dentro de uma frase de destaque o dourado é SÓ da palavra-chave: o negrito do roteiro ali sai (ficava tudo em
    # caixa alta dourada); e um negrito que é a própria frase de destaque não vai parar em outro lugar da fala
    # (no Jung, "**a música** escolheu" foi marcar o "se a música tinha influenciado")
    def tira_hl(pp):
        W = pp["words"]
        em = [(o["w0"], o["w1"]) for o in pp["overlays"] if o.get("type") == "emphasis"]
        em_txt = [" ".join(t for w in W[a:b + 1] for t in roteiros._toks(w["w"])) for a, b in em]
        for a, b in em:
            for i in range(a, b + 1):
                if W[i].get("hl") == "roteiro":
                    W[i].pop("hl")
        i = 0
        while i < len(W):
            if W[i].get("hl") == "roteiro":
                j = i
                while j + 1 < len(W) and W[j + 1].get("hl") == "roteiro":
                    j += 1
                run = " ".join(t for w in W[i:j + 1] for t in roteiros._toks(w["w"]))
                if any(f" {run} " in f" {t} " for t in em_txt):
                    for k in range(i, j + 1):
                        W[k].pop("hl")
                i = j + 1
            else:
                i += 1
    update(pid, tira_hl)
    rep.append(f"negrito do roteiro → destaque na legenda: {len(hl['achados'])}"
               + (f" (não achei: {hl['faltando']})" if hl["faltando"] else ""))
    return rep


def lacunas(pid, max_s=6.0):
    """REGRA DELE: nunca mais de 5–7 s só ele falando sem nada visual (dopamina). Lista os trechos (tempo do vídeo
    final) sem B-roll/motion/tvzinha/tela verde/destaque por mais de `max_s`, com o que está sendo dito."""
    from . import timeline
    p = load(pid)
    c = timeline.compute(p)
    sp = float(p["settings"].get("speed", 1) or 1)
    vis = sorted((o["a"], o["b"]) for o in c["overlays"]
                 if o.get("type") in ("media", "motion", "greenscreen", "emphasis") and "a" in o)
    out, t = [], 0.0
    for a, b in vis + [(c["duration"], c["duration"])]:
        if a - t > max_s:
            ws = [c2 for c2 in c["captions"] if t <= c2["a"] < a]
            texto = " ".join(w["w"] for c2 in ws for w in c2["words"])
            out.append({"de": round(t / sp, 1), "ate": round(a / sp, 1), "s": round((a - t) / sp, 1), "fala": texto})
        t = max(t, b)
    return out


def montar(code, stand_in=None, voz="rapida"):
    mp4 = ensaio(code, stand_in, voz)
    r = next(x for x in roteiros.load() if x["code"] == code)
    pid = criar_projeto(mp4, f"{code} · ensaio · {r['title']}")
    corrigir_pelo_roteiro(pid, code)
    rep = aplicar(pid, code) if (EDICAO / f"{code}.json").exists() else ["(ainda sem roteiros/edicao/%s.json)" % code]
    return pid, rep

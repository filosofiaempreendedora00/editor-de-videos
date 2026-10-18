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
                if SequenceMatcher(None, wt[i], st[j]).ratio() >= 0.6:
                    fixes[i] = script[j]
        elif op == "replace" and a1 - a0 == 1 and 2 <= b1 - b0 <= 3:
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


CENA = {"full": "b-roll", "viral": "tvzinha", "topo": "dividida 1", "meio": "dividida 2"}
WHOOSH = ["camera_mirrorless", "click_mouse"]     # sons de câmera/clique (ele não gosta de "vento"/whoosh)


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
        junto_next = nxt and (o.get("chain") or nxt["w0"] <= o["w1"] + 2)
        # voltar para ele = corte seco (sem transição nem som): menos vaivém (pedido dele)
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
    p = load(pid)
    words = p["words"]
    adir = PROJECTS / pid / "assets"
    rep, new = [], []
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
        if ate:
            b = _find(words, ate, w0)
            w1 = b[1] if b else w1
        ov.update(w0=w0, w1=max(w0, w1))
        for it in (ov.get("params") or {}).get("items", []) if isinstance(ov.get("params"), dict) else []:
            if isinstance(it, dict) and it.get("em"):
                h = _find(words, it.pop("em"), w0)
                if h:
                    it["w"] = h[0]
        for k in ("file",):
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
                # alterna os dois estilos de tela dividida (variedade de cenas); sequência emendada fica no mesmo
                if not (new and new[-1].get("chain") and new[-1].get("layout") in ("topo", "meio")):
                    n_split += 1
                ov["layout"] = "topo" if n_split % 2 else "meio"
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

    # REGRA DELE: nada de vaivém. Ativos horizontais em sequência viram UM bloco de tela dividida (50/50): ele fica
    # embaixo e os ativos vão trocando em cima, sem transição nem barulho entre eles
    sp_ = sorted([o for o in new if o.get("type") == "media"], key=lambda o: o["w0"])
    for a_, b_ in zip(sp_, sp_[1:]):
        if a_.get("layout") in ("topo", "meio") and b_.get("layout") in ("topo", "meio") and b_["w0"] - a_["w1"] <= 8:
            a_["chain"] = True
            a_["layout"] = b_["layout"] = "meio"
    # telas divididas: mede a altura real da sua cabeça em cada trecho (prévia e render posicionam você por ela)
    src = PROJECTS / pid / p["source"]["file"]
    for o in new:
        if o.get("type") == "media" and o.get("layout") in ("topo", "meio"):
            try:
                o["head"] = head_top(src, words[o["w0"]]["start"] + 0.2)
            except Exception:  # noqa: BLE001
                pass
    new = cenas_e_transicoes(new, code)

    def f(pp):
        keep = [o for o in pp["overlays"] if o.get("plano") != code]
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

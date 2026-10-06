"""Servidor local do editor. Rode com ./iniciar.sh e abra http://localhost:8765"""
import json
import os
import re
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import List

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from . import brain, fonts, presets, media, motion, plan, reference, refs, render, sfx, sources, timeline, transcribe  # noqa: E402
from .store import PROJECTS, load, lock, pdir, save, update  # noqa: E402

app = FastAPI(title="Editor de Vídeos")
jobs = {}


@app.middleware("http")
async def no_cache_for_app(request, call_next):
    """A interface muda com frequência: o navegador sempre confere se há versão nova (sem cache velho)."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def view(p):
    """Projeto + dados derivados (trechos, legendas, inserções posicionadas)."""
    out = dict(p)
    out["preview"] = "preview.mp4" if (PROJECTS / p["id"] / "preview.mp4").exists() else None
    scene_now = (p.get("settings") or {}).get("bg_scene") or "none"
    pb = PROJECTS / p["id"] / "preview_bg.json"
    if scene_now != "none" and pb.exists() and json.loads(pb.read_text()).get("scene") == scene_now:
        out["preview"] = "preview_bg.mp4"
    if p.get("status") == "ready":
        out["computed"] = timeline.compute(p)
    out["cutout"] = "fg_alpha.webm" if (PROJECTS / p["id"] / "fg_alpha.webm").exists() else None
    cj = next((j for j in jobs.values() if j["project"] == p["id"] and j["kind"] == "cutout"
               and j["status"] == "running"), None)
    out["cutout_job"] = cj["id"] if cj else None
    # processamento de fundo em andamento (a página retoma o acompanhamento ao abrir)
    bj = next((j for j in jobs.values() if j["project"] == p["id"] and j["kind"] == "background"
               and j["status"] == "running"), None)
    out["bg_job"] = bj["id"] if bj else None
    return out


# ---------------------------------------------------------------- jobs em segundo plano

def start_job(pid, kind, fn):
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "project": pid, "kind": kind, "status": "running",
           "progress": 0.0, "message": "", "result": None}
    jobs[jid] = job

    def progress(x, msg=None):
        job["progress"] = round(float(x), 3)
        if msg:
            job["message"] = msg

    def run():
        try:
            job["result"] = fn(progress)
            job["status"] = "done"
            job["progress"] = 1.0
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job["status"] = "error"
            job["message"] = str(e)[:1500]

    threading.Thread(target=run, daemon=True).start()
    return job


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    if jid not in jobs:
        raise HTTPException(404, "job não encontrado")
    return jobs[jid]


# ---------------------------------------------------------------- status

@app.get("/api/status")
def status():
    return {
        "engines": brain.engines(),
        "claude_model": brain.CLAUDE_MODEL,
        "ollama_model": brain.OLLAMA_MODEL,
        "whisper": transcribe.MODEL_SIZE,
        "transcriber": transcribe.engine(),
        "vocab": transcribe.vocabulary(),
        "chrome": bool(sources.chrome()),
        "sources": sources.SOURCES,
        "templates": brain.MOTION_TEMPLATES,
        "sfx": sfx.library(),
        "looks": list(render.LOOKS),
        "styles": {k: {"name": v["name"], "description": v.get("description", ""), "palette": v.get("palette", {})}
                   for k, v in presets.all_presets().items()},
        "default_style": presets.default_slug(),
    }


# ---------------------------------------------------------------- projetos

@app.get("/api/projects")
def list_projects():
    items = []
    for d in PROJECTS.iterdir():
        f = d / "project.json"
        if f.exists():
            p = json.loads(f.read_text(encoding="utf-8"))
            items.append({k: p.get(k) for k in ("id", "name", "created", "updated", "status")}
                         | {"duration": p["source"].get("duration")})
    return sorted(items, key=lambda x: -(x.get("updated") or 0))


def run_plan(pid, engine, progress, apply_cuts=True):
    p = load(pid)
    fmt = reference.load(p["formato"]) if p.get("formato") else None
    progress(0.1, {"regras": "Analisando o roteiro…", "ollama": "IA local analisando o roteiro…",
                   "claude_api": "Claude analisando o roteiro…"}.get(engine, "Analisando…"))
    result = brain.plan(engine, p["words"], p["deleted"], p["source"]["duration"], formato=fmt,
                        project_dir=pdir(pid))
    update(pid, lambda pp: plan.apply(pp, result, engine, apply_cuts=apply_cuts))
    return {"cuts": len(result.get("cuts", [])), "items": len(result.get("items", [])),
            "analysis": result.get("analysis", {})}


def _safe_name(name):
    return re.sub(r"[^\w.\-]", "_", Path(name).name)


@app.post("/api/projects")
async def create_project(file: List[UploadFile] = File(...), extras: List[UploadFile] = File(default=[]),
                         language: str = Form("pt"), engine: str = Form("regras"), formato: str = Form(""),
                         autofill: bool = Form(True)):
    """`file`: uma ou mais gravações (juntadas em ordem de nome). `extras`: prints/vídeos de apoio (vão para assets/)."""
    pid = uuid.uuid4().hex[:10]
    d = PROJECTS / pid
    (d / "assets").mkdir(parents=True)
    (d / "exports").mkdir()
    takes_up = sorted(file, key=lambda u: media.natural_key(u.filename or ""))
    if len(takes_up) == 1:
        ext = Path(takes_up[0].filename or "video.mp4").suffix.lower() or ".mp4"
        takes = [d / f"source{ext}"]
    else:
        (d / "takes").mkdir()
        takes = [d / "takes" / f"{k + 1:02d}_{_safe_name(u.filename or 'video.mp4')}" for k, u in enumerate(takes_up)]
    for u, dst in zip(takes_up, takes):
        with dst.open("wb") as fh:
            shutil.copyfileobj(u.file, fh, length=8 * 1024 * 1024)
    infos = [media.probe(t) for t in takes]
    if not all(i["has_video"] for i in infos):
        bad = [u.filename for u, i in zip(takes_up, infos) if not i["has_video"]]
        shutil.rmtree(d)
        raise HTTPException(400, "Não encontrei vídeo em: " + ", ".join(bad))
    for u in extras:
        name = f"{uuid.uuid4().hex[:6]}_{_safe_name(u.filename or 'arquivo')}"
        if media.kind_of(name) == "unknown":
            continue
        with (d / "assets" / name).open("wb") as fh:
            shutil.copyfileobj(u.file, fh, length=8 * 1024 * 1024)
    multi = len(takes) > 1
    src = d / "source.mp4" if multi else takes[0]
    info = dict(infos[0])
    if multi:
        info.update(duration=sum(i["duration"] for i in infos), hdr=None, rotation=0)
    settings = {**timeline.DEFAULT_SETTINGS, "reframe": True, "smooth_zoom": True, "scene_transition": "leak",
                "rhythm_cuts": True,
                **presets.settings_for(presets.default_slug()), **presets.user_defaults()}
    fmt = reference.load(formato) if formato else None
    if fmt:
        settings.update(fmt.get("settings", {}))
    stem = Path(takes_up[0].filename or "Vídeo").stem
    p = {
        "id": pid, "name": stem + (f" (+{len(takes) - 1})" if multi else ""), "created": time.time(), "updated": time.time(),
        "status": "processing", "language": language, "formato": formato or None,
        "source": {"file": src.name, **info},
        "takes": [u.filename for u in takes_up] if multi else None,
        "words": [], "deleted": [], "overlays": [], "ai_cuts": [], "credits": [], "settings": settings,
    }
    save(p)
    media.thumbnail(takes[0], d / "thumb.jpg", at=min(1.0, infos[0]["duration"] / 2))

    def pipeline(progress):
        nonlocal info
        if multi:
            progress(0.01, f"Juntando {len(takes)} gravações em ordem de nome…")
            media.concat_takes(takes, src)
            info = media.probe(src)
            update(pid, lambda pp: pp.__setitem__("source", {"file": src.name, **info}))
            shutil.rmtree(d / "takes", ignore_errors=True)
        progress(0.02, "Extraindo áudio…")
        wav = d / "audio.wav"
        words = []
        if info["has_audio"]:
            media.extract_audio(src, wav)
            (d / "waveform.json").write_text(json.dumps(media.waveform_peaks(wav)))
            progress(0.05, "Transcrevendo a fala (Whisper, no seu Mac)…")
            words = transcribe.transcribe(wav, language, on_progress=lambda x: progress(0.05 + x * 0.7))
        fillers = [w["i"] for w in words if timeline.is_filler(w["w"])]
        sil = transcribe.silences(wav) if info["has_audio"] else []
        if info.get("hdr"):
            progress(0.76, "Preparando a prévia (vídeo HDR)…")
            media.make_proxy(src, d / "preview.mp4", info["hdr"])

        def done(pp):
            pp["words"] = words
            pp["deleted"] = fillers
            pp["silences"] = sil
            pp["status"] = "ready"
        update(pid, done)
        if words:
            eng = engine if brain.engines().get(engine) and engine != "claude_code" else "regras"
            try:
                run_plan(pid, eng, lambda x, m=None: progress(0.76 + 0.1 * x, m))
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                progress(0.86, f"Plano automático falhou ({e}); usando regras.")
                run_plan(pid, "regras", lambda x, m=None: None)
            # TELA VERDE automática: se você lê um print de apoio no vídeo, ele vira o fundo e você vai pro canto
            try:
                from . import greenscreen
                progress(0.88, "Procurando prints que você lê no vídeo…")
                update(pid, lambda pp: greenscreen.auto_detect(pp, d))
                if any(o.get("type") == "greenscreen" for o in load(pid).get("overlays", [])):
                    from . import background
                    background.ensure_cutout(load(pid), d,
                                             on_progress=lambda x, m=None: progress(0.88 + 0.1 * x, m))
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            if autofill and load(pid)["settings"].get("inserts"):
                pp = load(pid)
                res = plan.autofill(pp, d / "assets",
                                    on_progress=lambda x, m=None: progress(0.87 + 0.12 * x, m))
                update(pid, lambda q: q.update(overlays=pp["overlays"], credits=pp.get("credits", [])))
        return {"words": len(words)}

    job = start_job(pid, "process", pipeline)
    update(pid, lambda pp: pp.__setitem__("job", job["id"]))
    return {"project": view(load(pid)), "job": job}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return view(load(pid))


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: dict = Body(...)):
    allowed = {"deleted", "overlays", "settings", "name", "manual", "order", "splits", "music"}

    def apply(p):
        for k, v in body.items():
            if k not in allowed:
                continue
            if k == "settings":
                p["settings"] = {**p.get("settings", {}), **v}
                presets.remember(v)
            elif k == "deleted":
                p["deleted"] = sorted(set(int(i) for i in v))
            else:
                p[k] = v
        plan.ensure_ids(p)
    return view(update(pid, apply))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    shutil.rmtree(pdir(pid))
    return {"ok": True}


@app.post("/api/projects/{pid}/assets")
async def upload_asset(pid: str, file: UploadFile = File(...)):
    d = pdir(pid) / "assets"
    name = f"{uuid.uuid4().hex[:6]}_{_safe_name(file.filename or 'arquivo')}"
    with (d / name).open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    kind = media.kind_of(name)
    if kind == "unknown":
        (d / name).unlink()
        raise HTTPException(400, "Formato não suportado. Use imagem, vídeo ou áudio.")
    return {"file": name, "kind": kind}


@app.get("/api/projects/{pid}/assets")
def list_assets(pid: str):
    p = load(pid)
    credits = {c["file"]: c for c in p.get("credits", [])}
    d = pdir(pid) / "assets"
    out = []
    for f in sorted(d.iterdir(), key=lambda x: -x.stat().st_mtime):
        if f.is_file() and not f.name.startswith(".") and media.kind_of(f.name) != "unknown":
            out.append({"file": f.name, "kind": media.kind_of(f.name), "credit": credits.get(f.name)})
    return out


def _learn(old, new):
    """Aprende termos que você corrigiu (nomes, marcas, siglas) para as próximas transcrições."""
    olds = {w.lower() for w in old.split()}
    terms = [re.sub(r"[^\wÀ-ÿ\-]", "", t) for t in new.split()]
    keep = [t for t in terms if t and t.lower() not in olds and (t[0].isupper() or any(c.isdigit() for c in t)
                                                              or (len(t) >= 2 and t.isupper()))]
    return transcribe.add_vocabulary(keep)


@app.post("/api/projects/{pid}/words")
def edit_words(pid: str, body: dict = Body(...)):
    """Corrige o texto das palavras i0..i1 (a legenda muda; tempos, cortes e inserções ficam)."""
    i0, i1, text = int(body["i0"]), int(body["i1"]), str(body.get("text", "")).strip()
    learned = []

    def apply(p):
        words = p["words"]
        if not (0 <= i0 <= i1 < len(words)):
            raise HTTPException(400, "trecho inválido")
        old = " ".join(words[i]["w"] for i in range(i0, i1 + 1))
        transcribe.replace_text(words, i0, i1, text)
        learned.extend(_learn(old, text))
    out = view(update(pid, apply))
    out["learned"] = learned
    return out


@app.post("/api/projects/{pid}/range")
def edit_range(pid: str, body: dict = Body(...)):
    """Corta ou restaura um trecho por TEMPO (vídeo original), como a lâmina de um editor."""
    a, b, mode = float(body["a"]), float(body["b"]), body.get("mode", "cut")
    if b < a:
        a, b = b, a

    def apply(p):
        p.setdefault("manual", []).append({"a": round(a, 3), "b": round(b, 3), "mode": mode})
        d = set(p["deleted"])
        for w in p["words"]:
            mid = (w["start"] + w["end"]) / 2
            if a <= mid <= b:
                (d.discard if mode == "keep" else d.add)(w["i"])
        p["deleted"] = sorted(d)
        if mode == "cut" and body.get("ripple"):
            # excluir um PEDAÇO (estilo CapCut): o que estava preso a ele (sons, transições, destaques) sai junto;
            # o resto já anda para a esquerda sozinho, porque tudo é ancorado nas palavras
            dl = set(p["deleted"])
            def inside(o):
                w0, w1 = o.get("w0", -1), o.get("w1", o.get("w0", -1))
                return w0 >= 0 and all(i in dl for i in range(w0, w1 + 1))
            p["overlays"] = [o for o in p["overlays"] if not inside(o)]
            p["splits"] = [t for t in p.get("splits", []) if not (a + 0.02 < t < b - 0.02)]
    return view(update(pid, apply))


@app.post("/api/projects/{pid}/reprocess")
def reprocess(pid: str, body: dict = Body(default={})):
    """Refaz a transcrição (motor novo), os silêncios e o plano. Cortes/inserções anteriores são refeitos."""
    d = pdir(pid)

    def run(progress):
        p = load(pid)
        wav = d / "audio.wav"
        progress(0.05, "Transcrevendo de novo…")
        words = transcribe.transcribe(wav, p.get("language") or "pt",
                                      on_progress=lambda x: progress(0.05 + 0.75 * x, "Transcrevendo de novo…"))
        sil = transcribe.silences(wav)

        def apply(pp):
            pp.update(words=words, silences=sil, deleted=[w["i"] for w in words if timeline.is_filler(w["w"])],
                      overlays=[], ai_cuts=[], manual=[])
            keep = {k: v for k, v in pp.get("settings", {}).items() if k in ("format", "music", "music_volume")}
            style = pp.get("settings", {}).get("style") or presets.default_slug()
            pp["settings"] = {**timeline.DEFAULT_SETTINGS, **presets.settings_for(style), **keep}
        update(pid, apply)
        (d / "grade.json").unlink(missing_ok=True)
        run_plan(pid, body.get("engine") or "regras", lambda x, m=None: progress(0.82 + 0.17 * x, m))
        return {"words": len(words)}
    return start_job(pid, "reprocess", run)


@app.post("/api/projects/{pid}/proxy")
def make_proxy(pid: str):
    """Gera a cópia de prévia (para projetos HDR antigos)."""
    d = pdir(pid)

    def run(progress):
        p = load(pid)
        info = media.probe(d / p["source"]["file"])
        if info.get("hdr") and not (d / "preview.mp4").exists():
            progress(0.1, "Preparando a prévia…")
            media.make_proxy(d / p["source"]["file"], d / "preview.mp4", info["hdr"])
        update(pid, lambda pp: pp["source"].update(hdr=info.get("hdr")))
        return {"preview": (d / "preview.mp4").exists()}
    return start_job(pid, "proxy", run)


@app.get("/api/projects/{pid}/grade")
def get_grade(pid: str):
    p = load(pid)
    pr = render.grade_params(p, pdir(pid), float(p.get("settings", {}).get("grade_strength", 1.0)))
    return {k: v for k, v in (pr or {}).items() if k != "analysis"}


@app.post("/api/projects/{pid}/style")
def apply_style(pid: str, body: dict = Body(...)):
    """Aplica uma identidade visual ao projeto (e, se pedido, torna padrão para vídeos novos)."""
    slug = body.get("slug") or "padrao"
    if slug not in presets.all_presets():
        raise HTTPException(404, "identidade não encontrada")
    if body.get("default"):
        presets.set_default(slug)
    return view(update(pid, lambda p: p.__setitem__("settings", {**p.get("settings", {}), **presets.settings_for(slug)})))


@app.get("/api/vocab")
def get_vocab():
    return {"terms": transcribe.vocabulary()}


@app.put("/api/vocab")
def put_vocab(body: dict = Body(...)):
    terms = [t.strip() for t in re.split(r"[\n,;]+", body.get("text", "")) if t.strip()]
    transcribe.VOCAB_FILE.write_text("\n".join(terms) + "\n", encoding="utf-8")
    return {"terms": terms}


@app.post("/api/projects/{pid}/autocut")
def autocut(pid: str, body: dict = Body(default={})):
    """Corta hesitações e ajusta o limite de pausa."""
    def apply(p):
        p["settings"] = {**p.get("settings", {}), **(body.get("settings") or {})}
        fillers = {w["i"] for w in p["words"] if timeline.is_filler(w["w"])}
        p["deleted"] = sorted(set(p["deleted"]) | fillers)
    return view(update(pid, apply))


# ---------------------------------------------------------------- plano (roteiro -> inserções)

@app.post("/api/projects/{pid}/plan")
def make_plan(pid: str, body: dict = Body(default={})):
    pdir(pid)
    engine = body.get("engine", "regras")
    if engine == "claude_code":
        p = load(pid)
        fmt = reference.load(p["formato"]) if p.get("formato") else None
        f = brain.write_claude_code_brief(p, pdir(pid), fmt)
        return {"brief": str(f.relative_to(ROOT)),
                "prompt": f"Leia {f.relative_to(ROOT)} e escreva o plano de edição em "
                          f"projects/{pid}/plano.json, seguindo as instruções do arquivo."}
    if not brain.engines().get(engine):
        raise HTTPException(400, {"ollama": "O Ollama não está rodando. Instale em ollama.com e rode "
                                            f"`ollama pull {brain.OLLAMA_MODEL}`.",
                                  "claude_api": "Coloque ANTHROPIC_API_KEY no arquivo .env e reinicie."}
                            .get(engine, "Motor indisponível."))
    return start_job(pid, "plan", lambda progress: run_plan(pid, engine, progress,
                                                            apply_cuts=body.get("cuts", True)))


@app.post("/api/projects/{pid}/plan/load")
def load_claude_code_plan(pid: str):
    return start_job(pid, "plan", lambda progress: run_plan(pid, "claude_code", progress))


@app.post("/api/projects/{pid}/autofill")
def autofill(pid: str):
    d = pdir(pid)

    def run(progress):
        p = load(pid)
        res = plan.autofill(p, d / "assets", on_progress=progress)
        update(pid, lambda q: q.update(overlays=p["overlays"], credits=p.get("credits", [])))
        return res
    return start_job(pid, "autofill", run)


# ---------------------------------------------------------------- busca de materiais

@app.get("/api/sources/search")
def search_sources(source: str, q: str, lang: str = "pt"):
    try:
        return sources.search(source, q, lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Falha ao buscar em {source}: {e}")


@app.post("/api/sources/resolve")
def resolve_source(result: dict = Body(...)):
    try:
        return {"url": sources.resolve_video(result)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, str(e))


@app.post("/api/projects/{pid}/fetch")
def fetch_material(pid: str, body: dict = Body(...)):
    """Baixa um resultado de busca para o projeto e (opcional) o encaixa numa inserção."""
    d = pdir(pid)
    result = body["result"]

    def run(progress):
        progress(0.1, "Baixando material…")
        got = sources.fetch(result, d / "assets", start=float(body.get("start", 0)),
                            length=float(body.get("length", 8)), mode=body.get("mode", "card"),
                            explicit_start="start" in body and float(body.get("start") or 0) > 0)

        def apply(p):
            plan.add_credit(p, result, got["file"])
            oid = body.get("overlay_id")
            for o in p.get("overlays", []):
                if o.get("id") == oid:
                    o["file"] = got["file"]
                    o["auto"] = False
                    if got.get("print"):
                        o["print"] = True
                        if o.get("layout") in (None, "full"):
                            o["layout"] = "card"
        update(pid, apply)
        return got
    return start_job(pid, "fetch", run)


# ---------------------------------------------------------------- formatos (referências)

@app.get("/api/formatos")
def list_formatos():
    return reference.list_all()


@app.post("/api/formatos")
def create_formato(body: dict = Body(...)):
    return reference.create(body.get("name") or "Meu formato")


@app.patch("/api/formatos/{slug}")
def patch_formato(slug: str, body: dict = Body(...)):
    fmt = reference.load(slug)
    if not fmt:
        raise HTTPException(404)
    for k in ("name", "notes"):
        if k in body:
            fmt[k] = body[k]
    reference.save(fmt)
    return reference.rebuild(slug)


@app.delete("/api/formatos/{slug}")
def delete_formato(slug: str):
    d = reference.formato_dir(slug)
    if d.exists() and d.parent == reference.FORMATOS:
        shutil.rmtree(d)
    return {"ok": True}


@app.post("/api/formatos/{slug}/refs")
async def add_reference(slug: str, file: UploadFile = File(...), language: str = Form("")):
    if not reference.load(slug):
        raise HTTPException(404)
    d = reference.formato_dir(slug) / "refs"
    d.mkdir(exist_ok=True)
    name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "ref.mp4").name)
    dst = d / f"{uuid.uuid4().hex[:6]}_{name}"
    with dst.open("wb") as fh:
        shutil.copyfileobj(file.file, fh, length=8 * 1024 * 1024)

    def run(progress):
        reference.analyze(dst, d, language=language or None, on_progress=progress)
        return reference.rebuild(slug)
    return start_job(slug, "reference", run)


@app.delete("/api/formatos/{slug}/refs/{stem}")
def delete_reference(slug: str, stem: str):
    d = reference.formato_dir(slug) / "refs"
    for f in d.glob(f"{stem}*"):
        if f.parent == d:
            f.unlink()
    return reference.rebuild(slug)


@app.post("/api/projects/{pid}/formato")
def apply_formato(pid: str, body: dict = Body(...)):
    slug = body.get("slug") or None
    fmt = reference.load(slug) if slug else None

    def apply(p):
        p["formato"] = slug
        if fmt:
            p["settings"] = {**p.get("settings", {}), **fmt.get("settings", {})}
    return view(update(pid, apply))


@app.get("/formatos-media/{slug}/{name}")
def formato_media(slug: str, name: str):
    f = (reference.formato_dir(slug) / "refs" / name).resolve()
    if reference.FORMATOS.resolve() not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ---------------------------------------------------------------- exportação

@app.post("/api/projects/{pid}/render")
def do_render(pid: str):
    d = pdir(pid)

    def run(progress):
        p = load(pid)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^\w\-]", "_", p["name"])[:40] or "video"
        out = d / "exports" / f"{safe}-{stamp}.mp4"
        progress(0.01, "Preparando…")
        render.render(p, d, out, on_progress=lambda x, m=None: progress(x, m or "Renderizando…"))
        cred = out.with_suffix(".creditos.txt")
        return {"file": out.name, "url": f"/media/{pid}/exports/{out.name}",
                "credits": f"/media/{pid}/exports/{cred.name}" if cred.exists() else None}
    return start_job(pid, "render", run)


@app.get("/api/projects/{pid}/exports")
def list_exports(pid: str):
    d = pdir(pid) / "exports"
    files = sorted(d.glob("*.mp4"), key=lambda f: -f.stat().st_mtime)
    return [{"file": f.name, "url": f"/media/{pid}/exports/{f.name}", "size": f.stat().st_size} for f in files]


@app.get("/api/projects/{pid}/waveform")
def waveform(pid: str):
    f = pdir(pid) / "waveform.json"
    return JSONResponse(json.loads(f.read_text()) if f.exists() else [])


@app.get("/media/{pid}/{path:path}")
def serve_media(pid: str, path: str):
    base = pdir(pid).resolve()
    f = (base / path).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


sfx.ensure_library()
threading.Thread(target=sfx.download_catalog, daemon=True).start()
fonts.ensure()
# ------------------------------------------------------------------ referências (links salvos em referencias/links.json)
@app.post("/api/projects/{pid}/cutout")
def make_cutout(pid: str):
    """Recorta você do fundo (uma vez por vídeo) — para a tela verde aparecer recortada já na prévia."""
    from . import background
    running = next((j for j in jobs.values() if j["project"] == pid and j["kind"] in ("cutout", "background")
                    and j["status"] == "running"), None)
    if running:
        return running
    return start_job(pid, "cutout", lambda progress: {"cutout": background.ensure_cutout(load(pid), pdir(pid), progress)})


@app.post("/api/projects/{pid}/greenscreen")
def add_greenscreen(pid: str, body: dict = Body(...)):
    """Tela verde com um print: acha sozinho o trecho em que você o lê; ou usa o trecho dado (w0..w1)."""
    from . import greenscreen
    from .plan import new_id
    file = body.get("file") or ""
    p = load(pid)
    if not (pdir(pid) / "assets" / file).exists():
        raise HTTPException(404, "Arquivo não encontrado.")
    found = None
    if body.get("w0") is None:
        try:
            found = greenscreen.detect(p, pdir(pid), file)
        except Exception:  # noqa: BLE001
            found = None
    if found:
        ov = found
    elif body.get("w0") is not None:
        ov = {"type": "greenscreen", "file": file, "w0": int(body["w0"]), "w1": int(body.get("w1", body["w0"])),
              "corner": "bl", "size": 0.52}
    else:
        return {"found": False, "project": view(p)}
    ov["id"] = new_id()
    ov["corner"] = body.get("corner", ov.get("corner", "bl"))
    p = update(pid, lambda pp: pp.setdefault("overlays", []).append(ov))
    return {"found": bool(found), "overlay": ov, "project": view(p)}


@app.get("/api/music")
def music_list():
    from . import music
    out = []
    for c in music.CATALOG:
        p = music.MUSIC_DIR / f"{c['slug']}.mp3"
        out.append({**c, "file": "lib:" + c["slug"], "src": f"/api/music/{c['slug']}/file",
                    "duration": music.duration(p) if p.exists() else None})
    return out


@app.get("/api/music/{slug}/file")
def music_file(slug: str):
    from . import music
    if not music.entry(slug):
        raise HTTPException(404)
    return FileResponse(music.ensure(slug), media_type="audio/mpeg")


@app.get("/api/music/{slug}/info")
def music_info(slug: str):
    from . import music
    if not music.entry(slug):
        raise HTTPException(404)
    return {"duration": music.duration(music.ensure(slug))}


@app.get("/api/backgrounds")
def backgrounds_list():
    from . import background
    return [{**sc, "thumb": f"/api/backgrounds/{sc['slug']}/thumb"} for sc in background.SCENES]


@app.get("/api/backgrounds/{slug}/thumb")
def background_thumb(slug: str):
    from . import background
    if not background.scene(slug):
        raise HTTPException(404)
    return FileResponse(background.thumb(slug))


@app.post("/api/projects/{pid}/background")
def set_background(pid: str, body: dict = Body(...)):
    """Troca o fundo (cenário). Na 1ª vez recorta você + cadeira (~2 min); depois é rápido."""
    from . import background
    scene = body.get("scene") or "none"
    if scene != "none" and not scene.startswith("file:") and not background.scene(scene):
        raise HTTPException(400, "Cenário desconhecido.")
    update(pid, lambda p: p["settings"].__setitem__("bg_scene", scene))
    d = pdir(pid)
    # um processamento de fundo por vídeo: se já há um rodando, ele usa o cenário escolhido por último
    running = next((j for j in jobs.values() if j["project"] == pid and j["kind"] == "background"
                    and j["status"] == "running"), None)
    if running:
        return running

    def work(progress):
        while True:
            p = load(pid)
            sc = p["settings"].get("bg_scene") or "none"
            if sc == "none":
                return {"preview": None}
            name = background.apply(p, d, on_progress=progress)
            if (load(pid)["settings"].get("bg_scene") or "none") == sc:   # trocou no meio? refaz a prévia
                return {"preview": name}
    job = start_job(pid, "background", work)
    return job


@app.get("/api/refs")
def refs_list():
    return refs.load()


@app.post("/api/refs")
def refs_add(body: dict = Body(...)):
    res = refs.add(body.get("text", ""), body.get("note", ""), body.get("tags"))
    if not res["added"] and not res["updated"]:
        raise HTTPException(400, "Não encontrei nenhum link nesse texto.")
    return res


@app.get("/api/refs/sync")
def refs_sync_status():
    return refs.sync_status()


@app.post("/api/refs/sync")
def refs_sync_now():
    refs.sync_github()
    return refs.sync_status()


@app.get("/api/refs/thumb/{name}")
def refs_thumb(name: str):
    path = refs.THUMBS / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.patch("/api/refs/{rid}")
def refs_edit(rid: str, body: dict = Body(...)):
    try:
        return refs.edit(rid, body)
    except KeyError:
        raise HTTPException(404, "Referência não encontrada.")


@app.delete("/api/refs/{rid}")
def refs_delete(rid: str):
    try:
        refs.remove(rid)
    except KeyError:
        raise HTTPException(404, "Referência não encontrada.")
    return {"ok": True}


app.mount("/sfx", StaticFiles(directory=sfx.SFX_DIR), name="sfx")
app.mount("/fonts", StaticFiles(directory=fonts.FONT_DIR), name="fonts")
app.mount("/motion", StaticFiles(directory=motion.MOTION_DIR), name="motion")
app.mount("/", StaticFiles(directory=ROOT / "app" / "static", html=True), name="static")


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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from . import ai, media, render, timeline, transcribe  # noqa: E402

PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)

app = FastAPI(title="Editor de Vídeos")
locks = {}
jobs = {}


# ---------------------------------------------------------------- persistência

def pdir(pid):
    if not re.fullmatch(r"[a-z0-9]{6,16}", pid):
        raise HTTPException(404, "projeto não encontrado")
    d = PROJECTS / pid
    if not (d / "project.json").exists():
        raise HTTPException(404, "projeto não encontrado")
    return d


def lock(pid):
    return locks.setdefault(pid, threading.RLock())


def load(pid):
    return json.loads((pdir(pid) / "project.json").read_text(encoding="utf-8"))


def save(p):
    d = PROJECTS / p["id"]
    tmp = d / "project.json.tmp"
    tmp.write_text(media.dump(p), encoding="utf-8")
    tmp.replace(d / "project.json")


def view(p):
    """Projeto + dados derivados (trechos, legendas, inserções posicionadas)."""
    out = dict(p)
    if p.get("status") == "ready":
        out["computed"] = timeline.compute(p)
    return out


def update(pid, fn):
    with lock(pid):
        p = load(pid)
        fn(p)
        p["updated"] = time.time()
        save(p)
        return p


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


# ---------------------------------------------------------------- projetos

@app.get("/api/status")
def status():
    return {"ai": ai.available(), "model": ai.MODEL, "whisper": transcribe.MODEL_SIZE}


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


@app.post("/api/projects")
async def create_project(file: UploadFile = File(...), language: str = Form("pt"),
                         auto_ai: bool = Form(True)):
    pid = uuid.uuid4().hex[:10]
    d = PROJECTS / pid
    (d / "assets").mkdir(parents=True)
    (d / "exports").mkdir()
    ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    src = d / f"source{ext}"
    with src.open("wb") as fh:
        shutil.copyfileobj(file.file, fh, length=8 * 1024 * 1024)
    info = media.probe(src)
    if not info["has_video"]:
        shutil.rmtree(d)
        raise HTTPException(400, "Não encontrei vídeo nesse arquivo.")
    p = {
        "id": pid,
        "name": Path(file.filename or "Vídeo").stem,
        "created": time.time(),
        "updated": time.time(),
        "status": "processing",
        "language": language,
        "source": {"file": src.name, **info},
        "words": [],
        "deleted": [],
        "overlays": [],
        "suggestions": [],
        "ai_cuts": [],
        "settings": dict(timeline.DEFAULT_SETTINGS),
    }
    save(p)
    media.thumbnail(src, d / "thumb.jpg", at=min(1.0, info["duration"] / 2))

    def pipeline(progress):
        progress(0.02, "Extraindo áudio…")
        wav = d / "audio.wav"
        if info["has_audio"]:
            media.extract_audio(src, wav)
            (d / "waveform.json").write_text(json.dumps(media.waveform_peaks(wav)))
            progress(0.05, "Transcrevendo a fala (Whisper, no seu Mac)…")
            words = transcribe.transcribe(
                wav, language, on_progress=lambda x: progress(0.05 + x * 0.8))
        else:
            words = []
        fillers = [w["i"] for w in words if timeline.is_filler(w["w"])]

        def done(pp):
            pp["words"] = words
            pp["deleted"] = fillers
            pp["status"] = "ready"
        update(pid, done)

        if auto_ai and ai.available() and words:
            progress(0.88, "Claude está revisando os erros de gravação…")
            try:
                _apply_ai_clean(pid)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                progress(0.99, f"Limpeza com IA falhou: {e}")
        return {"words": len(words)}

    job = start_job(pid, "process", pipeline)
    update(pid, lambda pp: pp.__setitem__("job", job["id"]))
    return {"project": view(load(pid)), "job": job}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return view(load(pid))


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: dict):
    allowed = {"deleted", "overlays", "settings", "name", "suggestions"}

    def apply(p):
        for k, v in body.items():
            if k not in allowed:
                continue
            if k == "settings":
                p["settings"] = {**p.get("settings", {}), **v}
            elif k == "deleted":
                p["deleted"] = sorted(set(int(i) for i in v))
            else:
                p[k] = v
    return view(update(pid, apply))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    shutil.rmtree(pdir(pid))
    return {"ok": True}


@app.post("/api/projects/{pid}/assets")
async def upload_asset(pid: str, file: UploadFile = File(...)):
    d = pdir(pid) / "assets"
    name = re.sub(r"[^\w.\-]", "_", Path(file.filename or "arquivo").name)
    name = f"{uuid.uuid4().hex[:6]}_{name}"
    with (d / name).open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    kind = media.kind_of(name)
    if kind == "unknown":
        (d / name).unlink()
        raise HTTPException(400, "Formato não suportado. Use imagem, vídeo ou áudio.")
    return {"file": name, "kind": kind}


@app.post("/api/projects/{pid}/autocut")
def autocut(pid: str, body: dict):
    """Corta hesitações e ajusta o limite de pausa."""
    def apply(p):
        p["settings"] = {**p.get("settings", {}), **(body.get("settings") or {})}
        fillers = {w["i"] for w in p["words"] if timeline.is_filler(w["w"])}
        p["deleted"] = sorted(set(p["deleted"]) | fillers)
    return view(update(pid, apply))


# ---------------------------------------------------------------- IA

def _apply_ai_clean(pid):
    p = load(pid)
    cuts = ai.clean(p["words"], p["deleted"])

    def apply(pp):
        dl = set(pp["deleted"])
        for c in cuts:
            dl.update(range(c["start"], c["end"] + 1))
        pp["deleted"] = sorted(dl)
        pp["ai_cuts"] = cuts
    update(pid, apply)
    return cuts


@app.post("/api/projects/{pid}/ai/clean")
def ai_clean(pid: str):
    pdir(pid)
    if not ai.available():
        raise HTTPException(400, "IA desligada: coloque ANTHROPIC_API_KEY no arquivo .env e reinicie.")
    return start_job(pid, "ai_clean", lambda progress: {"cuts": _apply_ai_clean(pid)})


@app.post("/api/projects/{pid}/ai/suggest")
def ai_suggest(pid: str):
    pdir(pid)
    if not ai.available():
        raise HTTPException(400, "IA desligada: coloque ANTHROPIC_API_KEY no arquivo .env e reinicie.")

    def run(progress):
        p = load(pid)
        comp = timeline.compute(p)
        items = ai.suggest(p["words"], p["deleted"], comp["duration"])

        def apply(pp):
            new_overlays = []
            sugg = []
            for it in items:
                if it["kind"] == "text":
                    new_overlays.append({"id": uuid.uuid4().hex[:8], "type": "text",
                                         "text": it["text"], "w0": it["w0"], "w1": it["w1"],
                                         "ai": True})
                else:
                    sugg.append({"id": uuid.uuid4().hex[:8], **it})
            # substitui títulos sugeridos anteriormente pela IA; mantém os do usuário
            pp["overlays"] = [o for o in pp.get("overlays", []) if not o.get("ai")] + new_overlays
            pp["suggestions"] = sugg
        update(pid, apply)
        return {"items": items}
    return start_job(pid, "ai_suggest", run)


# ---------------------------------------------------------------- exportação

@app.post("/api/projects/{pid}/render")
def do_render(pid: str):
    d = pdir(pid)

    def run(progress):
        p = load(pid)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^\w\-]", "_", p["name"])[:40] or "video"
        out = d / "exports" / f"{safe}-{stamp}.mp4"
        progress(0.01, "Renderizando…")
        render.render(p, d, out, on_progress=lambda x: progress(x, "Renderizando…"))
        return {"file": out.name, "url": f"/media/{pid}/exports/{out.name}"}
    return start_job(pid, "render", run)


@app.get("/api/projects/{pid}/exports")
def list_exports(pid: str):
    d = pdir(pid) / "exports"
    files = sorted(d.glob("*.mp4"), key=lambda f: -f.stat().st_mtime)
    return [{"file": f.name, "url": f"/media/{pid}/exports/{f.name}",
             "size": f.stat().st_size} for f in files]


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


app.mount("/", StaticFiles(directory=ROOT / "app" / "static", html=True), name="static")

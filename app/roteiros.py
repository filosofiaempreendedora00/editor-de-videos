"""ROTEIROS: criação de roteiros + a "inteligência" do roteirista + organização dos vídeos por código de ID.

Tudo em arquivos JSON na pasta `roteiros/` (FORA do git — o repositório é público e roteiro é conteúdo do usuário):
  roteiros/roteiros.json      lista de vídeos/roteiros, cada um com um código (V001, V002…) que acompanha o vídeo
                               da ideia à publicação: ideia → roteiro → gravado → editado → publicado
  roteiros/inteligencia.json  o "cérebro": seções de conhecimento (público, tom de voz, estruturas, regras…) e uma
                               caixa de entrada de ensinamentos crus que o usuário vai mandando
  roteiros/drive.json         a pasta do Google Drive onde os vídeos ficam organizados pelos códigos
"""
import json
import re
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "roteiros"
DB = DIR / "roteiros.json"
BRAIN = DIR / "inteligencia.json"
DRIVE = DIR / "drive.json"
_lock = threading.Lock()

STATUS = ["ideia", "roteiro", "gravado", "editado", "publicado"]
PREFIX = "V"

# esqueleto inicial do cérebro: o usuário (e o Claude Code) vão preenchendo
DEFAULT_SECTIONS = [
    ("publico", "Público e avatar", "Para quem são os vídeos: quem é, o que quer, o que teme, como fala."),
    ("tom", "Tom de voz", "Como você fala: palavras que usa, palavras que evita, ritmo, humor, nível de formalidade."),
    ("ganchos", "Ganchos (hooks)", "Modelos de abertura que prendem nos 3 primeiros segundos."),
    ("estruturas", "Estruturas de roteiro", "Esqueletos que funcionam (ex.: gancho → problema → virada → prova → CTA)."),
    ("ctas", "Chamadas para ação", "Como você fecha os vídeos e o que pede para a pessoa fazer."),
    ("regras", "Regras e proibições", "O que nunca pode aparecer num roteiro seu."),
    ("exemplos", "Roteiros que funcionaram", "Vídeos seus (ou de referência) que performaram — e por quê."),
]


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, data):
    DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ roteiros (com código de ID)
def load():
    return _read(DB, [])


def _num(code):
    m = re.match(rf"^{PREFIX}(\d+)$", code or "")
    return int(m.group(1)) if m else 0


def next_code(items=None):
    items = load() if items is None else items
    return f"{PREFIX}{max([_num(r['code']) for r in items] + [0]) + 1:03d}"


def add(data=None):
    data = data or {}
    with _lock:
        items = load()
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        r = {"code": next_code(items), "title": (data.get("title") or "").strip() or "Sem título",
             "status": data.get("status") if data.get("status") in STATUS else "ideia",
             "hook": data.get("hook", ""), "body": data.get("body", ""), "cta": data.get("cta", ""),
             "notes": data.get("notes", ""), "tags": data.get("tags") or [],
             "project": data.get("project"), "drive": data.get("drive", ""),
             "created": now, "updated": now}
        items.append(r)
        _write(DB, items)
        return r


EDITABLE = {"title", "status", "hook", "body", "cta", "notes", "tags", "project", "drive"}


def edit(code, changes):
    with _lock:
        items = load()
        r = next((x for x in items if x["code"] == code), None)
        if not r:
            raise KeyError(code)
        for k, v in changes.items():
            if k in EDITABLE and not (k == "status" and v not in STATUS):
                r[k] = v
        r["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write(DB, items)
        return r


def remove(code):
    with _lock:
        items = load()
        if not any(x["code"] == code for x in items):
            raise KeyError(code)
        _write(DB, [x for x in items if x["code"] != code])


# ------------------------------------------------------------------ inteligência (o cérebro do roteirista)
def brain():
    b = _read(BRAIN, None)
    if b is None:
        b = {"sections": [{"id": i, "title": t, "hint": h, "body": ""} for i, t, h in DEFAULT_SECTIONS], "inbox": []}
        _write(BRAIN, b)
    return b


def brain_edit(section_id, body=None, title=None):
    with _lock:
        b = brain()
        s = next((x for x in b["sections"] if x["id"] == section_id), None)
        if not s:
            s = {"id": section_id, "title": title or section_id, "hint": "", "body": ""}
            b["sections"].append(s)
        if body is not None:
            s["body"] = body
        if title:
            s["title"] = title
        _write(BRAIN, b)
        return b


def brain_add_section(title):
    sid = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:30] or uuid.uuid4().hex[:6]
    return brain_edit(sid, body="", title=title.strip())


def brain_remove_section(section_id):
    with _lock:
        b = brain()
        b["sections"] = [x for x in b["sections"] if x["id"] != section_id]
        _write(BRAIN, b)
        return b


def teach(text):
    """Ensinamento cru (caixa de entrada): o usuário manda, o Claude Code organiza nas seções depois."""
    with _lock:
        b = brain()
        b["inbox"].append({"id": uuid.uuid4().hex[:8], "text": text.strip(),
                           "added": time.strftime("%Y-%m-%dT%H:%M:%S"), "done": False})
        _write(BRAIN, b)
        return b


def inbox_edit(item_id, done=None, delete=False):
    with _lock:
        b = brain()
        if delete:
            b["inbox"] = [x for x in b["inbox"] if x["id"] != item_id]
        else:
            for x in b["inbox"]:
                if x["id"] == item_id and done is not None:
                    x["done"] = bool(done)
        _write(BRAIN, b)
        return b


def brain_markdown():
    """O cérebro inteiro em texto (para o Claude Code ler antes de escrever um roteiro)."""
    b = brain()
    out = ["# Inteligência de roteiros", ""]
    for s in b["sections"]:
        out += [f"## {s['title']}", s["body"].strip() or "_(vazio)_", ""]
    pend = [x for x in b["inbox"] if not x["done"]]
    if pend:
        out += ["## Caixa de entrada (ainda não organizado)"] + [f"- {x['text']}" for x in pend] + [""]
    return "\n".join(out)


# ------------------------------------------------------------------ Google Drive
def drive():
    return _read(DRIVE, {"url": "", "folder_id": "", "local_path": ""})


def set_drive(url=None, local_path=None):
    d = drive()
    if url is not None:
        d["url"] = url.strip()
        m = re.search(r"/folders/([\w-]+)", d["url"])
        d["folder_id"] = m.group(1) if m else ""
    if local_path is not None:
        d["local_path"] = local_path.strip()
    _write(DRIVE, d)
    return status_drive(d)


def find_local_drive():
    """Pasta do "Google Drive para computador", se estiver instalado (é por ela que os vídeos são organizados)."""
    base = Path.home() / "Library" / "CloudStorage"
    return [str(p) for p in base.glob("GoogleDrive-*")] if base.exists() else []


def status_drive(d=None):
    d = d or drive()
    local = d.get("local_path") and Path(d["local_path"]).exists()
    return {**d, "local_ok": bool(local), "candidates": find_local_drive()}

"""Leitura/gravação dos projetos (usado pelo servidor e pela linha de comando)."""
import json
import re
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)
_locks = {}


class NotFound(Exception):
    pass


def pdir(pid):
    if not re.fullmatch(r"[a-z0-9]{6,16}", pid or "") or not (PROJECTS / pid / "project.json").exists():
        try:
            from fastapi import HTTPException
            raise HTTPException(404, "projeto não encontrado")
        except ImportError:
            raise NotFound(pid)
    return PROJECTS / pid


def lock(pid):
    return _locks.setdefault(pid, threading.RLock())


def load(pid):
    return json.loads((pdir(pid) / "project.json").read_text(encoding="utf-8"))


def save(p):
    d = PROJECTS / p["id"]
    tmp = d / "project.json.tmp"
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / "project.json")


def update(pid, fn):
    with lock(pid):
        p = load(pid)
        fn(p)
        p["updated"] = time.time()
        save(p)
        return p

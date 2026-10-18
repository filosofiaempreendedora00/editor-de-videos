"""Backup PRIVADO no GitHub (repo filosofiaempreendedora00/editor-de-videos-privado).

O repositório do editor é PÚBLICO, então o que é dele (roteiros, padrão de tom, comentários, decisões de edição dos
projetos, formatos, vocabulário) fica fora dele — e vem para cá, num clone em `.backup-privado/` (fora do git
público). Vídeos/áudios grandes NÃO entram (o GitHub não comporta; o bruto mora no Drive/Mac). Segredos também não
(`.env`, `roteiros/google.json`). Roda sozinho a cada 10 min com o servidor aberto (só commita se mudou) e com
`python -m app.cli backup`."""
import shutil
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / ".backup-privado"
REMOTE = "https://github.com/filosofiaempreendedora00/editor-de-videos-privado.git"
SECRETS = {"google.json"}
SMALL = 25 * 1024 * 1024          # nada acima de 25 MB


def _files():
    out = []
    for base in ("roteiros", "formatos"):
        for f in (ROOT / base).rglob("*"):
            if f.is_file() and f.name not in SECRETS and f.suffix.lower() in (".md", ".json", ".jsonl", ".txt") \
                    and f.stat().st_size < SMALL:
                out.append(f)
    for name in ("config.json", "vocabulario.txt"):
        if (ROOT / name).exists():
            out.append(ROOT / name)
    for d in (ROOT / "projects").glob("*"):
        for name in ("project.json", "plano.json", "grade.json", "para_claude_code.md"):
            if (d / name).exists():
                out.append(d / name)
    return out


def _git(*args, check=True):
    return subprocess.run(["git", "-C", str(DEST), *args], capture_output=True, text=True, check=check)


_lock = threading.Lock()


def run(push=True):
    with _lock:
        return _run(push)


def _run(push):
    if not (DEST / ".git").exists():
        DEST.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(DEST)], check=True)
        _git("remote", "add", "origin", REMOTE)
        (DEST / "README.md").write_text("# Backup privado do Editor de Vídeos\n\nGerado sozinho por `app/backup.py` "
                                        "(roteiros, padrão de tom, comentários, decisões de edição). Não edite aqui.\n")
    keep = set()
    for f in _files():
        rel = f.relative_to(ROOT)
        dst = DEST / rel
        keep.add(rel.as_posix())
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime or dst.stat().st_size != f.stat().st_size:
            shutil.copy2(f, dst)
    for base in ("roteiros", "formatos", "projects"):           # apagado no Mac → apagado no backup (histórico guarda)
        for f in (DEST / base).rglob("*") if (DEST / base).exists() else []:
            if f.is_file() and f.relative_to(DEST).as_posix() not in keep:
                f.unlink()
    _git("add", "-A")
    if not _git("status", "--porcelain").stdout.strip():
        return {"mudou": False}
    _git("-c", "user.name=Editor de Vídeos (backup)", "-c", "user.email=backup@local", "commit", "-qm",
         time.strftime("backup %Y-%m-%d %H:%M"))
    if push:
        r = _git("push", "-q", "-u", "origin", "main", check=False)
        if r.returncode:
            return {"mudou": True, "push": False, "erro": r.stderr.strip()[-300:]}
    return {"mudou": True, "push": push}


def start_loop(every=600):
    def loop():
        while True:
            try:
                run()
            except Exception as e:  # noqa: BLE001
                print("backup privado falhou:", e, flush=True)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True, name="backup-privado").start()

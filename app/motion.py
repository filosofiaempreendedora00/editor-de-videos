"""Renderiza os templates de motion (HTML/CSS) em sequências PNG transparentes,
controlando o Chrome via DevTools Protocol. Cada quadro é capturado num tempo
exato da animação, então o resultado é perfeitamente suave."""
import base64
import hashlib
import json
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

import httpx
from websockets.sync.client import connect

from .sources import chrome

MOTION_DIR = Path(__file__).resolve().parent / "motion"
TEMPLATES = sorted(p.stem for p in MOTION_DIR.glob("*.html"))
MAX_SECONDS = 12.0


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Browser:
    """Um Chrome invisível reaproveitado para renderizar vários motions."""

    def __init__(self):
        exe = chrome()
        if not exe:
            raise RuntimeError("Os motions precisam do Google Chrome instalado.")
        self.port = _free_port()
        self.profile = tempfile.mkdtemp(prefix="motion-chrome-")
        self.proc = subprocess.Popen(
            [exe, "--headless=new", f"--remote-debugging-port={self.port}", f"--user-data-dir={self.profile}",
             "--hide-scrollbars", "--mute-audio", "--no-first-run", "--disable-extensions",
             "--allow-file-access-from-files", "--force-color-profile=srgb", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = None
        for _ in range(100):
            try:
                pages = httpx.get(f"http://127.0.0.1:{self.port}/json/list", timeout=1).json()
                page = next(p for p in pages if p.get("type") == "page")
                url = page["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.1)
        if not url:
            self.close()
            raise RuntimeError("Não consegui iniciar o Chrome para renderizar motions.")
        self.ws = connect(url, max_size=None, open_timeout=10)
        self._id = 0

    def call(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv(timeout=60))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr, await_promise=False):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=await_promise, returnByValue=True)
        return r.get("result", {}).get("value")

    def render(self, url, width, height, seconds, fps, out_dir):
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        self.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        self.call("Page.navigate", url=url)
        for _ in range(100):
            if self.eval("document.readyState") == "complete" and self.eval("typeof window.__seek") == "function":
                break
            time.sleep(0.05)
        self.eval("window.__ready()", await_promise=True)
        frames = max(1, int(round(seconds * fps)))
        for k in range(frames):
            self.eval(f"window.__seek({k / fps:.4f})")
            shot = self.call("Page.captureScreenshot", format="png", fromSurface=True,
                             captureBeyondViewport=False)
            (out_dir / f"{k:05d}.png").write_bytes(base64.b64decode(shot["data"]))
        return frames

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def template_url(template, params):
    if template not in TEMPLATES:
        raise ValueError(f"template de motion desconhecido: {template}")
    return (MOTION_DIR / f"{template}.html").as_uri() + "#" + urllib.parse.quote(json.dumps(params, ensure_ascii=False))


def ensure(jobs, cache_dir, on_progress=None):
    """jobs = [{template, params, width, height, seconds, fps}] -> lista de pastas com PNGs.
    Usa cache: o mesmo motion não é renderizado duas vezes."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    results, todo = [], []
    for j in jobs:
        j = {**j, "seconds": min(MAX_SECONDS, max(0.5, float(j["seconds"])))}
        key = hashlib.sha1(json.dumps(j, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        d = cache_dir / key
        results.append(d)
        if not (d / "done").exists():
            todo.append((j, d))
    if todo:
        browser = Browser()
        try:
            for n, (j, d) in enumerate(todo):
                if d.exists():
                    shutil.rmtree(d)
                d.mkdir(parents=True)
                browser.render(template_url(j["template"], j["params"]), j["width"], j["height"],
                               j["seconds"], j["fps"], d)
                (d / "done").write_text("ok")
                if on_progress:
                    on_progress((n + 1) / len(todo))
        finally:
            browser.close()
    return results

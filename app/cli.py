"""Linha de comando do editor — pensada para o Claude Code operar a ferramenta
com pedidos em português ("corta as pausas e coloca legenda no projeto X").

  .venv/bin/python -m app.cli projetos
  .venv/bin/python -m app.cli ver <id>                 # resumo + transcrição com índices + inserções
  .venv/bin/python -m app.cli plano <id> [regras|ollama|claude_api]
  .venv/bin/python -m app.cli pedido-claude-code <id>  # gera projects/<id>/para_claude_code.md
  .venv/bin/python -m app.cli aplicar-plano <id> [arquivo.json]
  .venv/bin/python -m app.cli cortar <id> <i0> <i1>    # corta palavras i0..i1
  .venv/bin/python -m app.cli restaurar <id> <i0> <i1>
  .venv/bin/python -m app.cli inserir <id> '<json da inserção>'
  .venv/bin/python -m app.cli remover <id> <overlay_id>
  .venv/bin/python -m app.cli config <id> chave=valor [...]
  .venv/bin/python -m app.cli buscar <fonte> "<busca>"
  .venv/bin/python -m app.cli preencher <id>           # busca materiais para os B-rolls pendentes
  .venv/bin/python -m app.cli formatos
  .venv/bin/python -m app.cli usar-formato <id> <slug>
  .venv/bin/python -m app.cli exportar <id>
  .venv/bin/python -m app.cli amostra <id> [segundos]   # prévia rápida (meia resolução) do começo
  .venv/bin/python -m app.cli quadros <id> [arquivo.mp4] # folha de quadros da última exportação (para revisar)
  .venv/bin/python -m app.cli formato-notas <slug> "<observações de estilo>"
  .venv/bin/python -m app.cli texto <id> <i0> <i1> "<texto correto>"   # corrige a transcrição/legenda
  .venv/bin/python -m app.cli trecho <id> <ini_s> <fim_s> cortar|restaurar  # corte/restauração por TEMPO
  .venv/bin/python -m app.cli retranscrever <id>                      # motor novo + silêncios + plano
  .venv/bin/python -m app.cli vocabulario [termo ...]                 # mostra/adiciona termos (nomes, marcas)
"""
import json
import sys
import time
from pathlib import Path

from . import brain, plan, reference, render, sources, timeline
from .ai_text import transcript_for_ai
from .server import _load_env  # noqa: F401  (carrega o .env)
from .store import PROJECTS, load, pdir, update


def out(x):
    print(json.dumps(x, ensure_ascii=False, indent=1) if not isinstance(x, str) else x)


def cmd_projetos():
    for d in sorted(PROJECTS.iterdir(), key=lambda d: -d.stat().st_mtime):
        f = d / "project.json"
        if f.exists():
            p = json.loads(f.read_text(encoding="utf-8"))
            print(f"{p['id']}  {p['status']:<10}  {p['source']['duration']:>6.1f}s  {p['name']}")


def cmd_ver(pid):
    p = load(pid)
    c = timeline.compute(p)
    print(f"# {p['name']} ({pid}) — bruto {p['source']['duration']:.1f}s -> final {c['duration']:.1f}s, "
          f"{len(c['cuts'])} trechos, formato {c['settings']['format']}, formato-ref {p.get('formato')}")
    print("\n## Configurações\n" + json.dumps(c["settings"], ensure_ascii=False))
    print("\n## Transcrição mantida ([índice]palavra)\n" + transcript_for_ai(p["words"], p["deleted"]))
    print("\n## Inserções")
    for o in sorted(c["overlays"], key=lambda o: o["a"]):
        desc = o.get("text") or o.get("sfx") or o.get("template") or o.get("file") or o.get("query") or ""
        print(f"- {o['id']} {o['type']:<11} {o['a']:6.2f}-{o['b']:6.2f}s  w{o['w0']}-{o.get('w1')}  {desc}")


def cmd_plano(pid, engine="regras"):
    p = load(pid)
    fmt = reference.load(p["formato"]) if p.get("formato") else None
    result = brain.plan(engine, p["words"], p["deleted"], p["source"]["duration"], formato=fmt,
                        project_dir=pdir(pid))
    update(pid, lambda pp: plan.apply(pp, result, engine))
    print(f"Plano aplicado: {len(result['cuts'])} cortes, {len(result['items'])} inserções.")


def cmd_pedido_claude_code(pid):
    p = load(pid)
    fmt = reference.load(p["formato"]) if p.get("formato") else None
    print(brain.write_claude_code_brief(p, pdir(pid), fmt))


def cmd_aplicar_plano(pid, arquivo=None):
    if arquivo:
        Path(pdir(pid) / "plano.json").write_text(Path(arquivo).read_text(encoding="utf-8"), encoding="utf-8")
    result = brain.read_claude_code_plan(pdir(pid), len(load(pid)["words"]))
    update(pid, lambda pp: plan.apply(pp, result, "claude_code"))
    print(f"Plano do Claude Code aplicado: {len(result['cuts'])} cortes, {len(result['items'])} inserções.")


def cmd_cortar(pid, a, b, restore=False):
    a, b = int(a), int(b)

    def f(p):
        d = set(p["deleted"])
        for i in range(a, b + 1):
            d.discard(i) if restore else d.add(i)
        p["deleted"] = sorted(d)
    update(pid, f)
    print(("Restaurado" if restore else "Cortado") + f": palavras {a}-{b}")


def cmd_inserir(pid, js):
    o = json.loads(js)
    o.setdefault("id", plan.new_id())
    o.setdefault("w1", o.get("w0"))
    update(pid, lambda p: p.setdefault("overlays", []).append(o))
    print(f"Inserção {o['id']} adicionada.")


def cmd_remover(pid, oid):
    update(pid, lambda p: p.__setitem__("overlays", [o for o in p["overlays"] if o.get("id") != oid]))
    print(f"Removida {oid}.")


def cmd_config(pid, *pairs):
    def parse(v):
        try:
            return json.loads(v)
        except ValueError:
            return v
    kv = {k: parse(v) for k, v in (x.split("=", 1) for x in pairs)}
    update(pid, lambda p: p.__setitem__("settings", {**p.get("settings", {}), **kv}))
    print("Configurações:", kv)


def cmd_buscar(fonte, q):
    for r in sources.search(fonte, q):
        print(f"- [{r['kind']}] {r['title'][:90]}  ({r.get('license', '')})  {r.get('page_url', '')}")


def cmd_preencher(pid):
    p = load(pid)
    res = plan.autofill(p, pdir(pid) / "assets", on_progress=lambda x, m=None: print(m or ""))
    update(pid, lambda q: q.update(overlays=p["overlays"], credits=p.get("credits", [])))
    out(res)


def cmd_formatos():
    for f in reference.list_all():
        print(f"{f['slug']}: {f['name']} — {len(f.get('refs', []))} referência(s)\n  {f.get('brief', '')[:300]}")


def cmd_usar_formato(pid, slug):
    fmt = reference.load(slug)
    update(pid, lambda p: (p.__setitem__("formato", slug),
                           p.__setitem__("settings", {**p["settings"], **(fmt or {}).get("settings", {})})))
    print(f"Formato {slug} aplicado.")


def cmd_exportar(pid):
    p = load(pid)
    d = pdir(pid)
    out_path = d / "exports" / f"{p['name'][:40]}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    render.render(p, d, out_path, on_progress=lambda x, m=None: print(f"\r{m or ''} {x * 100:5.1f}%", end=""))
    print(f"\nPronto: {out_path}")


def cmd_amostra(pid, segundos="15"):
    p = load(pid)
    d = pdir(pid)
    out_path = d / "exports" / f"amostra-{time.strftime('%H%M%S')}.mp4"
    render.render(p, d, out_path, limit=float(segundos), scale=0.5,
                  on_progress=lambda x, m=None: print(f"\r{m or ''} {x * 100:5.1f}%", end=""))
    print(f"\nAmostra: {out_path}")
    cmd_quadros(pid, str(out_path))


def cmd_quadros(pid, arquivo=None):
    import subprocess
    from .media import FFMPEG, probe
    d = pdir(pid)
    v = Path(arquivo) if arquivo else max((d / "exports").glob("*.mp4"), key=lambda f: f.stat().st_mtime)
    dur = probe(v)["duration"] or 1
    out_img = v.with_suffix(".quadros.jpg")
    n = 12
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(v), "-vf",
                    f"fps={n / dur:.4f},scale=320:-2,drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:"
                    f"text='%{{pts\\:hms}}':x=6:y=6:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.6,tile=4x3:padding=4",
                    "-frames:v", "1", str(out_img)])
    print(f"Folha de quadros: {out_img}")


def cmd_formato_notas(slug, notas):
    fmt = reference.load(slug)
    fmt["notes"] = notas
    reference.save(fmt)
    reference.rebuild(slug)
    print("Observações salvas no formato", slug)


def cmd_texto(pid, a, b, text):
    from .transcribe import replace_text
    update(pid, lambda p: replace_text(p["words"], int(a), int(b), text))
    print(f"Texto das palavras {a}-{b} agora: {text}")


def cmd_vocabulario(*terms):
    from . import transcribe
    if terms:
        print("Adicionados:", transcribe.add_vocabulary(list(terms)))
    print(", ".join(transcribe.vocabulary()) or "(vazio)")


def cmd_trecho(pid, a, b, modo="cortar"):
    mode = "keep" if modo.startswith("rest") else "cut"
    a, b = sorted((float(a), float(b)))

    def f(p):
        p.setdefault("manual", []).append({"a": a, "b": b, "mode": mode})
        d = set(p["deleted"])
        for w in p["words"]:
            if a <= (w["start"] + w["end"]) / 2 <= b:
                (d.discard if mode == "keep" else d.add)(w["i"])
        p["deleted"] = sorted(d)
    update(pid, f)
    print(("Restaurado" if mode == "keep" else "Cortado") + f": {a:.2f}s–{b:.2f}s")


def cmd_retranscrever(pid):
    from . import transcribe
    d = pdir(pid)
    words = transcribe.transcribe(d / "audio.wav", load(pid).get("language") or "pt")
    sil = transcribe.silences(d / "audio.wav")
    update(pid, lambda p: p.update(words=words, silences=sil, deleted=[], overlays=[], ai_cuts=[], manual=[]))
    cmd_plano(pid, "regras")


def cmd_refs(busca=""):
    from . import refs
    q = busca.lower().lstrip("@#")
    for r in sorted(refs.load(), key=lambda r: r["added"], reverse=True):
        txt = " ".join([r["url"], r.get("handle") or "", r.get("note", ""), *r.get("tags", [])]).lower()
        if q and q not in txt:
            continue
        who = f" @{r['handle']}" if r.get("handle") else ""
        tags = " ".join("#" + t for t in r.get("tags", []))
        print(f"[{r['id']}] {r['kind']}{who} — {r['url']}  {r.get('note', '')} {tags}".rstrip())


def cmd_ref_add(texto, nota="", etiquetas=""):
    from . import refs
    res = refs.add(texto, nota, etiquetas)
    print(f"{len(res['added'])} salva(s), {len(res['updated'])} atualizada(s) em referencias/links.json")
    refs.wait_sync()
    st = refs.sync_status()
    print("GitHub: " + ("enviado" if st["state"] == "ok" else f"não enviado ({st['msg']})"))


def cmd_fundo(pid, cena="biblioteca"):
    """Troca o fundo: biblioteca | gabinete | biblioteca_escura | none | file:<arquivo em assets>."""
    from . import background
    update(pid, lambda p: p["settings"].__setitem__("bg_scene", cena))
    if cena == "none":
        print("Fundo original.")
        return
    name = background.apply(load(pid), pdir(pid), on_progress=lambda x, m=None: print(f"\r{m or ''} {x * 100:5.1f}%", end=""))
    print(f"\nCenário '{cena}' aplicado (prévia: {name}).")


def cmd_tela_verde(pid, arquivo, w0=None, w1=None):
    """Tela verde com um print de assets/: sem w0/w1 acha sozinho o trecho em que você o lê."""
    from . import greenscreen
    from .plan import new_id
    p = load(pid)
    ov = None if w0 is not None else greenscreen.detect(p, pdir(pid), arquivo)
    if ov is None:
        if w0 is None:
            print("Não achei você lendo esse print. Passe o trecho: tela-verde <id> <arquivo> <w0> <w1>")
            return
        ov = {"type": "greenscreen", "file": arquivo, "w0": int(w0), "w1": int(w1 or w0), "corner": "bl", "size": 0.52}
    ov["id"] = new_id()
    update(pid, lambda pp: pp.setdefault("overlays", []).append(ov))
    print(f"Tela verde: palavras {ov['w0']}–{ov['w1']} ({ov.get('reason', 'trecho escolhido')})")


def cmd_roteiros(codigo=""):
    from . import roteiros
    for r in roteiros.load():
        if codigo and r["code"] != codigo:
            continue
        print(f"{r['code']}  [{r['status']:9}]  {r['title']}" + (f"  · projeto {r['project']}" if r.get("project") else ""))
        if codigo:
            for k in ("hook", "body", "cta", "notes"):
                if r.get(k):
                    print(f"\n--- {k} ---\n{r[k]}")


def cmd_roteiro_add(titulo, status="ideia"):
    from . import roteiros
    r = roteiros.add({"title": titulo, "status": status})
    print(f"Criado {r['code']}: {r['title']}")


def cmd_cerebro():
    from . import roteiros
    print(roteiros.brain_markdown())


COMMANDS = {
    "roteiros": cmd_roteiros, "roteiro-add": cmd_roteiro_add, "cerebro": cmd_cerebro,
    "tela-verde": cmd_tela_verde,
    "fundo": cmd_fundo,
    "refs": cmd_refs, "ref-add": cmd_ref_add,
    "trecho": cmd_trecho, "retranscrever": cmd_retranscrever,
    "texto": cmd_texto, "vocabulario": cmd_vocabulario,
    "amostra": cmd_amostra, "quadros": cmd_quadros, "formato-notas": cmd_formato_notas,
    "projetos": cmd_projetos, "ver": cmd_ver, "plano": cmd_plano, "pedido-claude-code": cmd_pedido_claude_code,
    "aplicar-plano": cmd_aplicar_plano, "cortar": cmd_cortar,
    "restaurar": lambda pid, a, b: cmd_cortar(pid, a, b, restore=True),
    "inserir": cmd_inserir, "remover": cmd_remover, "config": cmd_config, "buscar": cmd_buscar,
    "preencher": cmd_preencher, "formatos": cmd_formatos, "usar-formato": cmd_usar_formato,
    "exportar": cmd_exportar,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](*sys.argv[2:])

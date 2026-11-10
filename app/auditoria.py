"""AUDITORIA DE PRIMEIRA ENTREGA (03/11, pedido dele: "maximizar as chances de que eu te envie um arquivo de vídeo e
ele já venha perfeitamente pronto"). Confere no vídeo CALCULADO (timeline.compute) as regras mensuráveis que ele mais
cobrou nas observações de 18/10–03/11 — o que é gosto fica na skill editar-video §-0; o que dá para medir fica aqui.

Cada achado: (nível, tempo no vídeo final em s, tema, mensagem). Nível "✗" = ele já reprovou isso; "⚠" = confira.
Roda sozinha no fim do `aplicar-edicao` e com `auditar <pid>`.
"""
import json
import re
import subprocess
from pathlib import Path

from . import timeline
from .media import FFMPEG, probe

VIDEO = (".mp4", ".mov", ".webm", ".m4v")
SEM_ROSTO = {"full", "viral", "motion"}          # cenas que cobrem a tela inteira (ele some)
# motions que voam POR CIMA dele, com o rosto à vista (V020 10/11: o aviãozinho do CTA contava como 'troca de cena')
SOBRE_ELE = {"aviaozinho", "emoji3d", "emojifun", "paleta"}
GAP_HOOK = 3.6       # s (vídeo final): no gancho, nada parado ~4 s (V018: as moedas ~4 s sozinhas foram cobradas)
GAP_CORPO = 7.0      # s: nunca mais de ~5–7 s só ele falando sem nada visual
ATIVO_MAX = 6.5      # s: um mesmo ativo parado na tela ("durou muito tempo esse b-roll")
SOM_ANTES, SOM_DEPOIS = 0.3, 0.6   # s: janela em que o som do "brotar" tem que cair
VENTO = re.compile(r"whoosh|swoosh|riser|vento|wind", re.I)


def _zoom(segs, t):
    for s in segs:
        if s["out"] <= t < s["out"] + s["end"] - s["start"]:
            k = (t - s["out"]) / max(0.01, s["end"] - s["start"])
            return round(float(s.get("zoom", 1)) * (s.get("kb0", 1) + (s.get("kb1", 1) - s.get("kb0", 1)) * k), 1)
    return 1.0


def _cena(ovs, t, segs=None):
    """Tipo de cena no instante t (tempo de compute): o ativo que entrou por último, ou 'solo' (com o número gigante
    atrás e o enquadramento — o pós-gancho ABERTO depois do gancho fechado é troca de formato)."""
    act = [o for o in ovs if o["type"] in ("media", "motion", "greenscreen") and o["a"] <= t < o["b"]
           and not (o["type"] == "motion" and o.get("template") in SOBRE_ELE)]
    if not act:
        num = any(o["type"] == "behind" and o.get("big") and o["a"] <= t < o["b"] for o in ovs)
        return "solo", ("num" if num else "") + (f"z{_zoom(segs, t)}" if segs else "")
    o = max(act, key=lambda x: x["a"])
    if o["type"] == "greenscreen":
        return "gs", o.get("file")
    if o["type"] == "motion":
        return ("meio" if o.get("layout") == "meio" else "motion"), o.get("template")
    return o.get("layout", "full"), f'{o.get("file")}@{o.get("clip_start") or 0}' 


def _barras(path, cache):
    """Faixas pretas DENTRO do arquivo (YouTube com degradê nas bordas — V015 02/11): cropdetect em 2 s."""
    key = f"{path.name}:{int(path.stat().st_mtime)}"
    if key in cache:
        return cache[key]
    res = None
    try:
        info = probe(path)
        W_, H_, D_ = info["width"], info["height"], float(info.get("duration") or 3)
        achou = []
        for ss in (min(1.0, D_ * 0.2), max(0.0, D_ * 0.6)):
            r = subprocess.run([FFMPEG, "-hide_banner", "-ss", f"{ss:.2f}", "-i", str(path), "-t", "1", "-vf",
                                "cropdetect=limit=16:round=2:reset=0", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
            m = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
            if m:
                achou.append((int(m[-1][0]), int(m[-1][1])))
        if len(achou) == 2 and W_:
            w, h = min(a[0] for a in achou), min(a[1] for a in achou)
            iguais = abs(achou[0][0] - achou[1][0]) <= 8 and abs(achou[0][1] - achou[1][1]) <= 8
            if iguais and w * h >= 0.6 * W_ * H_ and (w < W_ * 0.96 or h < H_ * 0.96):
                res = f"{W_}x{H_} → conteúdo {w}x{h}"
    except Exception:  # noqa: BLE001
        res = None
    cache[key] = res
    return res


def auditar(pid, projects_dir="projects"):
    pdir = Path(projects_dir) / pid
    p = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    c = timeline.compute(p)
    sp = float(c["settings"].get("speed") or 1.0)
    out = lambda t: t / sp                                  # noqa: E731  (tempo do vídeo final)
    ovs = c["overlays"]
    segs = c["segments"]
    dur = c["duration"]
    achados = []

    def add(nivel, t, tema, msg):
        achados.append((nivel, round(out(t), 1), tema, msg))

    vis = [o for o in ovs if o["type"] in ("media", "motion", "greenscreen", "emphasis", "text", "calor", "zoom")
           or (o["type"] == "behind" and o.get("big"))]
    # eventos visuais = começo de cada elemento + cada item interno de motion (um motion que muda conta como evento)
    ev = sorted({round(o["a"], 2) for o in vis} | {round(o["a"] + float(it.get("t", 0)), 2) for o in ovs
                 if o["type"] in ("motion", "media") for it in ((o.get("params") or (o.get("motion") or {}).get("params") or {})
                                                               .get("items") or []) if isinstance(it, dict) and "t" in it})
    for o in ovs:
        prm = o.get("params") or (o.get("motion") or {}).get("params") or {}
        for it in prm.get("items") or []:
            if isinstance(it, dict) and it.get("w") is not None and 0 <= int(it["w"]) < len(p["words"]):
                ev.append(round(timeline.to_output(segs, p["words"][int(it["w"])]["start"]), 2))
    ev = sorted(set(ev))
    trans = [o for o in ovs if o["type"] == "transition"]
    _cut = next((o["a"] for o in sorted(trans, key=lambda o: o["a"]) if o["a"] > 1.0), None)
    cut0 = lambda t: _cut is not None and abs(t - _cut) < 0.6  # noqa: E731
    fundo_muda = [o["a"] for o in ovs if o["type"] == "calor"] + ([c["segments"][0]["out"]] if p.get("source_orig") else [])
    muda_fundo = lambda t: any(abs(t - x) < 0.6 for x in fundo_muda) or (p.get("source_orig") and cut0(t))  # noqa: E731
    sfx = [o for o in ovs if o["type"] == "sfx"]

    # ---- GANCHO: termina na 1ª transição depois de 1 s (corte do pós-hook)
    cut = next((o["a"] for o in sorted(trans, key=lambda o: o["a"]) if o["a"] > 1.0), None)
    if cut:
        pts = [0.0] + [e for e in ev if 0 < e < cut] + [cut]
        gap = max((b - a, a) for a, b in zip(pts, pts[1:]))
        if out(gap[0]) > GAP_HOOK:
            add("✗", gap[1], "gancho", f"{out(gap[0]):.1f} s sem nada novo no gancho (energia desproporcional: troca a cada ~2 s)")
        sem = [t / 10 for t in range(0, int(cut * 10)) if _cena(ovs, t / 10, segs)[0] in SEM_ROSTO]
        if len(sem) > 0.5 * cut * 10:
            add("✗", sem[0], "gancho", "o gancho fica mais da metade SEM o seu rosto (rosto em 100% dos ganchos)")
        antes, depois = _cena(ovs, cut - 0.15, segs), _cena(ovs, cut + 0.25, segs)
        if (antes[0] == depois[0] and antes[0] != "solo" or antes == depois) and not muda_fundo(cut):
            add("✗", cut, "gancho", f"a transição do gancho mantém a mesma estrutura ({antes[0]} → {depois[0]})")

    # ---- MONOTONIA: tempo sem nenhum evento visual; ativo parado tempo demais
    pts = [cut or 0.0] + [e for e in ev if e > (cut or 0)] + [dur]
    for a, b in zip(pts, pts[1:]):
        if out(b - a) > GAP_CORPO:
            add("⚠", a, "ritmo", f"{out(b - a):.1f} s sem nada visual novo ('fiquei falando muito tempo sem nada dinâmico')")
    for o in ovs:
        if o["type"] == "media" and not o.get("motion") and out(o["b"] - o["a"]) > ATIVO_MAX:
            add("⚠", o["a"], "ritmo", f"{o.get('file')} fica {out(o['b'] - o['a']):.1f} s na tela ('durou muito tempo esse b-roll')")

    # ---- TRANSIÇÕES: só com troca de cena; nunca no 1º quadro
    for o in trans:
        if o["a"] < 0.3:
            add("✗", o["a"], "transição", "transição no começo do vídeo (a luz deixa a tela creme no 1º quadro)")
            continue
        antes, depois = _cena(ovs, o["a"] - 0.15, segs), _cena(ovs, o["a"] + 0.25, segs)
        if antes == depois and not muda_fundo(o["a"]):
            add("✗", o["a"], "transição", f"transição sem troca de cena ({antes[0]} → {depois[0]}): 'o antes e o depois não podem ser idênticos'")
    t, prev = 0.0, _cena(ovs, 0.0, segs)
    while t < dur:
        t += 0.1
        cur = _cena(ovs, t, segs)
        if cur[0] != prev[0] and cur[0] in SEM_ROSTO | {"solo"} and prev[0] in SEM_ROSTO | {"solo"}:
            perto = [x for x in trans + sfx if abs(x["a"] - t) < 0.35]
            if not perto:
                add("⚠", t, "transição", f"troca seca de cena ({prev[0]} → {cur[0]}) sem transição nem som")
        prev = cur

    # ---- SONS: tudo que BROTA tem som (com bolinha roxa); nada de vento; nada empilhado
    meds_ = [o for o in ovs if o["type"] in ("media", "motion")]
    for o in ovs:
        brota = o["type"] in ("motion", "greenscreen", "media") or (o["type"] == "behind" and o.get("big"))
        if not brota or o["a"] < 0.2:
            continue
        lay = o.get("layout", "full") if o["type"] == "media" else ("meio" if o.get("layout") == "meio" else "motion")
        troca = any(m is not o and abs(m["b"] - o["a"]) < 0.2 and (m.get("layout", "full") if m["type"] == "media" else "motion") == lay
                    for m in meds_)
        if troca and lay != "viral":
            continue                      # troca de ativo DENTRO da mesma cena (dividida → dividida): silenciosa por regra
        if not any(o["a"] - SOM_ANTES <= s["a"] <= o["a"] + SOM_DEPOIS for s in sfx):
            nome = o.get("file") or o.get("template") or o.get("text") or o["type"]
            add("⚠", o["a"], "som", f"{nome} entra sem som (clique/pop na hora em que brota)")
    for s in sfx:
        if VENTO.search(s.get("sfx", "")):
            add("⚠", s["a"], "som", f"som '{s['sfx']}' tem cara de vento/whoosh (reprovado no V018) — confira")
    ss = sorted(sfx, key=lambda s: s["a"])
    for s1, s2 in zip(ss, ss[1:]):
        longos = ("reverse_expectativa", "auto_", "coro", "datilografando", "riser")
        if any(str(x.get("sfx", "")).startswith(longos) for x in (s1, s2)):
            continue
        if s2["a"] - s1["a"] < 0.12 and s1.get("sfx") != s2.get("sfx"):
            add("⚠", s1["a"], "som", f"dois sons empilhados ({s1['sfx']} + {s2['sfx']})")

    # ---- LEGENDAS: toda palavra falada aparece (legenda comum, destaque ou motion que mostra o texto)
    dl = set(i for i, w in enumerate(p["words"]) if w.get("deleted")) | set(p.get("deleted") or [])
    tem = {w["i"] for cp in c["captions"] for w in cp.get("words", [])}
    for o in ovs:
        lay = o.get("layout") if isinstance(o.get("layout"), dict) else None
        if o["type"] == "emphasis" and lay:
            tem |= {w["i"] for ln in lay.get("lines", []) for w in ln.get("words", [])}
        if o.get("hide_captions") or o.get("hide_captions_meio") or (o.get("motion") or {}).get("hide_captions"):
            tem |= set(range(o.get("w0", 0), o.get("w1", -1) + 1))
    falta = []
    for s in c["segments"]:
        for i, w in enumerate(p["words"]):
            if i in dl or not w["w"].strip() or i in tem or w.get("bg"):
                continue
            if min(w["end"], s["end"]) - max(w["start"], s["start"]) >= 0.1:    # legenda inclui com ≥ 0,08 s (folga de 1 quadro)
                falta.append((s["out"] + max(0.0, w["start"] - s["start"]), w["w"]))
    for t0, w in falta:
        add("✗", t0, "legenda", f"palavra falada sem legenda: '{w}'")

    # ---- ATIVOS: plano curto (congela/vai e volta), faixas pretas no arquivo, fim sem rosto, fim repetido
    cache_f = pdir / ".auditoria_cache.json"
    try:
        cache = json.loads(cache_f.read_text())
    except Exception:  # noqa: BLE001
        cache = {}
    for o in ovs:
        f = o.get("file")
        if o["type"] != "media" or not f or not f.lower().endswith(VIDEO) or f.startswith("motion_"):
            continue
        fp = pdir / "assets" / f
        if not fp.exists():
            add("✗", o["a"], "ativo", f"{f} não existe em assets/")
            continue
        try:
            d = float(probe(fp).get("duration") or 0) - float(o.get("clip_start") or 0)
            if o.get("shot_end"):
                d = min(d, float(o["shot_end"]) - float(o.get("clip_start") or 0))
        except Exception:  # noqa: BLE001
            d = 0
        win = o["b"] - o["a"]
        if d > 0 and d < win * 0.6:
            add("✗", o["a"], "ativo", f"{f}: o plano tem {d:.1f} s para uma janela de {win:.1f} s (vai travar ou repetir)")
        bar = _barras(fp, cache)
        if bar:
            add("⚠", o["a"], "ativo", f"{f} tem faixas pretas no próprio arquivo ({bar}) — corte as bordas")
    try:
        cache_f.write_text(json.dumps(cache))
    except Exception:  # noqa: BLE001
        pass
    fim = _cena(ovs, dur - 0.4, segs)
    fim_meio = any(o.get("fim") for o in ovs if o["type"] == "media")
    if fim[0] in SEM_ROSTO and not fim_meio:
        add("⚠", dur - 0.4, "fim", f"o vídeo termina sem o seu rosto ({fim[0]})")
    meds = [o for o in sorted(ovs, key=lambda o: o["a"]) if o["type"] == "media" and o.get("file")]
    if meds and meds[-1]["a"] > dur - 8 and any(m.get("file") == meds[-1].get("file") for m in meds[:-1]) \
            and not meds[-1].get("callback"):
        add("⚠", meds[-1]["a"], "fim", f"o fim repete um ativo já mostrado ({meds[-1]['file']})")

    # ---- RECORTE: tudo que vai ATRÁS dele precisa do recorte de alta qualidade
    hq = p.get("mask_hq") or []
    for o in ovs:
        if (o["type"] == "behind" and o.get("big")) or (o["type"] == "calor" and o.get("image")):
            seg = next((s for s in c["segments"] if s["out"] <= o["a"] < s["out"] + s["end"] - s["start"]), None)
            if seg:
                t_src = seg["start"] + o["a"] - seg["out"]
                if not any(r[0] <= t_src <= r[1] for r in hq):
                    add("✗", o["a"], "recorte", "algo atrás de você sem o recorte de alta qualidade (coqueiro/parapeito aparecem)")

    # ---- ZOOM duplo
    zs = sorted([o for o in ovs if o["type"] == "zoom"], key=lambda o: o["a"])
    for z1, z2 in zip(zs, zs[1:]):
        if z2["a"] - z1["a"] < 1.2:
            add("⚠", z1["a"], "zoom", "dois zooms seguidos ('pareceu bugado')")

    # ---- MÚSICA
    mus = p.get("music") or []
    if not mus:
        add("⚠", 0, "música", "vídeo sem música")
    for m in mus:
        if m.get("vol") is not None and not (0.008 <= float(m["vol"]) <= 0.3):
            add("⚠", float(m.get("start") or 0), "música", f"volume da música fora do normal ({m['vol']})")

    achados.sort(key=lambda x: (x[0] != "✗", x[1]))
    return achados


def relatorio(pid, projects_dir="projects"):
    ach = auditar(pid, projects_dir)
    if not ach:
        return "✓ auditoria: nada do que ele já cobrou apareceu (gancho, ritmo, transições, sons, legendas, ativos, recorte)"
    fmt = lambda s: f"{int(s // 60)}:{s % 60:04.1f}"          # noqa: E731
    linhas = [f"{n} {fmt(t)} [{tema}] {msg}" for n, t, tema, msg in ach]
    nx = sum(1 for a in ach if a[0] == "✗")
    return f"auditoria: {nx} reprovado(s) já cobrado(s) por ele, {len(ach) - nx} para conferir\n" + "\n".join(linhas)

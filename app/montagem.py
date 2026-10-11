"""MONTADOR (formato "cases"): narração + lista de cenas (ativos reais) → vídeo vertical no ritmo do Matheus Beirão.

spec (JSON):
  {"voice": "voz.mp3", "words": "words_final.json",   # palavras com start/end (tempo da narração)
   "w": 1080, "h": 1920, "fps": 30,
   "shots": [{"t0": 0.0, "t1": 3.2, "src": "arquivo.mp4", "ss": 380.0,
              "mode": "full" | "band",                # tela cheia (recorte vertical) | faixa 16:9 sobre fundo desfocado
              "x": 0.5,                               # centro do recorte horizontal (modo full)
              "zoom": "in" | "out" | "none",          # aproximação/afastamento contínuo (~6%)
              "punch": 6.1,                           # instante (s, na narração) do punch-in de ênfase
              "click": true}],                        # clique quando a imagem "brota" (prints, gráficos)
   "hooks": [9.22, 80.17],                            # cortes com som de expectativa terminando ali + luz + flash
   "music": {"slug": "mk_hip_hop_02", "vol": 0.10},
   "gold": ["1.500", "1,4", "bilhão", ...]}          # palavras da legenda em dourado
Legenda: Montserrat Alternates, minúscula, 2–3 palavras, branca, palavras-chave em Dourado Kronos (regras do usuário:
nada sobre rosto; aqui não há rosto do apresentador, a legenda fica na altura de ~62%).
"""
import json
import re
import subprocess
from pathlib import Path

from . import fonts, music as music_mod, sfx
from .media import FFMPEG, probe
from .render import LEAK_FRAMES, LEAK_PRE, ass_color, ass_header, ass_time, leak_frames

ROOT = Path(__file__).resolve().parent.parent
GOLD = "#E0BB6A"


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])


def _zoom_expr(z0, z1, nfr, punch_frame=None, punch=1.13):
    k = f"({z0:.5f}+({z1 - z0:.5f})*on/{max(1, nfr)})"
    if punch_frame is not None:
        k = f"({k}*(1+{punch - 1:.4f}*gte(on\\,{punch_frame})))"
    return k


def _persp(k):
    L, T = f"W*(1-1/{k})/2", f"H*(1-1/{k})*0.45"
    R, B = f"W-{L}", f"{T}+H/{k}"
    return (f"perspective=x0='{L}':y0='{T}':x1='{R}':y1='{T}':x2='{L}':y2='{B}':x3='{R}':y3='{B}'"
            f":interpolation=cubic:sense=source:eval=frame")


def render_shot(sh, out, W, H, fps, base_dir):
    src = Path(sh["src"])
    if not src.is_absolute():
        src = base_dir / src
    nfr = round(sh["t1"] * fps) - round(sh["t0"] * fps)
    dur = nfr / fps
    sdur = probe(src)["duration"] or 0
    ss = float(sh.get("ss", 0))
    if sdur and ss + dur > sdur - 0.05:                     # fonte curta: recua o trecho para caber
        ss = max(0.0, sdur - dur - 0.1)
    zoom = sh.get("zoom", "in")
    z0, z1 = {"in": (1.0, 1.07), "out": (1.07, 1.0), "none": (1.0, 1.0)}.get(zoom, (1.0, 1.06))
    pf = None
    if sh.get("punch") is not None:
        pf = max(0, round((sh["punch"] - sh["t0"]) * fps))
    k = _zoom_expr(z0, z1, nfr, pf)
    sharp = "unsharp=5:5:0.6:5:5:0.0,"
    if sh.get("mode", "full") == "full":
        x = float(sh.get("x", 0.5))
        vf = (f"scale='if(gt(iw/ih,{W}/{H}),-2,{W})':'if(gt(iw/ih,{W}/{H}),{H},-2)':flags=lanczos,"
              f"crop={W}:{H}:x=(iw-{W})*{x:.3f}:y=(ih-{H})/2,{sharp}setsar=1,fps={fps},{_persp(k)},format=yuv420p")
        fc = f"[0:v]setpts=PTS-STARTPTS,{vf},setpts=N/({fps}*TB)[v]"
    else:
        # faixa: o ativo inteiro (16:9) em cima de um fundo dele mesmo desfocado e escuro
        bw = W
        y = int(H * float(sh.get("y", 0.40)))
        fc = (f"[0:v]setpts=PTS-STARTPTS,split=2[a][b];"
              f"[b]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,"
              f"eq=brightness=-0.18:saturation=0.8,setsar=1,fps={fps}[bg];"
              f"[a]scale={bw}:-2:flags=lanczos,{sharp}setsar=1,fps={fps},{_persp(k)}[fg];"
              f"[bg][fg]overlay=(W-w)/2:{y}-h/2,format=yuv420p,setpts=N/({fps}*TB)[v]")
    _run([FFMPEG, "-y", "-v", "error", "-ss", f"{ss:.3f}", "-i", str(src), "-t", f"{dur + 0.5:.3f}",
          "-filter_complex", fc, "-map", "[v]", "-frames:v", str(nfr), "-r", str(fps), "-an",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-video_track_timescale", "15360", str(out)])
    return nfr


def captions_ass(words, path, W, H, gold_words, total):
    """Legendas de 2–3 palavras (quebra na pontuação), minúsculas, palavras-chave em dourado."""
    size = int(W * 0.082)
    txt = ass_color("#F5EFE6")
    shade = ass_color("#150C06", 0x40)
    style = (f"Style: Cap,{fonts.CAPTION_FONT} Bold,{size},{txt},{txt},{shade},{ass_color('#150C06', 0x70)},"
             f"0,0,0,0,100,100,{-size * 0.03:.1f},0,1,{max(3, size // 14)},2,5,60,60,0,1")
    lines = [ass_header(W, H, [style])]
    gold = ass_color(GOLD)
    golds = {g.lower() for g in gold_words}
    chunks, cur = [], []
    for wd in words:
        cur.append(wd)
        end_punct = re.search(r"[.,!?…:;]$", wd["w"])
        if len(cur) >= 3 or (end_punct and len(cur) >= 1) or (len(cur) == 2 and len(" ".join(x["w"] for x in cur)) > 16):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    y = int(H * 0.62)
    for n, ch in enumerate(chunks):
        a = ch[0]["start"]
        b = chunks[n + 1][0]["start"] if n + 1 < len(chunks) else total
        b = min(b, ch[-1]["end"] + 0.6)
        parts = []
        for wd in ch:
            raw = wd["w"].strip('"“”')
            low = raw if raw.isupper() and len(raw) > 1 else raw.lower()
            low = re.sub(r"[,;:]$", "", low)
            clean = re.sub(r"[^\wÀ-ÿ.,$]", "", raw.lower()).strip(".,")
            is_gold = clean in golds or bool(re.search(r"\d", raw))
            parts.append((f"{{\\1c{gold}}}" if is_gold else "") + low + (f"{{\\1c{txt}}}" if is_gold else ""))
        text = " ".join(parts)
        lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,"
                     f"{{\\an5\\pos({W // 2},{y})\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)\\fad(40,0)}}{text}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(spec_path, out_path, on_progress=print):
    spec_path = Path(spec_path).resolve()
    base = spec_path.parent
    S = json.loads(spec_path.read_text(encoding="utf-8"))
    W, H, fps = S.get("w", 1080), S.get("h", 1920), S.get("fps", 30)
    voice = base / S["voice"]
    words = json.loads((base / S["words"]).read_text(encoding="utf-8"))
    total = probe(voice)["duration"]
    work = base / "_montagem"
    work.mkdir(exist_ok=True)
    shots = sorted(S["shots"], key=lambda s: s["t0"])
    # cobre a linha do tempo inteira: cada cena vai até a próxima começar
    for i, sh in enumerate(shots):
        sh["t1"] = shots[i + 1]["t0"] if i + 1 < len(shots) else total
    clips = []
    import hashlib
    for i, sh in enumerate(shots):
        key = hashlib.sha1(json.dumps([sh, W, H, fps, "v2"], sort_keys=True).encode()).hexdigest()[:10]
        out = work / f"shot_{i:03d}_{key}.mp4"
        if not out.exists():
            render_shot(sh, out, W, H, fps, base)
        clips.append(out)
        if i % 8 == 0:
            on_progress(f"cenas {i + 1}/{len(shots)}")
    lst = work / "lista.txt"
    bad = [c.name for c in clips if not probe(c)["duration"]]
    if bad:
        raise RuntimeError(f"cenas vazias: {bad}")
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips))
    joined = work / "junto.mp4"
    _run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    # legendas
    ass = work / "legendas.ass"
    captions_ass(words, ass, W, H, S.get("gold", []), total)
    # áudio: voz + música (abaixa sob a voz) + sons (expectativa terminando no corte, flash, cliques)
    sfx.ensure_synth()
    inputs = ["-i", str(joined), "-i", str(voice)]
    fa = []
    mix = ["[vo]"]
    fa.append("[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0,asplit=2[vo][vk]")
    n_in = 2
    events = []
    meta = {x["name"]: x for x in sfx.CATALOG}
    for t in S.get("hooks", []):
        events.append(("reverse_expectativa", t - meta["reverse_expectativa"].get("lead", 2.3)))
        events.append(("flash_camera", t - meta["flash_camera"].get("lead", 0.02)))
    for sh in shots:
        if sh.get("click"):
            events.append(("click_classico", sh["t0"]))
    for k, (name, t) in enumerate(events):
        p = sfx.path_of(name)
        g = meta[name].get("gain", 0)
        inputs += ["-i", str(p)]
        fa.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={g}dB,"
                  f"adelay={int(max(0, t) * 1000)}:all=1[s{k}]")
        mix.append(f"[s{k}]")
        n_in += 1
    m = S.get("music")
    if m:
        mp = music_mod.ensure(m["slug"])
        inputs += ["-stream_loop", "-1", "-i", str(mp)]
        fa.append(f"[{n_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total + 1:.2f},"
                  f"volume={m.get('vol', 0.12)},afade=t=out:st={total - 2:.2f}:d=2[mu0]")
        fa.append("[mu0][vk]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=400[mu]")
        mix.append("[mu]")
        n_in += 1
    fa.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    # vídeo: legendas + luz (leak) nos cortes do hook
    fv = []
    cur = "0:v"
    for j, t in enumerate(S.get("hooks", [])):
        d = leak_frames(fps, side=j % 2)
        t0 = max(0.0, t - LEAK_PRE / fps)
        t1 = t + (LEAK_FRAMES - LEAK_PRE) / fps
        inputs += ["-framerate", f"{fps:g}", "-i", str(Path(d) / "%05d.png")]
        fv.append(f"[{n_in}:v]format=rgba,scale={W}:{H},setpts=PTS-STARTPTS+{t0:.3f}/TB[lk{j}]")
        fv.append(f"[{cur}][lk{j}]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})':eof_action=pass[lv{j}]")
        cur = f"lv{j}"
        n_in += 1
    rel = Path(ass).relative_to(ROOT).as_posix().replace(":", "\\:").replace("'", "\\'")
    fv.append(f"[{cur}]ass='{rel}':fontsdir=fonts,format=yuv420p[v]")
    _run([FFMPEG, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fv + fa),
          "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)])
    return out_path

"""ESTALO: você estala os dedos e o fundo vira outro cenário (ex.: a Biblioteca de Alexandria), com transição e som.

Nível "profissional" (pedido do usuário: nada de cabeça com pedaços brancos, nada de cara de amador):
1. o ESTALO é achado no áudio (transiente agudo mais forte) e a MÃO na imagem (Apple Vision, pose da mão);
2. RECORTE de você + cadeira em cada quadro com o recorte nativo do Mac (Vision "foreground instance mask"),
   refinado por FILTRO GUIADO pela própria imagem (borda de cabelo macia) e estabilizado no tempo (não "ferve");
3. DESCONTAMINAÇÃO: a câmera está parada, então dá para reconstruir a parede original (mediana dos quadros onde ela
   aparece) e tirar a cor dela das bordas — é isso que elimina os "pedaços brancos" no cabelo
   (equação do recorte: I = αF + (1−α)B  →  F = (I − (1−α)B) / α);
4. CENÁRIO como lente de celular (desfoque), exposição/cor casadas com a sua luz, granulação, luz do cenário
   vazando de leve na sua borda (light wrap) e uma leve "reluz" quente em você;
5. TRANSIÇÃO no estalo: onda de luz quente nascendo da mão, revelando o cenário + soco de câmera sutil;
   SOM: subida curta antes e impacto grave no estalo (biblioteca do editor).
"""
import json
import subprocess
from pathlib import Path

import numpy as np

from .media import FFMPEG, probe

ROOT = Path(__file__).resolve().parent.parent
BG_DIR = ROOT / "backgrounds"
CENARIOS = {
    "alexandria": {"file": "alexandria21.jpg", "nome": "Biblioteca de Alexandria (Bibliotheca Alexandrina, salão principal)",
                   "credit": "Foto: Cecioka — Wikimedia Commons, CC BY-SA 4.0 ('Bibliotheca Alexandrina 21.jpg')"},
    "alexandria2": {"file": "alexandria22.jpg", "nome": "Biblioteca de Alexandria (vista 2)",
                    "credit": "Foto: Cecioka — Wikimedia Commons, CC BY-SA 4.0 ('Bibliotheca Alexandrina 22.jpg')"},
    "alexandria3": {"file": "alexandria23.jpg", "nome": "Biblioteca de Alexandria (vista 3)",
                    "credit": "Foto: Cecioka — Wikimedia Commons, CC BY-SA 4.0 ('Bibliotheca Alexandrina 23.jpg')"},
}


# ---------------------------------------------------------------- 1. o estalo e a mão

def snap_candidates(path, top=3):
    """Candidatos a estalo [(segundo, pontuação)], melhor primeiro. Um estalo é um estouro AGUDO (muita energia
    acima de 5 kHz), de ATAQUE instantâneo (chega ao pico em ≤ 4 ms), MUITO mais alto que o entorno e CURTÍSSIMO
    (em 40 ms já caiu). Os chiados e consoantes da fala ("s", "t", "x") até são agudos, mas sobem devagar ou duram mais."""
    def env_of(hp):
        raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "32000", "-af", f"highpass=f={hp}",
                              "-f", "f32le", "-"], capture_output=True).stdout
        a = np.abs(np.frombuffer(raw, np.float32))
        return np.array([a[i:i + 64].max() for i in range(0, len(a) - 64, 64)]) if len(a) > 3200 else None
    env, hi = env_of(2200), env_of(5000)
    if env is None:
        return []
    n = min(len(env), len(hi))
    out = []
    for k in range(25, n - 25):
        if env[k] < env[k - 1] or env[k] < env[k + 1]:
            continue
        if env[min(n - 1, k + 20)] > env[k] * 0.35:              # ainda alto 40 ms depois → não é estalo
            continue
        if env[k - 2] > env[k] * 0.45:                           # subiu devagar → consoante, não estalo
            continue
        ctx = np.median(env[max(0, k - 100):min(n, k + 100)]) + 1e-5
        bright = hi[k] / (env[k] + 1e-6)                         # fração acima de 5 kHz
        out.append((k, env[k] / ctx * np.sqrt(env[k]) * (0.4 + bright)))
    out.sort(key=lambda x: -x[1])
    res = []
    for k, sc in out:
        if any(abs(k - kk) < 50 for kk, _ in res):
            continue
        res.append((k, sc))
        if len(res) >= top:
            break
    final = []
    for k, sc in res:
        k0 = k
        while k0 > 0 and env[k0 - 1] > env[k] * 0.35:
            k0 -= 1
        final.append((round(k0 * 64 / 32000, 3), round(float(sc), 2)))
    return final


def detect_snap(path):
    c = snap_candidates(path, 1)
    return c[0][0] if c else None


def _cg(rgb):
    import Quartz
    h, w, _ = rgb.shape
    data = np.dstack([rgb, np.full((h, w), 255, np.uint8)]).tobytes()
    prov = Quartz.CGDataProviderCreateWithData(None, data, len(data), None)
    return Quartz.CGImageCreate(w, h, 8, 32, w * 4, Quartz.CGColorSpaceCreateDeviceRGB(),
                                Quartz.kCGImageAlphaNoneSkipLast, prov, None, False, Quartz.kCGRenderingIntentDefault)


def hand_point(rgb):
    """(x, y) normalizado (origem em cima) do estalo: entre a ponta do polegar e a do dedo médio."""
    import Vision
    req = Vision.VNDetectHumanHandPoseRequest.alloc().initWithCompletionHandler_(None)
    req.setMaximumHandCount_(2)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(_cg(rgb), None)
    h.performRequests_error_([req], None)
    best = None
    for obs in req.results() or []:
        pts = []
        for j in (Vision.VNHumanHandPoseObservationJointNameThumbTip, Vision.VNHumanHandPoseObservationJointNameMiddleTip,
                  Vision.VNHumanHandPoseObservationJointNameIndexTip):
            p, _err = obs.recognizedPointForJointName_error_(j, None)
            if p is not None and p.confidence() > 0.3:
                pts.append((p.location().x, 1 - p.location().y, p.confidence()))
        if pts and (best is None or sum(c for *_, c in pts) > best[2]):
            best = (np.mean([x for x, _, _ in pts]), np.mean([y for _, y, _ in pts]), sum(c for *_, c in pts))
    return (float(best[0]), float(best[1])) if best else None


def finger_gap(rgb):
    """Menor distância (fração da largura) entre a ponta do polegar e a do dedo médio — no instante antes do estalo
    elas estão encostadas. None se não houver mão visível."""
    import Vision
    req = Vision.VNDetectHumanHandPoseRequest.alloc().initWithCompletionHandler_(None)
    req.setMaximumHandCount_(2)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(_cg(rgb), None)
    h.performRequests_error_([req], None)
    best = None
    for obs in req.results() or []:
        t, _ = obs.recognizedPointForJointName_error_(Vision.VNHumanHandPoseObservationJointNameThumbTip, None)
        m, _ = obs.recognizedPointForJointName_error_(Vision.VNHumanHandPoseObservationJointNameMiddleTip, None)
        if t is None or m is None or min(t.confidence(), m.confidence()) < 0.3:
            continue
        ar = rgb.shape[0] / rgb.shape[1]
        g = float(np.hypot(t.location().x - m.location().x, (t.location().y - m.location().y) * ar))
        best = g if best is None else min(best, g)
    return best


def pick_snap(cands, frames, fps):
    """Entre os candidatos do áudio, fica com o que tem polegar e médio encostados logo antes (assinatura do estalo)."""
    for t, _sc in cands:
        for dt in (0.03, 0.07, 0.11):
            k = int(round((t - dt) * fps))
            if 0 <= k < len(frames):
                g = finger_gap(frames[k])
                if g is not None and g < 0.06:
                    return t
    return cands[0][0] if cands else None


# ---------------------------------------------------------------- 2. recorte de alta qualidade

def _pb(pb):
    try:
        import CoreVideo as CV
    except ImportError:
        import Quartz as CV
    CV.CVPixelBufferLockBaseAddress(pb, 1)
    w, h = CV.CVPixelBufferGetWidth(pb), CV.CVPixelBufferGetHeight(pb)
    bpr, fmt = CV.CVPixelBufferGetBytesPerRow(pb), CV.CVPixelBufferGetPixelFormatType(pb)
    buf = bytes(CV.CVPixelBufferGetBaseAddress(pb).as_buffer(bpr * h))
    CV.CVPixelBufferUnlockBaseAddress(pb, 1)
    if fmt == 1278226534:                            # 'L00f' float32
        return np.frombuffer(buf, np.float32).reshape(h, bpr // 4)[:, :w].copy()
    return np.frombuffer(buf, np.uint8).reshape(h, bpr)[:, :w].astype(np.float32) / 255.0


def raw_mask(rgb):
    """Você + o que está "colado" em você (cadeira, microfone): recorte nativo do macOS (o mesmo do 'recortar
    objeto' das fotos). Sem instância achada → máscara vazia."""
    import Vision
    req = Vision.VNGenerateForegroundInstanceMaskRequest.alloc().initWithCompletionHandler_(None)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(_cg(rgb), None)
    h.performRequests_error_([req], None)
    res = req.results() or []
    if not res:
        return np.zeros(rgb.shape[:2], np.float32)
    obs = res[0]
    out = obs.generateScaledMaskForImageForInstances_fromRequestHandler_error_(obs.allInstances(), h, None)
    m = _pb(out[0] if isinstance(out, tuple) else out)
    if m.shape != rgb.shape[:2]:
        import cv2
        m = cv2.resize(m, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR)
    return np.clip(m, 0, 1)


def guided(I, p, r, eps):
    """Filtro guiado (He et al.): a máscara herda as bordas finas da imagem (fios de cabelo)."""
    import cv2
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mI, mp = box(I), box(p)
    a = (box(I * p) - mI * mp) / (box(I * I) - mI * mI + eps)
    b = mp - a * mI
    return box(a) * I + box(b)


def refine(rgb, m, prev=None, prev_rgb=None):
    import cv2
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    # trabalha em meia resolução (rápido) e volta — o filtro guiado aproveita a imagem cheia
    a = guided(g, m.astype(np.float32), r=max(4, rgb.shape[1] // 180), eps=2e-3)
    a = np.clip(a, 0, 1)
    a = np.clip((a - 0.04) / 0.92, 0, 1)            # tira véu residual e firma o miolo
    if prev is not None:                             # estabilidade no tempo: onde a imagem não mexeu, média
        moved = cv2.GaussianBlur(np.abs(rgb.astype(np.int16) - prev_rgb.astype(np.int16)).max(2).astype(np.float32),
                                 (0, 0), 3) > 10
        a = np.where(moved, a, 0.55 * a + 0.45 * prev)
    return a.astype(np.float32)


# ---------------------------------------------------------------- 3–4. parede original, cenário e composição

def wall_plate(frames, alphas):
    """A parede ORIGINAL atrás de você (mediana dos quadros onde ela aparece; o que nunca aparece é completado)."""
    import cv2
    F = np.stack(frames).astype(np.float32)
    A = np.stack(alphas)
    vis = A < 0.04
    plate = np.zeros(F.shape[1:], np.float32)
    cnt = vis.sum(0)
    for c in range(3):
        ch = np.where(vis, F[..., c], np.nan)
        plate[..., c] = np.nan_to_num(np.nanmedian(ch, axis=0))
    hole = (cnt == 0).astype(np.uint8)
    if hole.any():
        sm = cv2.resize(plate.astype(np.uint8), None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
        hs = cv2.resize(hole, (sm.shape[1], sm.shape[0]), interpolation=cv2.INTER_NEAREST)
        fill = cv2.inpaint(sm, hs, 9, cv2.INPAINT_TELEA)
        fill = cv2.resize(fill, (plate.shape[1], plate.shape[0]), interpolation=cv2.INTER_CUBIC).astype(np.float32)
        plate = np.where(hole[..., None] > 0, fill, plate)
    return plate


def scene_plate(path, W, H, person_rgb, wall_rgb):
    """Foto do cenário pronta: preenche o quadro, desfoque de lente de celular, exposição/cor casadas com a luz
    da cena original (você foi iluminado por ela) e vinheta suave."""
    import cv2
    from PIL import Image
    im = np.asarray(Image.open(path).convert("RGB"), np.float32)
    h, w = im.shape[:2]
    s = max(W / w, H / h) * 1.08                     # folga para a câmera "assentar" depois do estalo
    im = cv2.resize(im, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    sigma = W * 0.009                                # desfoque de lente (pessoa em foco, fundo não)
    im = cv2.GaussianBlur(im, (0, 0), sigma)
    # exposição: o cenário fica um pouco mais escuro que você (sujeito em destaque, como retrato)
    lum = lambda x: float((x * [0.2126, 0.7152, 0.0722]).sum(-1).mean())
    target = min(lum(wall_rgb), lum(person_rgb) * 1.05) * 0.82
    im *= np.clip(target / max(1.0, lum(im)), 0.55, 1.35)
    yy, xx = np.mgrid[0:im.shape[0], 0:im.shape[1]].astype(np.float32)
    cx, cy = im.shape[1] / 2, im.shape[0] * 0.45
    r = np.sqrt(((xx - cx) / im.shape[1]) ** 2 + ((yy - cy) / im.shape[0]) ** 2)
    im *= (1 - 0.32 * np.clip(r / 0.75, 0, 1) ** 2)[..., None]
    return np.clip(im, 0, 255)


def crop_scene(big, W, H, zoom):
    """Recorte do cenário no quadro; zoom > 1 = mais fechado (o cenário "assenta" de 1,06 para 1)."""
    import cv2
    bh, bw = big.shape[:2]
    # mesma proporção do quadro (sem achatar) e cabendo na foto
    ch = min(bh, bw * H / W) / 1.08 / zoom
    cw = ch * W / H
    # horizonte da foto (meio dela, foto de celular na altura dos olhos) na altura do horizonte da câmera (~42%)
    x0 = (bw - cw) / 2
    y0 = float(np.clip(bh / 2 - 0.42 * ch, 0, bh - ch))
    M = np.float32([[W / cw, 0, -x0 * W / cw], [0, H / ch, -y0 * H / ch]])
    return cv2.warpAffine(big, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def composite(rgb, a, wall, bg, warm):
    import cv2
    I = rgb.astype(np.float32)
    A = a[..., None]
    # descontaminação: tira a parede original das bordas (fim dos "pedaços brancos")
    band = (A > 0.02) & (A < 0.985)
    F = (I - (1 - A) * wall) / np.maximum(A, 0.08)
    F = np.clip(F, 0, 255)
    F = np.where(band, F, I)
    # pixels quase transparentes: a cor "descontaminada" fica instável → puxa a cor de dentro (vizinhança)
    core = (a > 0.9).astype(np.float32)
    k = max(9, (rgb.shape[1] // 60) | 1)
    inside = cv2.GaussianBlur(I * core[..., None], (k, k), 0) / np.maximum(cv2.GaussianBlur(core, (k, k), 0)[..., None], 1e-3)
    t = np.clip((A - 0.08) / 0.25, 0, 1)
    F = np.where(band, F * t + inside * (1 - t), F)
    # "reluz": você recebe um pouco da cor do novo ambiente
    F = F * warm
    out = A * F + (1 - A) * bg
    # light wrap: a luz do cenário vaza ~ alguns px para dentro da sua borda
    ab = cv2.GaussianBlur(a, (0, 0), max(2.0, rgb.shape[1] / 300))
    edge = np.clip(1 - ab, 0, 1)[..., None] * A
    bgb = cv2.GaussianBlur(bg, (0, 0), rgb.shape[1] / 70)
    return out * (1 - 0.45 * edge) + bgb * 0.45 * edge


# ---------------------------------------------------------------- 5. transição

def ease_out(x):
    return 1 - (1 - np.clip(x, 0, 1)) ** 3


def transition(orig, comp, t_rel, hand, W, H, dur=0.55):
    """t_rel = segundos desde o estalo. Onda de luz quente nasce da mão e revela o cenário."""
    if t_rel < 0:
        return orig
    if t_rel >= dur:
        return comp
    p = t_rel / dur
    yy, xx = np.ogrid[0:H, 0:W]
    hx, hy = hand[0] * W, hand[1] * H
    d = np.sqrt((xx - hx) ** 2 + (yy - hy) ** 2).astype(np.float32)
    rmax = float(np.sqrt(max(hx, W - hx) ** 2 + max(hy, H - hy) ** 2)) * 1.05
    rad = ease_out(p) * rmax
    soft = W * 0.09
    rev = np.clip((rad - d) / soft + 0.5, 0, 1)[..., None]
    out = comp * rev + orig.astype(np.float32) * (1 - rev)
    # anel de luz quente (dourado/creme da paleta) na frente da onda, apagando com o tempo
    ring = np.exp(-((d - rad) / (W * 0.05)) ** 2)[..., None] * (1 - p) ** 1.4
    out = out + ring * np.array([255, 214, 150], np.float32) * 0.38
    # clarão curtíssimo no instante do estalo, nascendo da mão
    glow = np.exp(-(d / (W * 0.3)) ** 2)[..., None] * max(0.0, 1 - t_rel / 0.16) * 42
    return np.clip(out + glow, 0, 255)


def punch(img, t_rel):
    """Soco de câmera sutil no estalo (1 → 1,025 → 1), como se a imagem 'respirasse' com o impacto."""
    import cv2
    if t_rel < 0 or t_rel > 0.35:
        return img
    z = 1 + 0.025 * np.sin(np.pi * t_rel / 0.35)
    H, W = img.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H * 0.45), 0, z)
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------- tudo junto

def render(src, out, cenario="alexandria", t_snap=None, on_progress=print):
    """Gera o MP4 final (1080 de largura, som original + efeitos). Devolve um dict com o que foi feito."""
    import cv2
    info = probe(src)
    sw, sh = info["width"], info["height"]
    W = 1080 if sw < sh else 1920
    W, H = W, int(round(sh * W / sw / 2) * 2)
    fps = info.get("fps") or 30
    cands = [] if t_snap is not None else snap_candidates(src, 3)
    if t_snap is None and not cands:
        raise RuntimeError("Não achei o estalo no áudio.")
    dec = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-vf", f"scale={W}:{H}:flags=lanczos", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    frames, alphas, prev, prev_rgb = [], [], None, None
    while True:
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        rgb = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        a = refine(rgb, raw_mask(rgb), prev, prev_rgb)
        frames.append(rgb)
        alphas.append(a)
        prev, prev_rgb = a, rgb
        if on_progress and len(frames) % 30 == 0:
            on_progress(f"recortando: {len(frames)} quadros")
    dec.wait()
    n = len(frames)
    if t_snap is None:
        t_snap = pick_snap(cands, frames, fps)
    k_snap = min(n - 1, int(round(t_snap * fps)))
    hand = hand_point(frames[k_snap]) or hand_point(frames[max(0, k_snap - 2)]) or (0.62, 0.62)
    step = max(1, n // 60)
    wall = wall_plate(frames[::step], alphas[::step])
    sel = [f[a > 0.95] for f, a in zip(frames[::step], alphas[::step]) if (a > 0.95).any()][:10]
    person_rgb = np.concatenate(sel) if sel else wall.reshape(-1, 3)
    cen = CENARIOS[cenario]
    big = scene_plate(BG_DIR / cen["file"], W, H, person_rgb.astype(np.float32), wall)
    # reluz quente leve: você puxa ~12% da cor média do cenário
    bgm = big.reshape(-1, 3).mean(0)
    warm = 1 + 0.12 * (bgm / bgm.mean() - 1)
    enc = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps}",
                            "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p",
                            str(Path(out).with_suffix(".video.mp4"))], stdin=subprocess.PIPE)
    rng = np.random.default_rng(7)
    for i, (rgb, a) in enumerate(zip(frames, alphas)):
        t_rel = (i - k_snap) / fps
        if t_rel < 0:
            frame = rgb.astype(np.float32)
        else:
            settle = 1.0 + 0.06 * (1 - ease_out(t_rel / 2.4))          # o cenário "assenta" depois do estalo
            bg = crop_scene(big, W, H, settle)
            bg = bg + rng.normal(0, 3.2, bg.shape).astype(np.float32)  # granulação de vídeo
            comp = composite(rgb, a, wall, bg, warm)
            frame = transition(rgb, comp, t_rel, hand, W, H)
        frame = punch(np.clip(frame, 0, 255).astype(np.float32), t_rel)
        enc.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
        if on_progress and i % 30 == 0:
            on_progress(f"compondo: {i}/{n}")
    enc.stdin.close()
    enc.wait()
    # som: original + subida curta antes do estalo + impacto grave no estalo
    from . import sfx
    meta = {x["name"]: x for x in sfx.CATALOG}
    ins, filt, labs = ["-i", str(Path(out).with_suffix(".video.mp4")), "-i", str(src)], [], []
    plan = [("riser_curto", t_snap - 0.62, -9), ("whoosh_impacto_grave", t_snap - float(meta.get("whoosh_impacto_grave", {}).get("lead", 0.05)), -5)]
    for j, (name, at, gain) in enumerate(plan):
        p = sfx.path_of(name)
        if not p:
            continue
        ins += ["-i", str(p)]
        filt.append(f"[{len(ins) // 2 - 1}:a]volume={gain}dB,adelay={int(max(0, at) * 1000)}:all=1[s{j}]")
        labs.append(f"[s{j}]")
    has_audio = info.get("has_audio", True)
    if has_audio:
        filt.append("[1:a]aformat=sample_rates=48000:channel_layouts=stereo[vo]")
        mix = "[vo]" + "".join(labs) + f"amix=inputs={1 + len(labs)}:duration=first:normalize=0[a]"
    else:
        mix = "".join(labs) + f"amix=inputs={len(labs)}:duration=longest:normalize=0[a]"
    filt.append(mix)
    subprocess.run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    Path(out).with_suffix(".video.mp4").unlink(missing_ok=True)
    Path(out).with_suffix(".creditos.txt").write_text("Créditos:\n- Cenário: " + cen["credit"] + "\n", encoding="utf-8")
    return {"saida": str(out), "estalo_s": t_snap, "candidatos": cands, "mao": hand, "quadros": n, "cenario": cen["nome"]}

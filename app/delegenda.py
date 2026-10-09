"""REMOVER LEGENDA "queimada" no vídeo, deixando o fundo real (sem borrão).

Ideia: atrás da legenda quase sempre há um fundo FIXO (parede, cenário). Como as palavras mudam de largura e somem nas
pausas, cada pedaço do fundo aparece descoberto em algum momento. Então:
  1. lê só a FAIXA da legenda de todos os quadros (sem carregar o 4K inteiro na memória);
  2. acha o texto em cada quadro com o OCR da Apple (local) → máscara (com folga para caixa preta e sombra);
  3. separa os planos (cortes) e alinha os quadros de cada plano com homografia (o fundo é plano; zoom/balanço ok);
  4. monta, por plano, uma "placa" do fundo limpo = mediana dos quadros alinhados sem texto. O que nunca apareceu
     descoberto é preenchido UMA vez por plano (estável, sem tremer);
  5. em cada quadro, cola a placa só onde havia texto: borda suave, brilho/cor ajustados ao instante e granulação
     igual à do vídeo — para não dar para perceber;
  6. confere o resultado com o OCR de novo (relatório de quadros que ainda tenham texto).
"""
import json
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from . import ocr
from .media import FFMPEG, probe

PAD_X, PAD_TOP, PAD_BOTTOM = 100, 85, 95    # folga ao redor do texto (caixa de destaque + sombra: ~60 px medidos)
WIN, FAR = 36, 240                          # vizinhos: todos até ±1,5 s, depois de 6 em 6 até ±10 s (24 fps)


def _read_band(src, y0, h, W, out_path, n_frames):
    mm = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.uint8, shape=(n_frames, h, W, 3))
    p = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-vf", f"crop={W}:{h}:0:{y0}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    k, size = 0, h * W * 3
    while k < n_frames:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        mm[k] = np.frombuffer(buf, np.uint8).reshape(h, W, 3)
        k += 1
    p.stdout.close()
    p.wait()
    mm.flush()
    return mm, k


def _ocr_mask(band, tmpdir):
    """Máscara do texto num quadro da faixa (OCR em meia resolução)."""
    h, w = band.shape[:2]
    small = cv2.resize(band, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    f = Path(tmpdir) / "o.jpg"
    cv2.imwrite(str(f), small, [cv2.IMWRITE_JPEG_QUALITY, 92])
    m = np.zeros((h, w), np.uint8)
    boxes = []
    for line in ocr.read(f):
        x0, y0, x1, y1 = [v * 2 for v in line["box"]]
        boxes.append((x0, y0, x1, y1))
        cv2.rectangle(m, (int(max(0, x0 - PAD_X)), int(max(0, y0 - PAD_TOP))),
                      (int(min(w - 1, x1 + PAD_X)), int(min(h - 1, y1 + PAD_BOTTOM))), 255, -1)
    return m, boxes


def _pixel_text(band, near):
    """Reforço do OCR: pixels de letra (branco/amarelo bem saturado) perto da área do texto."""
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    white = (hsv[..., 2] > 225) & (hsv[..., 1] < 40)
    yellow = (hsv[..., 0] > 20) & (hsv[..., 0] < 38) & (hsv[..., 1] > 120) & (hsv[..., 2] > 180)
    t = ((white | yellow) & (near > 0)).astype(np.uint8) * 255
    return cv2.dilate(t, np.ones((35, 35), np.uint8))


DIS = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def _complete_flow(fl, known):
    """Preenche o fluxo onde ele é desconhecido (atrás do texto) a partir dos vizinhos conhecidos
    (convolução normalizada em várias escalas: o movimento da parte visível de um objeto continua por trás)."""
    out = fl.copy()
    w = known.astype(np.float32)
    if w.all() or not w.any():
        return out
    filled = known.copy()
    for sig in (3, 8, 20, 50, 120):
        num = cv2.GaussianBlur(fl * w[..., None], (0, 0), sig)
        den = cv2.GaussianBlur(w, (0, 0), sig)[..., None]
        est = num / np.maximum(den, 1e-4)
        put = (~filled) & (den[..., 0] > 0.02)
        out[put] = est[put]
        filled |= put
        if filled.all():
            break
    out[~filled] = np.median(fl[known], axis=0)
    return out


def _stabilize(outband, masks, a, b, on_progress, R=2):
    """Já sem legenda: dentro da área reconstruída, cada quadro vira a mediana dele com os vizinhos (±R) alinhados
    por fluxo óptico. O que é parede/luminária de verdade se mantém; manchas que aparecem num quadro só somem."""
    hold = {}
    for k in range(a, b):
        m = masks[k]
        if not m.any():
            continue
        ys_, xs_ = np.nonzero(m)
        y0_, y1_, x0_, x1_ = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        cur = np.asarray(outband[k], np.uint8)[y0_:y1_, x0_:x1_]
        g0 = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)
        stack = [cur.astype(np.float32)]
        for j in range(max(a, k - R), min(b, k + R + 1)):
            if j == k:
                continue
            nb = hold[j][y0_:y1_, x0_:x1_] if j in hold else np.asarray(outband[j], np.uint8)[y0_:y1_, x0_:x1_]
            fl = DIS.calc(cv2.resize(g0, None, fx=0.5, fy=0.5),
                          cv2.resize(cv2.cvtColor(nb, cv2.COLOR_BGR2GRAY), None, fx=0.5, fy=0.5), None)
            fl = cv2.resize(fl, (x1_ - x0_, y1_ - y0_)) * 2
            gx, gy = np.meshgrid(np.arange(x1_ - x0_, dtype=np.float32), np.arange(y1_ - y0_, dtype=np.float32))
            stack.append(cv2.remap(nb, gx + fl[..., 0], gy + fl[..., 1], cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REFLECT).astype(np.float32))
        med = np.median(np.stack(stack), axis=0)
        core = cv2.GaussianBlur((cv2.erode(m, np.ones((25, 25), np.uint8)) > 0).astype(np.float32), (0, 0), 6)
        core = core[y0_:y1_, x0_:x1_, None]
        hold[k] = np.asarray(outband[k], np.uint8).copy()          # original (sem suavizar) para os próximos
        new = cur * (1 - core) + med * core
        fr = np.asarray(outband[k], np.uint8).copy()
        fr[y0_:y1_, x0_:x1_] = new.clip(0, 255).astype(np.uint8)
        outband[k] = fr
        for old in [x for x in hold if x < k - R]:
            del hold[old]


def _gray(b):
    return cv2.cvtColor(cv2.resize(b, (b.shape[1] // 2, b.shape[0] // 2)), cv2.COLOR_BGR2GRAY)


def _homography(ga, gb, na, nb, orb, bf):
    """H (na resolução das imagens dadas) que leva b → a, usando só o fundo (na/nb = 255 onde pode usar)."""
    ka, da = orb.detectAndCompute(ga, na)
    kb, db = orb.detectAndCompute(gb, nb)
    if da is None or db is None or len(ka) < 30 or len(kb) < 30:
        return None, 0
    ms = bf.knnMatch(db, da, k=2)
    good = [m for m, n in (x for x in ms if len(x) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 25:
        return None, len(good)
    pb = np.float32([kb[m.queryIdx].pt for m in good])
    pa = np.float32([ka[m.trainIdx].pt for m in good])
    H, inl = cv2.findHomography(pb, pa, cv2.RANSAC, 2.0)
    return H, int(inl.sum()) if inl is not None else 0


def remove(src, out, work=None, on_progress=print, y_range=None):
    """Remove a legenda do vídeo `src` e grava `out`. Devolve um relatório (dict)."""
    src, out = Path(src), Path(out)
    work = Path(work or tempfile.mkdtemp(prefix="delegenda-"))
    work.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    W, H, fps = info["width"], info["height"], info.get("fps") or 24
    n = int(round(info["duration"] * fps)) + 2

    # --- 0) onde fica a legenda: OCR em alguns quadros espalhados (ou faixa dada)
    if y_range is None:
        ys = []
        with tempfile.TemporaryDirectory() as td:
            for k in range(24):
                t = info["duration"] * (k + 0.5) / 24
                f = Path(td) / f"p{k}.jpg"
                subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                                "-vf", "scale=iw/2:-2", str(f)])
                ys += [(l["box"][1] * 2, l["box"][3] * 2) for l in ocr.read(f)]
        if not ys:
            raise RuntimeError("Não achei legenda no vídeo.")
        # a faixa que concentra a maior parte das linhas de texto
        mid = float(np.median([(a + b) / 2 for a, b in ys]))
        near = [(a, b) for a, b in ys if abs((a + b) / 2 - mid) < H * 0.08]
        y_range = (min(a for a, _ in near), max(b for _, b in near))
    y0 = int(max(0, y_range[0] - 140)) // 2 * 2
    y1 = int(min(H, y_range[1] + 160)) // 2 * 2
    bh = y1 - y0
    on_progress(f"faixa da legenda: y {y0}–{y1} de {H}")

    # --- 1) faixa de todos os quadros + imagem de alinhamento (parede do topo até a legenda, meia resolução)
    band, n = _read_band(src, y0, bh, W, work / "band.npy", n)
    ah, aw = y1 // 2 // 2 * 2, W // 2
    al = np.lib.format.open_memmap(work / "align.npy", mode="w+", dtype=np.uint8, shape=(n, ah, aw))
    p = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-vf", f"crop={W}:{ah * 2}:0:0,scale={aw}:{ah},format=gray",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    for k in range(n):
        buf = p.stdout.read(ah * aw)
        if len(buf) < ah * aw:
            break
        al[k] = np.frombuffer(buf, np.uint8).reshape(ah, aw)
    p.stdout.close()
    p.wait()
    on_progress(f"{n} quadros lidos")

    # --- 2) máscara do texto em cada quadro
    masks = np.lib.format.open_memmap(work / "mask.npy", mode="w+", dtype=np.uint8, shape=(n, bh, W))
    with tempfile.TemporaryDirectory() as td:
        for k in range(n):
            m, _ = _ocr_mask(band[k], td)
            if m.any():
                m |= _pixel_text(band[k], cv2.dilate(m, np.ones((61, 61), np.uint8)))
            masks[k] = m
            if k % 200 == 0:
                on_progress(f"OCR {k}/{n}")
    # legenda que entra/sai animada: une com os vizinhos (o OCR pode perder 1 quadro); janela rolante, pouca memória
    hist = []
    for k in range(n):
        cur = hist + [masks[j].copy() for j in range(k, min(n, k + 3))]      # k-2..k+2 originais
        u = cur[0].copy()
        for x in cur[1:]:
            u |= x
        hist = (hist + [masks[k].copy()])[-2:]
        masks[k] = u
    masks.flush()

    # --- 3) planos e alinhamento (homografia de cada quadro para o quadro de referência do plano)
    orb = cv2.ORB_create(4000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    # band (resolução cheia, origem em y0) ↔ alinhamento (meia resolução, origem no topo)
    S = np.array([[0.5, 0, 0], [0, 0.5, 0.5 * y0], [0, 0, 1]], np.float64)     # band → align
    Si = np.linalg.inv(S)

    def usable(k):
        u = np.full((ah, aw), 255, np.uint8)
        mk = cv2.resize(masks[k], (aw, bh // 2), interpolation=cv2.INTER_NEAREST)
        y = y0 // 2
        u[y:y + mk.shape[0]][:ah - y] &= 255 - mk[:ah - y]
        return u
    Hs = [np.eye(3)]
    shots = [0]
    for k in range(1, n):
        Ha, inl = _homography(al[k - 1], al[k], usable(k - 1), usable(k), orb, bf)
        diff = float(np.mean(cv2.absdiff(al[k - 1], al[k])))
        if Ha is None or inl < 60 or diff > 30:
            shots.append(k)
            Hs.append(np.eye(3))
        else:
            Hs.append(Hs[-1] @ (Si @ Ha @ S))  # k → início do plano (coordenadas da faixa)
        if k % 300 == 0:
            on_progress(f"alinhando {k}/{n} ({len(shots)} planos)")
    shots.append(n)
    np.save(work / "Hs.npy", np.array(Hs))
    (work / "shots.json").write_text(json.dumps(shots))
    on_progress(f"{len(shots) - 1} planos")

    small_m = np.stack([masks[k][::8, ::8] for k in range(n)])
    small_x = np.stack([cv2.dilate(masks[k], np.ones((41, 41), np.uint8))[::8, ::8] > 0 for k in range(n)])

    # --- 4) placa do fundo por plano e 5) composição
    outband = np.lib.format.open_memmap(work / "out.npy", mode="w+", dtype=np.uint8, shape=(n, bh, W, 3))
    holes_total = 0
    fallback_px = 0
    MARG = 220                                # a placa é maior que a faixa (zoom/balanço)
    T = np.array([[1, 0, MARG], [0, 1, MARG], [0, 0, 1]], np.float64)
    CW, CH = W + 2 * MARG, bh + 2 * MARG
    for s in range(len(shots) - 1):
        a, b = shots[s], shots[s + 1]
        ref = (a + b) // 2
        Href_inv = np.linalg.inv(Hs[ref])
        toC = [T @ Href_inv @ Hs[k] for k in range(a, b)]        # quadro k → tela da placa
        idx = np.linspace(a, b - 1, min(b - a, 48)).astype(int)
        need = np.zeros((CH, CW), np.uint8)
        for k in range(a, b):
            need |= cv2.warpPerspective(masks[k], toC[k - a], (CW, CH), flags=cv2.INTER_NEAREST)
        plate = np.zeros((CH, CW, 3), np.uint8)
        hole = np.zeros((CH, CW), np.uint8)
        if need.any():
            # só a região que precisa (economiza memória): retângulo em volta do texto do plano
            ys_, xs_ = np.nonzero(cv2.dilate(need, np.ones((61, 61), np.uint8)))
            ry0, ry1, rx0, rx1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
            stack = np.full((len(idx), ry1 - ry0, rx1 - rx0, 3), np.nan, np.float32)
            cover = np.zeros((ry1 - ry0, rx1 - rx0), np.int32)
            for j, k in enumerate(idx):
                M = toC[k - a]
                wf = cv2.warpPerspective(band[k], M, (CW, CH), flags=cv2.INTER_LINEAR)[ry0:ry1, rx0:rx1]
                ok = cv2.warpPerspective(255 - cv2.dilate(masks[k], np.ones((41, 41), np.uint8)), M, (CW, CH),
                                         flags=cv2.INTER_NEAREST, borderValue=0)[ry0:ry1, rx0:rx1] > 0
                stack[j][ok] = wf[ok]
                cover += ok
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(stack, axis=0)
            del stack
            plate[ry0:ry1, rx0:rx1] = np.nan_to_num(med, nan=0).clip(0, 255).astype(np.uint8)
            hole[ry0:ry1, rx0:rx1] = ((cover == 0) & (need[ry0:ry1, rx0:rx1] > 0)).astype(np.uint8) * 255
        nh = int((hole > 0).sum())
        holes_total += nh
        if nh:
            plate = cv2.inpaint(plate, cv2.dilate(hole, np.ones((5, 5), np.uint8)), 9, cv2.INPAINT_TELEA)
        excl = lambda k: cv2.dilate(masks[k], np.ones((41, 41), np.uint8))   # perto do texto não serve de fonte
        corners = np.float32([[0, 0], [W, 0], [W, bh], [0, bh]]).reshape(-1, 1, 2)

        def posed(k, j):
            """quanto o enquadramento mudou entre j e k (px médios nos cantos da faixa): menos = menos paralaxe"""
            Mjk = np.linalg.inv(Hs[k]) @ Hs[j]
            return float(np.linalg.norm(cv2.perspectiveTransform(corners, Mjk) - corners, axis=2).mean())
        for k in range(a, b):
            fr = band[k].copy()
            m = masks[k]
            if not m.any():
                outband[k] = fr
                continue
            # região a reconstruir neste quadro (retângulo em volta do texto)
            ys_, xs_ = np.nonzero(cv2.dilate(m, np.ones((31, 31), np.uint8)))
            qy0, qy1, qx0, qx1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
            Off = np.array([[1, 0, -qx0], [0, 1, -qy0], [0, 0, 1]], np.float64)
            size = (qx1 - qx0, qy1 - qy0)
            Hinv_k = np.linalg.inv(Hs[k])
            # alvo: o próprio quadro (fora do texto) serve de referência para o ajuste fino
            tgt = cv2.cvtColor(fr[qy0:qy1, qx0:qx1], cv2.COLOR_BGR2GRAY)
            tgt_ok = (excl(k)[qy0:qy1, qx0:qx1] == 0)
            loc = np.full((size[1], size[0], 3), np.nan, np.float32)
            todo = (m[qy0:qy1, qx0:qx1] > 0)
            acc = np.zeros((size[1], size[0], 3), np.float32)
            wsum = np.zeros((size[1], size[0]), np.float32)
            rank = 0
            patches = []
            # escolha dos vizinhos: os que MAIS mostram de parede limpa onde falta (escala 1/8, sem warp), o tempo
            # só desempata; assim as pausas sem legenda (parede inteira) são achadas mesmo se estiverem longe
            cands = [j for j in range(max(a, k - FAR), min(b, k + FAR + 1)) if j != k]
            rem = small_m[k] > 0
            srcs = []
            for _ in range(6):
                if not rem.any() or not cands:
                    break
                gain = np.array([(rem & ~small_x[j]).sum() * (1 - 0.0015 * abs(j - k)) * np.exp(-posed(k, j) / 45.0)
                                 for j in cands])
                bi = int(gain.argmax())
                if gain[bi] <= 0:
                    break
                j = cands.pop(bi)
                srcs.append(j)
                rem &= small_x[j]
            srcs.append(-1)                       # por último: a placa do plano (também passa pelo ajuste fino)
            for j in srcs:
                if not (todo & np.isnan(loc[..., 0])).any():
                    break
                if j == -1:
                    Mp = Off @ np.linalg.inv(toC[k - a])
                    wf = cv2.warpPerspective(plate, Mp, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
                    ok = np.ones(todo.shape, bool)
                else:
                    ok_src = 255 - excl(j)
                    ok_src[:8] = 0
                    ok_src[-8:] = 0
                    ok_src[:, :8] = 0
                    ok_src[:, -8:] = 0
                    M = Off @ Hinv_k @ Hs[j]                                  # quadro j → quadro k (homografia)
                    wf = cv2.warpPerspective(band[j], M, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
                    ok = cv2.warpPerspective(ok_src, M, size, flags=cv2.INTER_NEAREST, borderValue=0) > 0
                need = todo & np.isnan(loc[..., 0]) & ok
                if need.sum() < 50:
                    continue
                # ajuste fino por pixel (luminária e objetos fora do plano da parede têm paralaxe): fluxo óptico entre
                # o quadro k e o vizinho já alinhado; dentro do texto o fluxo é desconhecido → completado pelas bordas
                both = ok & tgt_ok
                if both.sum() > 4000:
                    g1 = cv2.resize(tgt, None, fx=0.5, fy=0.5)
                    g2 = cv2.resize(cv2.cvtColor(wf, cv2.COLOR_BGR2GRAY), None, fx=0.5, fy=0.5)
                    fl = DIS.calc(g1, g2, None)
                    w = cv2.resize(both.astype(np.uint8), (g1.shape[1], g1.shape[0]), interpolation=cv2.INTER_NEAREST)
                    fl = _complete_flow(fl, w > 0) * 2
                    fl = cv2.resize(fl, size, interpolation=cv2.INTER_LINEAR)
                    gx, gy = np.meshgrid(np.arange(size[0], dtype=np.float32), np.arange(size[1], dtype=np.float32))
                    mx, my = gx + fl[..., 0], gy + fl[..., 1]
                    wf = cv2.remap(wf, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
                    ok = cv2.remap(ok.astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderValue=0) > 0
                ok = cv2.erode(ok.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
                need = todo & np.isnan(loc[..., 0]) & ok
                # mesma luz do instante k (o vizinho pode estar um pouco mais claro/escuro)
                ring_ok = ok & tgt_ok
                if ring_ok.sum() > 2000:
                    gk = (fr[qy0:qy1, qx0:qx1][ring_ok].astype(np.float32).mean(0) + 1) / (wf[ring_ok].astype(np.float32).mean(0) + 1)
                    wf = (wf.astype(np.float32) * gk.clip(0.85, 1.18))
                # dono único por pixel: o primeiro (melhor) vizinho que mostra o ponto; guardo para costurar depois
                own = need.copy()
                patches.append((wf.astype(np.float32), ok, own))
                loc[need] = wf[need]
                rank += 1
            # costura: cada pixel é do seu dono; só numa faixa estreita entre donos vizinhos as fontes se misturam
            if len(patches) > 1:
                acc[:] = 0
                wsum[:] = 0
                for wfp, okp, ownp in patches:
                    wgt = cv2.GaussianBlur(ownp.astype(np.float32), (0, 0), 4) * okp
                    acc += wfp * wgt[..., None]
                    wsum += wgt
                cov = (wsum > 1e-3) & ~np.isnan(loc[..., 0])
                loc[cov] = acc[cov] / wsum[cov][..., None]
            miss = np.isnan(loc[..., 0])
            fallback_px += int((miss & todo).sum())
            # o que nenhum vizinho mostrou: placa do plano inteiro (já com o preenchimento estável)
            Minv = Off @ np.linalg.inv(toC[k - a])
            pw_shot = cv2.warpPerspective(plate, Minv, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).astype(np.float32)
            loc[miss] = pw_shot[miss]
            pw = fr.astype(np.float32).copy()
            pw[qy0:qy1, qx0:qx1] = loc
            # brilho/cor do instante: compara um anel em volta do texto
            ring = (cv2.dilate(m, np.ones((41, 41), np.uint8)) > 0) & (m == 0)
            if ring.sum() > 500:
                # luz LOCAL: razão quadro/preenchimento medida em volta do texto, espalhada para dentro (suave)
                rq = ring[qy0:qy1, qx0:qx1]
                if rq.sum() > 500:
                    f0 = fr[qy0:qy1, qx0:qx1].astype(np.float32) + 1
                    ratio = np.where(rq[..., None], f0 / (loc + 1), 0).astype(np.float32)
                    R = np.stack([_complete_flow(ratio[..., c:c + 1].repeat(2, axis=2), rq)[..., 0] for c in range(3)], -1)
                    R = cv2.GaussianBlur(R, (0, 0), 12)
                    pw[qy0:qy1, qx0:qx1] *= R.clip(0.75, 1.33)
                # granulação igual à do vídeo (a mediana fica "lisa" demais)
                hp = fr.astype(np.float32) - cv2.GaussianBlur(fr, (0, 0), 1.2).astype(np.float32)
                sd = float(hp[ring].std())
                hp2 = loc - cv2.GaussianBlur(loc, (0, 0), 1.2)
                sd2 = float(hp2.std()) + 1e-3
                if sd > sd2:
                    pw[qy0:qy1, qx0:qx1] += np.random.default_rng(k).normal(0, np.sqrt(sd * sd - sd2 * sd2), loc.shape)
            # a transição suave fica DENTRO da folga da máscara (lá o próprio quadro já é parede limpa); fora dela,
            # nada do quadro é tocado
            core = cv2.erode(m, np.ones((25, 25), np.uint8))
            alpha = cv2.GaussianBlur((core > 0).astype(np.float32), (0, 0), 6)[..., None]
            alpha[m == 0] = 0
            outband[k] = (fr * (1 - alpha) + pw * alpha).clip(0, 255).astype(np.uint8)
            if k % 100 == 0:
                on_progress(f"  quadro {k}")
        _stabilize(outband, masks, a, b, on_progress)
        on_progress(f"plano {s + 1}/{len(shots) - 1}: quadros {a}–{b - 1}, buracos preenchidos {nh} px")
    outband.flush()

    # --- 6) grava o vídeo: quadros originais com a faixa trocada (áudio original)
    dec = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(fps), "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a?",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                            "-c:a", "copy", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    size = W * H * 3
    for k in range(n):
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        fr[y0:y1] = outband[k]
        enc.stdin.write(fr.tobytes())
        if k % 300 == 0:
            on_progress(f"gravando {k}/{n}")
    dec.stdout.close()
    enc.stdin.close()
    dec.wait()
    enc.wait()

    # --- conferência: ainda tem texto?
    left = []
    with tempfile.TemporaryDirectory() as td:
        for k in range(0, n, 6):
            f = Path(td) / "q.jpg"
            cv2.imwrite(str(f), cv2.resize(outband[k], (W // 2, bh // 2)), [cv2.IMWRITE_JPEG_QUALITY, 92])
            txt = [l["text"] for l in ocr.read(f)]
            if txt:
                left.append({"frame": k, "t": round(k / fps, 2), "text": txt})
    rep = {"frames": n, "band": [y0, y1], "shots": len(shots) - 1, "holes_px": holes_total, "fallback_px": fallback_px, "text_left": left}
    (work / "relatorio.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep

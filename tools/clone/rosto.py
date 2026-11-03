"""CLONE — a boca do Roberto falando a fala nova, sobre trechos REAIS das gravações dele (cabeça, olhos, gestos, luz e
fundo de verdade). Só a metade de baixo do rosto é refeita, quadro a quadro, pelo MuseTalk 1.5 (MIT, local, MPS).
O detector de rosto do MuseTalk (mmpose + face_alignment) foi trocado pelo Apple Vision (já usado no editor). A
referência do modelo é um quadro do plano com a boca aberta e os dentes à mostra (como no treino); a mistura usa só os
LÁBIOS gerados e mantém a textura real da barba, com cor, nitidez e granulação casadas com o quadro original.
Roda no .venv-clone (Python 3.11). Só quando ele pede.

Uso: .venv-clone/bin/python tools/clone/rosto.py <plano.json> [--so-boca]
plano = {"audio": <wav da fala>, "fps": 30, "out": <mp4 sem som>,
         "shots": [{"src": <vídeo dele>, "ss": <s>, "n": <quadros>}, …],   (a soma dos n = duração da fala × fps)
         "biblioteca": [[<vídeo>, <início>, <fim>], …]}   (trechos de fala: as bocas REAIS — boca.py)
--so-boca: refaz só a escolha/colagem da boca real a partir de <out>.boca.npz (sem rodar o MuseTalk de novo).
CLONE_BOCA=gerada: os pixels do próprio MuseTalk (mistura antiga) em vez da boca real.
"""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
MT = ROOT / "vendor" / "MuseTalk"
MOD = ROOT / "models" / "clone"
sys.path.insert(0, str(MT))
import imageio_ffmpeg  # noqa: E402

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
DEV = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
DEBUG = bool(__import__("os").environ.get("CLONE_DEBUG"))
DUMP = __import__("os").environ.get("CLONE_DUMP")                    # pasta: salva recortes p/ ajustar a mistura
MODO_BOCA = __import__("os").environ.get("CLONE_BOCA", "real")      # "gerada" = os pixels do MuseTalk (compor)
MODO_REF = __import__("os").environ.get("CLONE_REF", "dentes")      # "mesmo" = o próprio quadro (como o repositório)


def _rss():
    import os
    return int(os.popen(f"ps -o rss= -p {os.getpid()}").read()) / 1e6


def sync():
    if DEBUG and DEV.type == "mps":
        torch.mps.synchronize()


# ---------------------------------------------------------------- modelos
def carregar():
    from diffusers import AutoencoderKL, UNet2DConditionModel
    from transformers import WhisperModel
    from musetalk.models.unet import PositionalEncoding
    from musetalk.utils.audio_processor import AudioProcessor
    vae = AutoencoderKL.from_pretrained(str(MOD / "sd-vae")).half().to(DEV).eval()   # fp16 = fp32 (PSNR 74 dB) com metade
    # da memória: em fp32 a decodificação de 4 quadros punha ~2 GB a mais e o Mac de 8 GB ia para o swap (16 s por lote)
    cfg = json.loads((MOD / "musetalkV15" / "musetalk.json").read_text())
    f16 = MOD / "musetalkV15" / "unet_fp16.pt"
    if not f16.exists():                                      # 1ª vez: converte (3,4 GB fp32 → 1,7 GB fp16) e guarda
        sd = torch.load(MOD / "musetalkV15" / "unet.pth", map_location="cpu", weights_only=True, mmap=True)
        torch.save({k: v.half() for k, v in sd.items()}, f16)
        del sd
    # pesos direto para a GPU, sem cópia na RAM (com a cópia o processo segurava 3,6 GB de RAM à toa e o Mac de 8 GB
    # ia para o swap no meio do vídeo)
    with torch.device("meta"):
        unet = UNet2DConditionModel(**cfg)
    unet.load_state_dict(torch.load(f16, map_location=DEV, weights_only=True, mmap=True), assign=True)
    unet = unet.half().to(DEV).eval()
    whisper = WhisperModel.from_pretrained(str(MOD / "whisper")).to(DEV).eval()
    ap = AudioProcessor(feature_extractor_path=str(MOD / "whisper"))
    pe = PositionalEncoding(d_model=384).to(DEV)
    return vae, unet, whisper, ap, pe


@torch.no_grad()
def audio_chunks(ap, whisper, wav, fps):
    feats, n = ap.get_audio_feature(str(wav))
    return ap.get_whisper_chunk(feats, DEV, torch.float32, whisper, n, fps=fps,
                                audio_padding_length_left=2, audio_padding_length_right=2)


# ---------------------------------------------------------------- rosto (Apple Vision)
def _cg(rgb):
    """CGImage para o Vision. Os bytes vão num NSData (memória do Objective-C, solta no fim do autorelease_pool):
    com CGDataProviderCreateWithData e um bytes do Python, cada quadro vazava ~9,6 MB (50 s de vídeo = 12 GB)."""
    import Foundation
    import Quartz
    h, w, _ = rgb.shape
    data = np.dstack([rgb, np.full((h, w), 255, np.uint8)]).tobytes()
    prov = Quartz.CGDataProviderCreateWithCFData(Foundation.NSData.dataWithBytes_length_(data, len(data)))
    return Quartz.CGImageCreate(w, h, 8, 32, w * 4, Quartz.CGColorSpaceCreateDeviceRGB(),
                                Quartz.kCGImageAlphaNoneSkipLast, prov, None, False, Quartz.kCGRenderingIntentDefault)


REGIOES = ("faceContour", "leftEyebrow", "rightEyebrow", "leftEye", "rightEye", "noseCrest", "nose", "outerLips", "innerLips")


def pontos_rosto(rgb):
    """Pontos do rosto em pixels (origem em cima à esquerda), por região. None se não houver rosto."""
    import objc
    import Vision
    H, W = rgb.shape[:2]
    with objc.autorelease_pool():
        req = Vision.VNDetectFaceLandmarksRequest.alloc().init()
        hd = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(_cg(rgb), None)
        ok, _ = hd.performRequests_error_([req], None)
        faces = list(req.results() or []) if ok else []
        if not faces:
            return None
        f = max(faces, key=lambda x: x.boundingBox().size.width * x.boundingBox().size.height)
        bb, lm = f.boundingBox(), f.landmarks()
        out = {}
        for nome in REGIOES:
            reg = getattr(lm, nome)()
            if reg is None:
                continue
            pts = reg.normalizedPoints()
            xy = []
            for i in range(reg.pointCount()):
                p = pts[i]
                xy.append(((bb.origin.x + p.x * bb.size.width) * W, (1 - (bb.origin.y + p.y * bb.size.height)) * H))
            out[nome] = np.array(xy, np.float32)
        return out


def pontos_caixa(q, box, pad=0.35):
    """Pontos do rosto só num recorte em volta da caixa (rápido); devolve em coordenadas do quadro."""
    H, W = q.shape[:2]
    x1, y1, x2, y2 = box.astype(int)
    px, py = int((x2 - x1) * pad), int((y2 - y1) * pad)
    a0, b0 = max(0, x1 - px), max(0, y1 - py)
    rec = np.ascontiguousarray(q[b0:min(H, y2 + py), a0:min(W, x2 + px)])
    p = pontos_rosto(rec)
    return None if p is None else {k: v + (a0, b0) for k, v in p.items()}


def caixa(pts, H):
    """A mesma regra do MuseTalk (preprocessing.get_landmark_and_bbox, v1.5): largura = extremos dos pontos; centro
    vertical no meio da ponte do nariz (ponto 29 dos 68); vai do queixo para cima a mesma distância; +margem embaixo."""
    tudo = np.concatenate(list(pts.values()))
    x1, x2 = float(tudo[:, 0].min()), float(tudo[:, 0].max())
    y2 = float(pts["faceContour"][:, 1].max())
    cr = pts.get("noseCrest")
    meio = cr[int(round((len(cr) - 1) * 0.67))] if cr is not None and len(cr) else tudo.mean(0)
    hy = float(meio[1])
    y1 = max(0.0, hy - (y2 - hy))
    y2 = min(H, y2 + 0.045 * (y2 - y1))
    return np.array([x1, y1, x2, y2], np.float32)


def boca_dentes(q, p):
    """Nota de um quadro como REFERÊNCIA do MuseTalk: boca aberta mostrando os dentes. No treino a referência é outro
    quadro do vídeo, com a mesma pose e a boca DIFERENTE (sample_method 'pose_similarity_and_mouth_dissimilarity');
    usar o próprio quadro (como o inference do repositório) faz o modelo copiar a boca original — sai lisa e sem
    dentes. Devolve (nota, inclinação dos olhos em graus)."""
    il, ol = p.get("innerLips"), p.get("outerLips")
    le, re_ = p.get("leftEye"), p.get("rightEye")
    rol = 0.0
    if le is not None and re_ is not None:
        d = re_.mean(0) - le.mean(0)
        rol = float(np.degrees(np.arctan2(d[1], d[0])))
        rol = rol - 180 if rol > 90 else rol + 180 if rol < -90 else rol
    if il is None or ol is None:
        return 0.0, rol
    ab = float(np.ptp(il[:, 1])) / max(1.0, float(np.ptp(ol[:, 0])))
    if ab < 0.12:
        return 0.0, rol
    x0, y0 = np.floor(ol.min(0)).astype(int)
    x1, y1 = np.ceil(ol.max(0)).astype(int)
    rec = q[max(0, y0):y1, max(0, x0):x1].astype(np.float32).mean(2)
    m = np.zeros(rec.shape, np.uint8)
    cv2.fillPoly(m, [np.round(il - (max(0, x0), max(0, y0))).astype(np.int32)], 1)
    if m.sum() < 20:
        return 0.0, rol
    claro = float(np.percentile(rec[m > 0], 75)) / max(1.0, float(np.median(rec)))     # dentes = o mais claro da boca
    return min(ab, 0.32) * claro, rol


def suavizar(arr, k=5):
    """Média móvel no tempo (a caixa do rosto não pode tremer quadro a quadro)."""
    if len(arr) < 3:
        return arr
    pad = np.concatenate([arr[:1].repeat(k // 2, 0), arr, arr[-1:].repeat(k // 2, 0)])
    ker = np.ones(k) / k
    return np.stack([np.convolve(pad[:, j], ker, mode="valid") for j in range(arr.shape[1])], 1)


def mascara(pts, box):
    """Onde a boca nova entra: a parte de baixo do rosto (da base do nariz até o queixo + a barba em volta), com borda
    suave. O contorno do queixo fica DENTRO (a boca abre e o queixo desce junto). Só no tamanho da caixa (rápido)."""
    x1, y1, x2, y2 = box.astype(int)
    m = np.zeros((y2 - y1, x2 - x1), np.float32)
    jaw = pts["faceContour"] - (x1, y1)
    nose = pts.get("nose")
    topo = (float(nose[:, 1].max()) - y1) if nose is not None and len(nose) else (y2 - y1) / 2
    cx = float(jaw[:, 0].mean())
    poly = [(x + (x - cx) * 0.07, y + 0.035 * (y2 - y1)) for x, y in jaw]                    # 7% para fora (barba)
    poly = [(poly[0][0], topo)] + poly + [(poly[-1][0], topo)]
    cv2.fillPoly(m, [np.array(poly, np.int32)], 1.0)
    m[: max(0, int(topo - 0.02 * (y2 - y1))), :] = 0
    s = max(3.0, 0.035 * (x2 - x1))
    m = cv2.GaussianBlur(m, (0, 0), s)
    h, w = m.shape                                   # a boca nova só existe dentro da caixa: zera suave nas bordas dela
    f = 2.5 * s
    ty = np.clip(np.minimum(np.arange(h), h - 1 - np.arange(h)) / f, 0, 1)
    tx = np.clip(np.minimum(np.arange(w), w - 1 - np.arange(w)) / f, 0, 1)
    return m * ty[:, None] * tx[None, :]


def casar(gen, orig, m):
    """Cor do quadro original na boca nova (a reconstrução do VAE é lisa e puxa um pouco a cor) + nitidez."""
    anel = (m > 0.05) & (m < 0.6)
    if anel.sum() > 50:
        for c in range(3):
            g, o = gen[..., c][anel], orig[..., c][anel]
            k = 0.5 + 0.5 * float(o.std()) / max(1.0, float(g.std()))                        # contraste: meio caminho
            gen[..., c] = (gen[..., c] - g.mean()) * k + o.mean()
    blur = cv2.GaussianBlur(gen, (0, 0), 1.1)
    return np.clip(cv2.addWeighted(gen, 1.55, blur, -0.55, 0), 0, 255)


def _poly_mask(shape, poly, sigma):
    m = np.zeros(shape, np.float32)
    cv2.fillPoly(m, [np.round(poly).astype(np.int32)], 1.0)
    return cv2.GaussianBlur(m, (0, 0), max(1.0, sigma))


def compor(orig, gen, p_o, p_g, box):
    """A boca nova SÓ onde ela muda (lábios, dentes e a sombra embaixo); a barba e o bigode ficam com a TEXTURA REAL
    (o MuseTalk desenha a barba borrada e mais rala — o que mais entregava). orig/gen: recortes da caixa (float32);
    p_o/p_g: pontos do rosto do original e da boca nova (coordenadas do quadro)."""
    x1, y1 = int(box[0]), int(box[1])
    h, w = orig.shape[:2]
    lab = [p["outerLips"] - (x1, y1) for p in (p_o, p_g) if p is not None and p.get("outerLips") is not None]
    if not lab:
        m = mascara(p_o, box)[..., None]
        return orig * (1 - m) + casar(gen, orig, m[..., 0]) * m
    todos = np.concatenate(lab)
    casco = cv2.convexHull(todos.astype(np.float32))[:, 0, :]
    cx, cy = todos.mean(0)
    mw, mh = float(np.ptp(todos[:, 0])), max(4.0, float(np.ptp(todos[:, 1])))
    zona = (casco - (cx, cy)) * (1.38, 1.75) + (cx, cy + 0.18 * mh)          # boca + queixinho (a boca abre p/ baixo)
    Mz = _poly_mask((h, w), zona, 0.16 * mw)
    nucleo = (casco - (cx, cy)) * 1.06 + (cx, cy)
    Mc = _poly_mask((h, w), nucleo, 0.05 * mw)
    gen = casar(gen, orig, Mz)
    sig = 1.6                                                                 # fios da barba: 1–3 px
    hf_o = orig - cv2.GaussianBlur(orig, (0, 0), sig)
    hf_g = gen - cv2.GaussianBlur(gen, (0, 0), sig)
    det = gen + (1 - Mc)[..., None] * (hf_o - hf_g)                          # fora dos lábios: textura do original
    falta = max(0.0, float(hf_o[Mc > 0.5].std()) ** 2 - float(hf_g[Mc > 0.5].std()) ** 2) ** 0.5 if (Mc > 0.5).sum() > 30 else 0
    if falta > 0.3:                                                           # nos lábios: a granulação do celular
        det += (np.random.normal(0, falta * 0.8, (h, w)) * Mc)[..., None].astype(np.float32)
    Mz = Mz[..., None]
    return orig * (1 - Mz) + det * Mz


# ---------------------------------------------------------------- trechos
def quadros(src, ss, n, W, H):
    """Os n quadros do trecho, UM DE CADA VEZ (o Mac tem 8 GB: 120 quadros 1080×1920 na memória = 750 MB + cópias)."""
    dec = subprocess.Popen([FFMPEG, "-v", "error", "-ss", f"{ss:.3f}", "-i", str(src), "-fps_mode", "passthrough",
                            "-frames:v", str(n), "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    k, ult = 0, None
    while k < n:
        b = dec.stdout.read(W * H * 3)
        if len(b) < W * H * 3:
            break
        ult = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        yield ult
        k += 1
    dec.stdout.close()
    dec.wait()
    while ult is not None and k < n:                # trecho no fim do arquivo: segura o último quadro
        yield ult
        k += 1


def alvo_do_quadro(p_o, pg, M):
    """A boca DESEJADA (lábios que o MuseTalk desenhou) no espaço canônico do quadro-base; o queixo é o do quadro-base
    (ele fica real). Sem lábios novos detectados: a boca do próprio quadro."""
    import boca
    f = pg if pg is not None and pg.get("outerLips") is not None and pg.get("innerLips") is not None else p_o
    return (boca.aplicar(M, f["outerLips"]), boca.aplicar(M, f["innerLips"]),
            boca.aplicar(M, boca._queixo(p_o["faceContour"])), f is pg)


def fase_boca(plano, d, enc, W, H):
    """Escolhe, quadro a quadro, a boca REAL dele mais parecida com a desenhada (Viterbi: sequências seguidas de
    quadros reais) e cola no quadro-base. d = o que a fase do MuseTalk deixou em <out>.boca.npz."""
    import boca
    lib, bcrops, _ = boca.carregar()
    out_c, in_c, qx = d["outer"].copy(), d["inner"].copy(), d["queixo"]
    inicio = np.concatenate([[0], np.cumsum([int(s["n"]) for s in plano["shots"]])])
    for a, b in zip(inicio, inicio[1:]):                           # suaviza o ruído do Vision (sem atravessar cortes)
        for arr in (out_c, in_c):
            if b - a >= 3:
                arr[a:b] = suavizar(arr[a:b].reshape(b - a, -1), 3).reshape(arr[a:b].shape)
    # o MuseTalk articula MENOS que ele (boca ~16% mais estreita e ~40% menos aberta — esticar só a altura deixava tudo
    # em "o"): o formato desenhado é levado para a faixa REAL dele, dimensão por dimensão (média e desvio da
    # biblioteca); o MuseTalk decide o QUANDO, a biblioteca o QUANTO
    F = boca.forma(out_c, in_c, qx)
    Fr = lib["forma"][lib["ok"]]
    k = np.clip(Fr.std(0) / np.maximum(1e-3, F.std(0)), 0.7, 2.0)
    alvos = Fr.mean(0) + (F - F.mean(0)) * k
    largura = lambda o: float(np.median(np.linalg.norm(np.subtract(*boca._cantos(o)), axis=-1)))  # noqa: E731
    print(f"rosto: boca desenhada {largura(out_c):.0f} px de largura × a dele {largura(lib['outer'][lib['ok']]):.0f} "
          f"(canônico) · ganho mediano do movimento ×{float(np.median(k)):.2f}", flush=True)
    fontes = [str(x) for x in lib["fontes"]]
    fonte_plano = []
    for sh in plano["shots"]:
        fonte_plano += [fontes.index(sh["src"]) if sh["src"] in fontes else -1] * int(sh["n"])
    esc, sig = boca.escolher(alvos, fonte_plano, set(int(x) for x in inicio[1:-1]), lib,
                             troca=float(__import__("os").environ.get("CLONE_TROCA", 4.0)))
    media, nseq = boca.continuidade(esc, lib)
    print(f"rosto: boca real — {nseq} sequências de quadros reais (média {media:.1f} quadros "
          f"seguidos), distância típica {sig:.2f}", flush=True)
    np.savez(str(Path(plano["out"]).with_suffix(".escolhas.npz")), esc=np.array(esc), outer=out_c, inner=in_c)
    cortes = set(int(x) for x in inicio[1:-1])
    seguido = lambda a, b: lib["span"][a] == lib["span"][b] and 0 <= lib["quadro"][b] - lib["quadro"][a] <= 2  # noqa: E731
    cola = lambda q, t, e: boca.colar(q, d["M"][t], bcrops[e], lib["outer"][e], d["orig_outer"][t],  # noqa: E731
                                      float(d["nariz_y"][t]), out_c[t])
    t = 0
    for si, sh in enumerate(plano["shots"]):
        for q in quadros(sh["src"], float(sh["ss"]), int(sh["n"]), W, H):
            novo = cola(q, t, esc[t])
            if t > 0 and t not in cortes and not seguido(esc[t - 1], esc[t]):
                # troca de sequência: 1 quadro meio a meio com a continuação da anterior (o "borrão" de 30 fps)
                ant = esc[t - 1] + 1 if esc[t - 1] + 1 < len(lib["span"]) and seguido(esc[t - 1], esc[t - 1] + 1) \
                    else esc[t - 1]
                novo = ((novo.astype(np.uint16) + cola(q, t, ant)) // 2).astype(np.uint8)
            enc.stdin.write(novo.tobytes())
            t += 1


@torch.no_grad()
def main():
    plano = json.loads(Path(sys.argv[1]).read_text())
    fps, W, H = int(plano.get("fps", 30)), int(plano.get("W", 1080)), int(plano.get("H", 1920))
    t0 = time.time()
    real = MODO_BOCA == "real" and bool(plano.get("biblioteca"))
    f_boca = Path(plano["out"]).with_suffix(".boca.npz")
    abrir = lambda: subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",  # noqa: E731
                                      "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "14", "-preset", "slow",
                                      "-pix_fmt", "yuv420p", plano["out"]], stdin=subprocess.PIPE)
    if real:
        sys.path.insert(0, str(Path(__file__).parent))
        import boca
        construir = lambda: boca.construir([tuple(x) for x in plano["biblioteca"]], W, H,  # noqa: E731
                                           log=lambda m: print(m, flush=True))
        if not (boca.CACHE / "modelo.npy").exists():
            construir()
        if "--so-boca" in sys.argv and f_boca.exists():            # ajuste da colagem: o MuseTalk já rodou
            construir()
            enc = abrir()
            fase_boca(plano, dict(np.load(f_boca)), enc, W, H)
            enc.stdin.close()
            enc.wait()
            print(f"rosto: ok {plano['out']} em {(time.time() - t0) / 60:.1f} min", flush=True)
            return
        modelo_cr = np.load(boca.CACHE / "modelo.npy")             # a biblioteca pode terminar enquanto o MuseTalk roda
        acum = {"outer": [], "inner": [], "queixo": [], "achou": [], "M": [], "orig_outer": [], "nariz_y": []}
    vae, unet, whisper, ap, pe = carregar()
    chunks = audio_chunks(ap, whisper, plano["audio"], fps).cpu()
    del whisper, ap                                  # o Whisper só serve para os trechos de áudio: libera a memória
    if DEV.type == "mps":
        torch.mps.empty_cache()
    total = sum(int(s["n"]) for s in plano["shots"])
    print(f"rosto: modelos em {time.time() - t0:.0f}s ({DEV}) · {total} quadros, {len(chunks)} de áudio", flush=True)
    sf = vae.config.scaling_factor
    enc = abrir()
    g, feito, t1 = 0, 0, time.time()
    for sh in plano["shots"]:
        n = int(sh["n"])
        # 1ª passada: só os pontos do rosto (a caixa precisa da média no tempo, então vem antes) e as candidatas a
        # referência (boca aberta com dentes; guardo só as 5 melhores — memória)
        pts, rols, cand = [], [], []
        for k, q in enumerate(quadros(sh["src"], float(sh["ss"]), n, W, H)):
            p = pontos_rosto(q)
            pts.append(p)
            if p is not None and MODO_REF == "dentes":
                s_, rol = boca_dentes(q, p)
                rols.append(rol)
                if s_ > 0 and (len(cand) < 5 or s_ > cand[-1][0]):
                    cand = sorted(cand + [(s_, rol, k, q.copy())], key=lambda c: -c[0])[:5]
        ok = [p for p in pts if p is not None]
        if not ok and real:
            raise SystemExit(f"rosto: sem rosto no trecho {sh['src']} {sh['ss']} — escolha outro")
        if not ok:                                   # sem rosto (raro): passa o trecho original
            for q in quadros(sh["src"], float(sh["ss"]), n, W, H):
                enc.stdin.write(q.tobytes())
            g += n
            continue
        pts = [p if p is not None else ok[0] for p in pts]
        pts += [pts[-1]] * (n - len(pts))
        boxes = suavizar(np.stack([caixa(p, H) for p in pts]))
        if real:
            Ms = boca.transformadas(pts, modelo_cr)
        ref_lat = None                                # uma referência por plano (a mesma em todos os quadros: sem cintilar)
        if cand:
            med = float(np.median(rols))
            s_, rol, kr, qr = max(cand, key=lambda c: c[0] - 0.02 * abs(c[1] - med))     # mesma pose do plano
            x1, y1, x2, y2 = boxes[kr].astype(int)
            c = cv2.resize(qr[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
            t = torch.from_numpy(c).float().permute(2, 0, 1)[None] / 127.5 - 1
            ref_lat = vae.encode(t.to(DEV).half()).latent_dist.mode() * sf
            print(f"rosto: referência do plano = quadro {kr} (boca {s_:.2f}, inclinação {rol - med:+.1f}°)", flush=True)
        del cand
        # 2ª passada: a boca nova, em lotes de B quadros
        B = int(__import__("os").environ.get("CLONE_LOTE", 2))      # 8 GB de RAM: lote pequeno = sem swap
        it = iter(quadros(sh["src"], float(sh["ss"]), n, W, H))
        for i0 in range(0, n, B):
            idx = list(range(i0, min(n, i0 + B)))
            lote = [next(it) for _ in idx]
            crops, meias = [], []
            for q, i in zip(lote, idx):
                x1, y1, x2, y2 = boxes[i].astype(int)
                c = cv2.resize(q[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
                t = torch.from_numpy(c).float().permute(2, 0, 1) / 127.5 - 1
                crops.append(t)
                mt = t.clone()
                mt[:, 128:, :] = -1.0                                # metade de baixo apagada (0 → −1 normalizado, como o MuseTalk)
                meias.append(mt)
            n_ = len(idx)
            x = torch.stack(meias + (crops if ref_lat is None else [])).to(DEV).half()
            _t = [time.time()]
            lat = vae.encode(x).latent_dist.mode() * sf                # média (não sorteio): sem tremer de um quadro ao outro
            ref = lat[n_:] if ref_lat is None else ref_lat.expand(n_, -1, -1, -1)
            lat_in = torch.cat([lat[:n_], ref], 1).half()                             # [masked | ref] → 8 canais
            aud = torch.stack([chunks[min(g + i, len(chunks) - 1)] for i in idx]).to(DEV).float()
            aud = pe(aud).half()
            sync(); _t.append(time.time())
            pred = unet(lat_in, torch.tensor([0], device=DEV), encoder_hidden_states=aud).sample
            sync(); _t.append(time.time())
            img = vae.decode(pred / sf).sample.float()
            img = ((img.clamp(-1, 1) + 1) * 127.5).permute(0, 2, 3, 1).cpu().numpy()
            _t.append(time.time())
            for k, (q0, i) in enumerate(zip(lote, idx)):
                x1, y1, x2, y2 = boxes[i].astype(int)
                q = q0.copy()
                orig = q[y1:y2, x1:x2].astype(np.float32)
                gen = cv2.resize(img[k], (x2 - x1, y2 - y1), interpolation=cv2.INTER_CUBIC)
                q[y1:y2, x1:x2] = np.clip(gen, 0, 255).astype(np.uint8)
                pg = pontos_caixa(q, boxes[i])                       # onde ficaram os lábios NOVOS
                if DUMP and (g + i) % 10 == 0:                       # material para ajustar a mistura sem rodar o modelo
                    extra = {f"o_{k_}": v for k_, v in pts[i].items()}
                    extra.update({f"g_{k_}": v for k_, v in (pg or {}).items()})
                    np.savez_compressed(Path(DUMP) / f"{g + i:04d}.npz", orig=orig.astype(np.uint8),
                                        gen=np.clip(gen, 0, 255).astype(np.uint8), box=boxes[i], **extra)
                if real:                                             # só o formato; a boca vem da biblioteca
                    o_, i_, qx_, achou = alvo_do_quadro(pts[i], pg, Ms[i])
                    for k_, v in zip(("outer", "inner", "queixo", "achou", "M", "orig_outer", "nariz_y"),
                                     (o_, i_, qx_, achou, Ms[i], pts[i]["outerLips"], pts[i]["nose"][:, 1].max())):
                        acum[k_].append(v)
                    continue
                q[y1:y2, x1:x2] = np.clip(compor(orig, gen, pts[i], pg, boxes[i]), 0, 255).astype(np.uint8)
                enc.stdin.write(q.tobytes())
            feito += n_
            if DEV.type == "mps":
                torch.mps.empty_cache()
            if DEBUG:
                _t.append(time.time())
                print('rosto[debug]: ' + ' '.join(f'{b - a:.2f}' for a, b in zip(_t, _t[1:])) + f' · mps {torch.mps.driver_allocated_memory() / 1e9:.1f} GB · rss {_rss():.1f} GB', flush=True)
            if feito % 60 < B:
                el = time.time() - t1
                print(f"rosto: {feito}/{total} quadros · {feito / max(1, el):.1f} q/s · faltam ~{(total - feito) / max(0.1, feito / max(1, el)) / 60:.1f} min", flush=True)
        g += n
        torch.mps.empty_cache() if DEV.type == "mps" else None
    if real:
        d = {k: np.array(v) for k, v in acum.items()}
        np.savez(f_boca, **d)
        del vae, unet
        if DEV.type == "mps":
            torch.mps.empty_cache()
        print(f"rosto: formato da boca em {feito} quadros ({int(d['achou'].sum())} com os lábios novos achados)", flush=True)
        construir()
        fase_boca(plano, d, enc, W, H)
    enc.stdin.close()
    enc.wait()
    print(f"rosto: ok {plano['out']} em {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()

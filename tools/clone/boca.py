"""CLONE — a BOCA REAL dele. O MuseTalk acerta o FORMATO da boca para a fala nova, mas desenha lábios lisos, dentes
borrados e barba rala (é o que denuncia a máquina). Aqui o formato dele vira só um guia: para cada quadro, a boca vem
de um quadro REAL das gravações (dentes, brilho dos lábios, barba, granulação do celular), escolhida pelo formato dos
lábios e emendada em sequências de quadros SEGUIDOS (o movimento é o dele de verdade) — a ideia do "Video Rewrite"
(Bregler, 1997) e do "Synthesizing Obama" (Suwajanakorn, 2017), com Viterbi para não trocar de fonte a todo quadro.

Biblioteca (uma vez, em clone/_cache/boca/): cada quadro de fala das gravações normalizado pelo crânio (olhos + nariz,
semelhança por mínimos quadrados, suavizada no tempo) num recorte 256×192 da região da boca; descritor = lábios (e
queixo) nessas coordenadas. Roda no .venv-clone, chamado pelo rosto.py.
"""
import json
from pathlib import Path

import cv2
import numpy as np

import rosto as R

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "clone" / "_cache" / "boca"
IOD = 140.0                       # distância entre os olhos no espaço canônico (≈ a das gravações: 131 px em 1080)
CW, CHh = 256, 192                # recorte canônico = o próprio espaço canônico: x ±0,91 IOD; os olhos ficam em
Y0 = 104.0                        # y = −Y0 (fora, acima), então o recorte vai de 0,74 a 2,11 IOD abaixo dos olhos
ESTAVEIS = ("leftEye", "rightEye", "noseCrest", "nose")


# ---------------------------------------------------------------- geometria
def _estaveis(p):
    return np.concatenate([p[k] for k in ESTAVEIS]).astype(np.float64)


def umeyama(src, dst):
    """Semelhança (escala, rotação, translação) que leva src → dst por mínimos quadrados. Devolve a matriz 2×3."""
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    cov = b.T @ a / len(src)
    U, S, Vt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(U) * np.linalg.det(Vt))
    D = np.diag([1.0, d])
    Rm = U @ D @ Vt
    s = float(np.trace(np.diag(S) @ D)) / max(1e-9, float((a ** 2).sum() / len(src)))
    t = md - s * Rm @ ms
    return np.hstack([s * Rm, t[:, None]]).astype(np.float64)


def aplicar(M, pts):
    return pts @ M[:, :2].T + M[:, 2]


def inversa(M):
    return cv2.invertAffineTransform(M.astype(np.float64))


def _por_olhos(p):
    """Semelhança inicial só pelos centros dos olhos (para montar o modelo médio do crânio)."""
    le, re_ = p["leftEye"].mean(0), p["rightEye"].mean(0)
    src = np.array([le, re_], np.float64)
    dst = np.array([[CW / 2 - IOD / 2, -Y0], [CW / 2 + IOD / 2, -Y0]], np.float64)
    return umeyama(src, dst)


def modelo_cranio(lista_p):
    """Pontos estáveis médios (olhos + nariz) no espaço canônico."""
    acc = [aplicar(_por_olhos(p), _estaveis(p)) for p in lista_p]
    return np.median(np.stack(acc), 0)


def transformadas(seq_p, modelo, k=5):
    """Uma semelhança por quadro (quadro → canônico), com os pontos estáveis suavizados no tempo (sem tremer)."""
    S = np.stack([_estaveis(p) for p in seq_p])
    if len(S) >= 3:
        pad = np.concatenate([S[:1].repeat(k // 2, 0), S, S[-1:].repeat(k // 2, 0)])
        S = np.stack([pad[i:i + len(S)] for i in range(k)]).mean(0)
    return [umeyama(s, modelo) for s in S]


def descritor(lab_out, lab_in, queixo=None):
    """Formato da boca no espaço canônico (relativo ao crânio: a abertura do queixo conta)."""
    v = [lab_out.ravel(), 1.5 * lab_in.ravel()]
    if queixo is not None:
        v.append(0.5 * queixo.ravel())
    return np.concatenate(v).astype(np.float32)


def _cantos(outer):
    """Cantos da boca (ponto mais à esquerda e mais à direita do contorno de fora), para arrays (..., N, 2)."""
    iL = outer[..., 0].argmin(-1)[..., None, None]
    iR = outer[..., 0].argmax(-1)[..., None, None]
    return (np.take_along_axis(outer, np.repeat(iL, 2, -1), -2)[..., 0, :],
            np.take_along_axis(outer, np.repeat(iR, 2, -1), -2)[..., 0, :])


def forma(outer, inner, queixo):
    """Descritor do FORMATO da boca, sem a posição: lábios e queixo relativos ao meio dos cantos (a boca escolhida é
    encaixada depois nos cantos da boca desenhada, então só o formato importa). Arrays (..., N, 2)."""
    a, b = _cantos(outer)
    c = ((a + b) / 2)[..., None, :]
    T = outer.shape[:-2]
    return np.concatenate([(outer - c).reshape(*T, -1), 1.5 * (inner - c).reshape(*T, -1),
                           0.5 * (queixo - c).reshape(*T, -1)], -1).astype(np.float32)


def _queixo(fc):
    """Os 5 pontos mais baixos do contorno do rosto, da esquerda para a direita."""
    sel = fc[np.argsort(fc[:, 1])[-5:]]
    return sel[np.argsort(sel[:, 0])]


# ---------------------------------------------------------------- biblioteca
def construir(spans, W=1080, H=1920, log=print):
    """spans = [(arquivo, início, fim)] (os trechos de fala de clone.biblioteca()). Retomável: cada trecho fica salvo
    em clone/_cache/boca/trecho_NN.* assim que termina."""
    import fcntl
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / "trava", "w") as trava:                   # outro processo construindo: espera ele terminar
        fcntl.flock(trava, fcntl.LOCK_EX)
        _construir(spans, W, H, log)


def _construir(spans, W, H, log):
    chave = json.dumps(spans)
    if (CACHE / "chave.json").exists() and (CACHE / "chave.json").read_text() != chave:
        for f in CACHE.glob("trecho_*"):                     # a lista de trechos mudou: refaz
            f.unlink()
        (CACHE / "modelo.npy").unlink(missing_ok=True)
    (CACHE / "chave.json").write_text(chave)
    fps = 30
    fontes = sorted({s for s, _, _ in spans})
    modelo = np.load(CACHE / "modelo.npy") if (CACHE / "modelo.npy").exists() else None
    for si, (src, a, b) in enumerate(spans):
        f_meta = CACHE / f"trecho_{si:02d}.npz"
        if f_meta.exists():
            continue
        k = int((b - a) * fps)
        # 1ª passada: só os pontos (um quadro por vez: um trecho de 70 s em 1080×1920 = 14 GB)
        ps = [R.pontos_rosto(q) for q in R.quadros(src, a, k, W, H)]
        bons = [p is not None and all(p.get(r) is not None for r in ESTAVEIS + ("outerLips", "innerLips", "faceContour"))
                for p in ps]
        if modelo is None:
            modelo = modelo_cranio([p for p, b_ in zip(ps, bons) if b_][:200])
            np.save(CACHE / "modelo.npy", modelo)
        cheios = [p if b_ else None for p, b_ in zip(ps, bons)]
        ult = next((p for p in cheios if p is not None), None)
        if ult is None:
            np.savez(f_meta, vazio=True)
            continue
        for j in range(len(cheios)):                       # buracos raros: o vizinho (e o quadro fica marcado ruim)
            if cheios[j] is None:
                cheios[j] = ult
            ult = cheios[j]
        Ms = transformadas(cheios, modelo)
        # 2ª passada: o recorte canônico de cada quadro, direto no disco
        tmp = CACHE / f"trecho_{si:02d}.tmp.npy"
        crops = np.lib.format.open_memmap(tmp, mode="w+", dtype=np.uint8, shape=(len(cheios), CHh, CW, 3))
        d = {k_: [] for k_ in ("desc", "outer", "inner", "quadro", "nit")}
        n = 0
        for j, q in enumerate(R.quadros(src, a, len(cheios), W, H)):
            p, M = cheios[j], Ms[j]
            crops[j] = cv2.warpAffine(q, M, (CW, CHh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
            lo, li = aplicar(M, p["outerLips"]), aplicar(M, p["innerLips"])
            bx0, by0 = np.maximum(0, lo.min(0).astype(int) - 6)
            bx1, by1 = lo.max(0).astype(int) + 6
            reg = cv2.cvtColor(np.ascontiguousarray(crops[j][by0:by1, bx0:bx1]), cv2.COLOR_RGB2GRAY)
            d["nit"].append(float(cv2.Laplacian(reg, cv2.CV_32F).var()) if reg.size > 100 else 0.0)
            d["desc"].append(descritor(lo, li, aplicar(M, _queixo(p["faceContour"]))))
            d["outer"].append(lo.astype(np.float32))
            d["inner"].append(li.astype(np.float32))
            d["quadro"].append(int(round(a * fps)) + j)
            n += 1
        crops.flush()
        del crops
        tmp.rename(CACHE / f"trecho_{si:02d}.crops.npy")
        np.savez(f_meta, n=n, ok=np.array(bons[:n]), src=fontes.index(src), **{k_: np.array(v) for k_, v in d.items()})
        log(f"boca: biblioteca {si + 1}/{len(spans)} · trecho de {n} quadros")


class _Recortes:
    """Os recortes de todos os trechos como uma lista só (cada trecho é um .npy aberto sob demanda)."""

    def __init__(self, arquivos, tamanhos):
        self.arqs, self.ini = arquivos, np.concatenate([[0], np.cumsum(tamanhos)])
        self.mm = [None] * len(arquivos)

    def __getitem__(self, i):
        t = int(np.searchsorted(self.ini, i, side="right") - 1)
        if self.mm[t] is None:
            self.mm[t] = np.load(self.arqs[t], mmap_mode="r")
        return self.mm[t][int(i - self.ini[t])]


def carregar():
    """Biblioteca inteira: meta (arrays concatenados), recortes e o modelo do crânio. Sai do conjunto o quadro sem
    rosto inteiro e o borrado (ele mexeu a cabeça: nitidez < 55% da mediana da gravação)."""
    partes, arqs, tam, span = [], [], [], []
    for f in sorted(CACHE.glob("trecho_*.npz")):
        z = np.load(f)
        if "vazio" in z.files:
            continue
        partes.append({k: z[k] for k in ("desc", "outer", "inner", "quadro", "nit", "ok")} | {"src": np.full(int(z["n"]), int(z["src"]))})
        arqs.append(f.with_suffix(".crops.npy"))
        tam.append(int(z["n"]))
        span.append(np.full(int(z["n"]), int(f.stem.split("_")[1])))
    meta = {k: np.concatenate([p[k] for p in partes]) for k in partes[0]}
    meta["span"] = np.concatenate(span)
    spans = json.loads((CACHE / "chave.json").read_text())
    meta["fontes"] = np.array(sorted({s for s, _, _ in spans}))
    ok = meta["ok"].astype(bool)
    for f in set(meta["src"].tolist()):
        m = meta["src"] == f
        ok[m] &= meta["nit"][m] >= 0.55 * np.median(meta["nit"][m])
    meta["ok"] = ok
    meta["n"] = len(ok)
    meta["queixo"] = (meta["desc"][:, -10:] / 0.5).reshape(-1, 5, 2)
    meta["forma"] = forma(meta["outer"], meta["inner"], meta["queixo"])
    return meta, _Recortes(arqs, tam), np.load(CACHE / "modelo.npy")


# ---------------------------------------------------------------- escolha (Viterbi)
def escolher(alvos, fonte_plano, cortes, lib, K=24, troca=1.4, mesma=0.15):
    """alvos: descritor desejado por quadro; fonte_plano: índice (em lib['fontes']) da gravação do plano-base de cada
    quadro (-1 se não estiver na biblioteca); cortes: quadros em que começa um plano (trocar ali é de graça).
    Custo = distância do formato + troca de fonte (exceto quadro seguinte da mesma sequência) − bônus da mesma
    gravação do plano (barba/luz do mesmo dia)."""
    D = lib["forma"]
    ok = lib["ok"]
    N = len(D)
    dist = []
    for t, a in enumerate(alvos):
        d = np.sqrt(((D - a) ** 2).mean(1))
        d[~ok] = np.inf
        if fonte_plano[t] >= 0:                                       # mesma gravação do plano: barba/luz do mesmo dia
            d = d - mesma * float(np.median(d[ok])) * (lib["src"] == fonte_plano[t])
        dist.append(d)
    sig = float(np.median([np.partition(d, 1)[0] for d in dist])) or 1.0
    # Viterbi numa passada só: as candidatas de cada quadro = as K mais parecidas + a CONTINUAÇÃO (quadro seguinte da
    # mesma gravação) das 2K melhores sequências até aqui — senão a troca era forçada e as sequências ficavam curtas
    cands = [np.argpartition(dist[0], K)[:K]]
    acc = dist[0][cands[0]] / sig
    back = []
    for t in range(1, len(alvos)):
        d = dist[t]
        pi = cands[-1]
        melhores = pi[np.argsort(acc)[:2 * K]] + 1
        melhores = melhores[melhores < N]
        melhores = melhores[(lib["span"][melhores] == lib["span"][melhores - 1]) & np.isfinite(d[melhores])]
        ci = np.unique(np.concatenate([np.argpartition(d, K)[:K], melhores]))
        seguido = (lib["span"][ci][None, :] == lib["span"][pi][:, None])
        passo = lib["quadro"][ci][None, :] - lib["quadro"][pi][:, None]
        tr = np.full((len(pi), len(ci)), 0.0 if t in cortes else troca)
        tr[seguido & (passo == 1)] = 0.0
        tr[seguido & ((passo == 0) | (passo == 2))] = 0.25 * troca
        tot = acc[:, None] + tr
        b = tot.argmin(0)
        back.append(b)
        acc = tot[b, np.arange(len(ci))] + d[ci] / sig
        cands.append(ci)
    k = int(acc.argmin())
    out = [int(cands[-1][k])]
    for t in range(len(alvos) - 2, -1, -1):
        k = int(back[t][k])
        out.append(int(cands[t][k]))
    return out[::-1], sig


def continuidade(escolhas, lib):
    """Quantos quadros seguidos (em média) cada sequência real dura — quanto maior, mais natural."""
    runs, r = [], 1
    for a, b in zip(escolhas, escolhas[1:]):
        if lib["span"][a] == lib["span"][b] and 0 <= lib["quadro"][b] - lib["quadro"][a] <= 2:
            r += 1
        else:
            runs.append(r)
            r = 1
    runs.append(r)
    return float(np.mean(runs)), len(runs)


# ---------------------------------------------------------------- colagem
def encaixe(lab_ex, lab_alvo):
    """Semelhança (canônico → canônico) que põe o meio dos cantos da boca escolhida sobre o da boca desenhada, com a
    inclinação dela. Sem mudar a escala: o canônico já é medido pelo crânio, então a boca real tem o tamanho certo
    (a do MuseTalk é ~16% mais estreita)."""
    a0, b0 = _cantos(lab_ex)
    a1, b1 = _cantos(lab_alvo)
    v0, v1 = b0 - a0, b1 - a1
    s = 1.0
    ang = np.arctan2(v1[1], v1[0]) - np.arctan2(v0[1], v0[0])
    Rm = s * np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    c0, c1 = (a0 + b0) / 2, (a1 + b1) / 2
    return np.hstack([Rm, (c1 - Rm @ c0)[:, None]])


def colar(q, M_alvo, crop, lab_ex, lab_orig, nariz_y, lab_alvo=None):
    """Põe a boca real (recorte canônico) no quadro q. M_alvo: quadro → canônico do quadro-base (suavizada);
    lab_ex: lábios do recorte (canônico); lab_orig: lábios do quadro-base (quadro); lab_alvo: lábios desenhados
    (canônico) — a boca escolhida é encaixada nos cantos deles. Devolve o quadro novo."""
    H, W = q.shape[:2]
    Mi = inversa(M_alvo)                                            # canônico → quadro
    if lab_alvo is not None:
        S = np.vstack([encaixe(lab_ex, lab_alvo), [0, 0, 1]])
        Mi = Mi @ S
    lab_ex_q = aplicar(Mi, lab_ex)
    todos = np.concatenate([lab_ex_q, lab_orig])
    c = todos.mean(0)
    mw = float(np.ptp(todos[:, 0]))
    casco = cv2.convexHull(todos.astype(np.float32))[:, 0, :]
    zona = (casco - c) * (1.30, 1.55) + c + (0, 0.06 * mw)
    x0, y0 = np.floor(zona.min(0) - 0.3 * mw).astype(int)
    x1, y1 = np.ceil(zona.max(0) + 0.3 * mw).astype(int)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    w, h = x1 - x0, y1 - y0
    A = Mi - [[0, 0, x0], [0, 0, y0]]                               # recorte canônico → região do quadro
    ex = cv2.warpAffine(np.ascontiguousarray(crop), A, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    cobre = cv2.warpAffine(np.ones(crop.shape[:2], np.float32), A, (w, h), flags=cv2.INTER_LINEAR)
    orig = q[y0:y1, x0:x1].astype(np.float32)
    ex = ex.astype(np.float32)
    duro = np.zeros((h, w), np.uint8)
    cv2.fillPoly(duro, [np.round(zona - (x0, y0)).astype(np.int32)], 1)
    yy = np.arange(h)[:, None] + y0
    teto = np.clip((yy - (nariz_y + 0.10 * mw)) / max(1.0, 0.12 * mw), 0, 1)     # nunca as narinas
    M = cv2.GaussianBlur(duro.astype(np.float32), (0, 0), max(1.0, 0.09 * mw)) * teto * (cobre > 0.99)
    # cor/luz do dia da gravação-base: campo suave medido no anel em volta (convolução normalizada)
    kk = max(3, int(0.18 * mw)) | 1
    anel = ((cv2.dilate(duro, np.ones((kk, kk), np.uint8)) - duro) * (cobre > 0.99)).astype(np.float32)
    s = max(2.0, 0.22 * mw)
    den = cv2.GaussianBlur(anel, (0, 0), s) + 1e-4
    corr = np.stack([cv2.GaussianBlur((orig[..., j] - ex[..., j]) * anel, (0, 0), s) / den for j in range(3)], -1)
    out = q.copy()
    M = M[..., None]
    out[y0:y1, x0:x1] = np.clip(orig * (1 - M) + (ex + corr) * M, 0, 255).astype(np.uint8)
    return out

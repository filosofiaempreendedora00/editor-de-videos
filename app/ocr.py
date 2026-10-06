"""Leitura de texto em imagens (prints) com o Apple Vision — local, grátis, sem internet.

Usado para: achar sozinho o trecho do vídeo em que você está LENDO um print (tela verde) e para
ocultar partes de um print (nome de marca, @, link).
"""
import re
import unicodedata
from pathlib import Path


def read(path):
    """[{text, box: (x0, y0, x1, y1) em pixels, origem no canto de cima}] por linha de texto."""
    import Quartz
    import Vision
    from Foundation import NSURL
    url = NSURL.fileURLWithPath_(str(Path(path).resolve()))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    W, H = Quartz.CGImageGetWidth(img), Quartz.CGImageGetHeight(img)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(["pt-BR", "en-US"])
    req.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    handler.performRequests_error_([req], None)
    out = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)[0]
        bb = obs.boundingBox()          # normalizado, origem embaixo
        x0, y0 = bb.origin.x * W, (1 - bb.origin.y - bb.size.height) * H
        out.append({"text": str(cand.string()), "box": (x0, y0, x0 + bb.size.width * W, y0 + bb.size.height * H),
                    "obs": obs, "cand": cand, "W": W, "H": H})
    return out


def word_box(line, start, end):
    """Caixa (pixels) de um pedaço [start:end] do texto de uma linha."""
    from Foundation import NSMakeRange
    r, _ = line["cand"].boundingBoxForRange_error_(NSMakeRange(start, end - start), None)
    if r is None:
        return line["box"]
    bb = r.boundingBox()
    W, H = line["W"], line["H"]
    x0, y0 = bb.origin.x * W, (1 - bb.origin.y - bb.size.height) * H
    return (x0, y0, x0 + bb.size.width * W, y0 + bb.size.height * H)


def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", w)


def tokens(path):
    """Palavras do print, normalizadas (sem acento/pontuação), na ordem de leitura."""
    toks = []
    for ln in read(path):
        toks += [norm(t) for t in ln["text"].split()]
    return [t for t in toks if t]

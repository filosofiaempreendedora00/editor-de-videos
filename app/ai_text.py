"""Formato compacto da transcrição para mandar a uma IA."""


def transcript_for_ai(words, deleted):
    """`[índice]palavra`, com marcas de pausa longa. Palavras já cortadas ficam de fora."""
    deleted = set(deleted)
    out = []
    prev = None
    for w in words:
        if w["i"] in deleted:
            continue
        if prev is not None and w["start"] - prev["end"] > 0.7:
            out.append(f"<pausa {w['start'] - prev['end']:.1f}s>")
        out.append(f"[{w['i']}]{w['w']}")
        prev = w
    return " ".join(out)

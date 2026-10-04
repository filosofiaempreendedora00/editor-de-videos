"""Formato compacto da transcrição para mandar a uma IA."""


def transcript_for_ai(words, deleted):
    """`[índice]palavra`, com marcas de pausa longa. Palavras já cortadas ficam de fora."""
    deleted = set(deleted)
    out = []
    prev = None
    for w in words:
        if w["i"] in deleted or not w["w"].strip():
            continue
        if prev is not None and w["start"] - prev["end"] > 0.7:
            out.append(f"<pausa {w['start'] - prev['end']:.1f}s>")
        # (?) = o reconhecimento de voz não teve certeza dessa palavra
        out.append(f"[{w['i']}]{w['w']}" + ("(?)" if w.get("p", 1) < 0.5 else ""))
        prev = w
    return " ".join(out)

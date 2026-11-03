"""CLONE — a fala na voz do Roberto, frase por frase (Chatterbox Multilingual, local). Roda no .venv-voz (Python 3.11).
Só quando ele pede (03/11: "não quero que você gaste fosfato a qualquer momento, só quando eu pedir").

Uso: .venv-voz/bin/python tools/clone/voz.py <texto.txt> <pasta_saida> [ref.wav] [exaggeration] [cfg]
Saída: <pasta>/frases/NNN.wav + <pasta>/frases.json ([{text, file, pausa}]) — a montagem (tempo, EQ da sala dele,
ruído de fundo, pausas) é feita depois por tools/clone/audio.py.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import torch
import torchaudio as ta
from num2words import num2words

ROOT = Path(__file__).resolve().parents[2]


def por_extenso(m):
    n = m.group(0).replace(".", "").replace(",", ".")
    try:
        v = float(n) if "." in n else int(n)
    except ValueError:
        return m.group(0)
    return num2words(v, lang="pt_BR").replace(",", "")


def normalizar(t):
    """Texto do roteiro → texto que a voz lê do jeito que ele falaria."""
    t = re.sub(r"\*\*|__|[“”\"«»]", "", t)                       # negrito do roteiro e aspas
    t = t.replace("…", ", ").replace("...", ", ").replace("—", ", ").replace("–", ", ")
    esc = r"(?:\s+(milhões|milhão|bilhões|bilhão|mil)\b)?"
    moeda = lambda nome: lambda m: f"{m.group(1)}{' ' + m.group(2) if m.group(2) else ''}" \
        f"{' de' if (m.group(2) or '').startswith(('milh', 'bilh')) else ''} {nome}"         # noqa: E731
    t = re.sub(r"US\$\s*([\d.,]*\d)" + esc, moeda("dólares"), t)
    t = re.sub(r"R\$\s*([\d.,]*\d)" + esc, moeda("reais"), t)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", lambda m: f"{m.group(1)} por cento", t)
    t = re.sub(r"\b(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)\b", por_extenso, t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def frases(texto):
    """Frases (com a pausa que vem depois). Frase longa (> 26 palavras) quebra na vírgula mais perto do meio."""
    out = []
    for par in [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]:
        for s in re.split(r"(?<=[.!?])\s+", normalizar(par)):
            s = s.strip()
            if not s:
                continue
            if not s[-1] in ".!?":
                s += "."
            partes = [s]
            while any(len(x.split()) > 26 for x in partes):
                y = max(partes, key=lambda x: len(x.split()))
                vs = [m.start() for m in re.finditer(r",\s", y)]
                if not vs:
                    break
                k = min(vs, key=lambda v: abs(v - len(y) / 2))
                i = partes.index(y)
                partes[i:i + 1] = [y[:k + 1].strip(), y[k + 1:].strip()]
            for k, x in enumerate(partes):
                fim = x[-1]
                pausa = 0.14 if fim == "," else (0.34 if fim in "?!" else 0.26)
                out.append({"text": x, "pausa": pausa})
        if out:
            out[-1]["pausa"] = max(out[-1]["pausa"], 0.42)      # fim de parágrafo: respiro maior
    return out


def main():
    txt, pasta = Path(sys.argv[1]), Path(sys.argv[2])
    ref = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else str(ROOT / "voz" / "ref_clone.wav")
    exg = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    cfg = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
    (pasta / "frases").mkdir(parents=True, exist_ok=True)
    lista = frases(txt.read_text(encoding="utf-8"))
    torch.manual_seed(7)
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    t0 = time.time()
    model = ChatterboxMultilingualTTS.from_pretrained(device=os.environ.get("VOZ_DEV", "cpu"))
    print(f"voz: modelo pronto em {time.time() - t0:.0f}s · {len(lista)} frases", flush=True)
    for k, f in enumerate(lista):
        f["file"] = f"frases/{k:03d}.wav"
        dst = pasta / f["file"]
        if dst.exists() and dst.stat().st_size > 2000:         # retomável: frase já gerada fica
            continue
        t1 = time.time()
        wav = model.generate(f["text"], language_id="pt", audio_prompt_path=ref, exaggeration=exg, cfg_weight=cfg)
        ta.save(str(dst), wav, model.sr)
        print(f"voz: {k + 1}/{len(lista)} {wav.shape[-1] / model.sr:.1f}s em {time.time() - t1:.0f}s · {f['text'][:60]}", flush=True)
    (pasta / "frases.json").write_text(json.dumps({"sr": model.sr, "frases": lista}, ensure_ascii=False, indent=1))
    print("voz: ok", flush=True)


if __name__ == "__main__":
    main()

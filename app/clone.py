"""CLONE DO ROBERTO (03/11) — só quando ELE pede ("não quero que você gaste fosfato a qualquer momento, só quando eu
pedir"). Texto ou roteiro → vídeo dele falando, pronto para entrar no editor como se fosse uma gravação:

  1. voz: Chatterbox Multilingual com a referência das gravações recentes (`voz/ref_clone.wav`), frase por frase
     (tools/clone/voz.py, .venv-voz);
  2. áudio: pausas naturais, o RITMO real dele, o timbre do microfone/sala e o ruído de fundo do ambiente
     (tools/clone/audio.py, .venv-clone);
  3. imagem: trechos REAIS das gravações dele (cabeça, olhos, gestos, luz, fundo) de 2,5–4,5 s cortados nas pausas
     da fala e escolhidos pelo ritmo; o MuseTalk 1.5 desenha o FORMATO da boca para a fala nova e a boca que entra é
     REAL — quadros seguidos das gravações dele com o mesmo formato (tools/clone/rosto.py + boca.py, .venv-clone,
     Apple Vision + MPS);
  4. junta: clone/<nome>/clone.mp4 (1080×1920, 30 fps).

CLI: `clone <"texto"|@arquivo.txt|V0NN> [nome]` — depois, se ele quiser: `criar_projeto` + `aplicar-edicao`.
"""
import json
import subprocess
from pathlib import Path

from .media import FFMPEG, probe

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
OUT = ROOT / "clone"
FPS = 30
# gravações reais (mesmo cenário, mesma luz): de onde saem os trechos de imagem e o "som da sala"
GRAVACOES = ["46c6c7565c", "917d676174", "38c2ae7a0a", "b66e8ae61d", "f1143271f6"]


def texto_de(arg):
    if arg.startswith("@"):
        return Path(arg[1:]).read_text(encoding="utf-8")
    if len(arg) <= 6 and arg.upper().startswith("V") and arg[1:].isdigit():
        from . import roteiros
        r = next(x for x in roteiros.load() if x["code"] == arg.upper())
        return "\n\n".join(x for x in (r.get("hook"), r.get("body"), r.get("cta")) if x)
    return arg


def _fonte(pid):
    p = json.loads((PROJECTS / pid / "project.json").read_text(encoding="utf-8"))
    src = p.get("source_orig") or p["source"]["file"]           # o V018 tem o estalo na gravação: usa a original
    return p, PROJECTS / pid / (src if isinstance(src, str) else src.get("file"))


def ritmo_real():
    """Palavras por segundo de FALA dele (sem pausas), medido nas gravações — a voz gerada segue esse ritmo."""
    pal, seg = 0, 0.0
    for pid in GRAVACOES:
        p, _ = _fonte(pid)
        ws = [w for i, w in enumerate(p["words"]) if w["w"].strip() and i not in set(p.get("deleted") or [])]
        for a, b in zip(ws, ws[1:]):
            gap = b["start"] - a["end"]
            seg += (a["end"] - a["start"]) + (gap if gap < 0.3 else 0)
            pal += 1
    return round(pal / max(1.0, seg), 2)


def biblioteca():
    """Trechos em que ele está FALANDO de frente (cabeça e olhos vivos), sem regravação: [(arquivo, início, fim)]."""
    out = []
    for pid in GRAVACOES:
        p, src = _fonte(pid)
        if not src.exists():
            continue
        dl = set(p.get("deleted") or [])
        ws = p["words"]
        i = 0
        while i < len(ws):
            if i in dl or not ws[i]["w"].strip():
                i += 1
                continue
            j = i
            while j + 1 < len(ws) and j + 1 not in dl and ws[j + 1]["start"] - ws[j]["end"] < 0.5:
                j += 1
            a, b = ws[i]["start"] + 0.05, ws[j]["end"] - 0.05
            if b - a >= 2.6 and a > 3.5:                         # fora do gancho (o estalo do V018 fica de fora)
                out.append((str(src), round(a, 2), round(b, 2)))
            i = j + 1
    return out


def envelope(arquivo, n=None):
    """Energia da fala a 30 quadros/s (log RMS) — a boca, o queixo e os gestos dele acompanham esse ritmo."""
    import numpy as np
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(arquivo), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                       capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    hop = 16000 // FPS
    k = len(x) // hop if n is None else n
    x = np.pad(x, (0, max(0, k * hop - len(x))))[:k * hop].reshape(k, hop)
    e = np.log(np.sqrt((x ** 2).mean(1) + 1e-10) + 1e-4)
    return np.convolve(e, np.ones(3) / 3, mode="same")


def _env_gravacao(src):
    import numpy as np
    cache = OUT / "_cache" / (Path(src).parent.name + ".env.npy")
    if cache.exists():
        return np.load(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    e = envelope(src)
    np.save(cache, e)
    return e


def escolher_trechos(env_nova, cortes, semente=7):
    """Para cada plano da fala nova, o trecho REAL dele cujo ritmo de fala mais se parece com o da fala nova
    (correlação da energia): o queixo, a cabeça e as mãos do original já vêm no compasso certo — só os lábios são
    refeitos. Sem repetir trecho; de preferência a mesma gravação seguida (como uma tomada só)."""
    import numpy as np
    lib = biblioteca()
    por_src = {}
    for src, a, b in lib:
        por_src.setdefault(src, []).append((int(np.ceil(a * FPS)), int(b * FPS)))
    envs = {src: _env_gravacao(src) for src in por_src}
    usados, shots, ant = [], [], None
    for a, b in zip(cortes, cortes[1:]):
        i0, i1 = int(round(a * FPS)), int(round(b * FPS))
        n = i1 - i0
        alvo = env_nova[i0:i1]
        alvo = (alvo - alvo.mean()) / (alvo.std() + 1e-6)
        melhor = None
        for src, spans in por_src.items():
            E = envs[src]
            for s0, s1 in spans:
                if s1 - s0 < n + 3:
                    continue
                W = np.lib.stride_tricks.sliding_window_view(E[s0:s1], n)
                Wz = (W - W.mean(1, keepdims=True)) / (W.std(1, keepdims=True) + 1e-6)
                c = Wz @ alvo / n
                for k in np.argsort(-c)[:12]:
                    ini = s0 + int(k)
                    if any(u[0] == src and abs(u[1] - ini) < max(n, u[2]) + FPS for u in usados):
                        continue
                    sc = float(c[k]) + (0.06 if src == ant else 0.0)
                    if melhor is None or sc > melhor[0]:
                        melhor = (sc, src, ini, float(c[k]))
                    break
        sc, src, ini, corr = melhor
        usados.append((src, ini, n))
        ant = src
        shots.append({"src": src, "ss": round(ini / FPS, 3), "n": n, "ritmo": round(corr, 2)})
    return shots


def planejar_cortes(wav, dur):
    """Pontos de corte nas PAUSAS da fala (energia baixa), com planos de 2,5–4,5 s."""
    import numpy as np
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, np.float32)
    hop = 80                                                   # 10 ms
    e = np.sqrt(np.convolve(x ** 2, np.ones(hop * 3) / (hop * 3), mode="same")[::hop] + 1e-12)
    cortes, t = [0.0], 0.0
    while dur - t > 5.2:
        lo, hi = t + 2.5, min(dur - 2.0, t + 4.5)
        a, b = int(lo * 100), int(hi * 100)
        k = a + int(np.argmin(e[a:b])) if b > a else a
        t = k / 100
        cortes.append(t)
    cortes.append(dur)
    return cortes


def gerar(arg, nome=None, exg=0.5, cfg=0.5, semente=7):
    texto = texto_de(arg).strip()
    nome = nome or (arg if len(arg) <= 6 and arg.upper().startswith("V") else "clone")
    pasta = OUT / nome
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "texto.txt").write_text(texto, encoding="utf-8")
    log = lambda m: print(f"clone: {m}", flush=True)          # noqa: E731
    # 1. voz (retomável: frases já geradas ficam)
    if not (pasta / "frases.json").exists():
        log("gerando a voz (≈ 8× o tempo da fala, na CPU)…")
        subprocess.run([str(ROOT / ".venv-voz/bin/python"), str(ROOT / "tools/clone/voz.py"), str(pasta / "texto.txt"),
                        str(pasta), str(ROOT / "voz/ref_clone.wav"), str(exg), str(cfg)], check=True)
    meta = json.loads((pasta / "frases.json").read_text())
    meta["ritmo_alvo"] = ritmo_real()
    (pasta / "frases.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    # 2. áudio com o som da sala
    gravs = [str(_fonte(pid)[1]) for pid in GRAVACOES[:3]]
    subprocess.run([str(ROOT / ".venv-clone/bin/python"), str(ROOT / "tools/clone/audio.py"), str(pasta),
                    str(pasta / "voz_final.wav"), *gravs], check=True)
    dur = float(probe(pasta / "voz_final.wav")["duration"])
    # 3. trechos reais dele, um por plano: o que tem o MESMO ritmo de fala
    cortes = planejar_cortes(pasta / "voz_final.wav", dur)
    shots = escolher_trechos(envelope(pasta / "voz_final.wav", int(round(dur * FPS))), cortes, semente)
    plano = {"audio": str(pasta / "voz_final.wav"), "fps": FPS, "W": 1080, "H": 1920, "out": str(pasta / "rosto.mp4"),
             "shots": shots, "biblioteca": biblioteca()}          # de onde saem as bocas REAIS (tools/clone/boca.py)
    (pasta / "plano_rosto.json").write_text(json.dumps(plano, ensure_ascii=False, indent=1))
    log(f"{len(shots)} planos reais seus, {dur:.1f} s — refazendo a boca (MuseTalk, MPS)…")
    subprocess.run([str(ROOT / ".venv-clone/bin/python"), str(ROOT / "tools/clone/rosto.py"), str(pasta / "plano_rosto.json")],
                   check=True)
    # 4. junta imagem + som
    final = pasta / "clone.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(pasta / "rosto.mp4"), "-i", str(pasta / "voz_final.wav"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)],
                   check=True)
    log(f"pronto: {final}")
    return final

"""O cenário surgindo atrás dele com a ONDA DO ESTALO no pós-gancho (V014 02/11): quadros reais do trecho (mesmo zoom
do render) com a onda de luz quente nascendo da mão e revelando a placa tratada; termina na placa pura (o calor segura
o último quadro).
uso: python tools/onda_cenario.py <pid> <placa.jpg> <assets/saida.mp4> [dur_onda]
No plano: {"type": "calor", "image": "<saida>.mp4", "strength": 1, "ramp": 0.004, "hold": true, "em": <1ª frase do pós-gancho>}
— aplique o plano ANTES (o script lê no projeto onde o calor começa). V014: lua_onda.mp4 (a Lua com a Terra)."""
import subprocess, sys
import cv2, numpy as np
ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
from pathlib import Path
from app import background, estalo, timeline
from app.media import FFMPEG
from app.montar_roteiro import load
pid, plate_jpg, out = sys.argv[1], sys.argv[2], sys.argv[3]
WAVE = float(sys.argv[4]) if len(sys.argv) > 4 else 0.55
pd = Path(ROOT) / "projects" / pid
p = load(pid)
c = timeline.compute(p)
fps = float(p["source"].get("fps") or 30)
W, H = 1080, 1920
cal = next(o for o in c["overlays"] if o.get("type") == "calor" and str(o.get("image", "")).startswith(Path(out).stem))
a = cal["a"]
seg = next(s for s in c["segments"] if s["out"] - 1e-6 <= a < s["out"] + s["end"] - s["start"])
k0, k1 = seg.get("kb0", 1.0), seg.get("kb1", 1.0)
nfr = max(1, round((seg["end"] - seg["start"]) * fps))
on0 = round((a - seg["out"]) * fps)
src_t = seg["start"] + on0 / fps
print("calor", round(a, 3), "trecho", round(seg["start"], 3), "src", round(src_t, 3), "kb", k0, k1, "zoom", seg["zoom"], flush=True)
# placa tratada como o fundo trocado (mesma cadeia do render: desfoque, cor puxada para a luz dele, vinheta, granulação)
gains = background.match_gains(pd / "mask_fg.mp4", Path(plate_jpg))
sig = float(p["settings"].get("bg_blur") or 1.0)
tp = Path(out).with_suffix(".placa.png")
subprocess.run([FFMPEG, "-v", "error", "-y", "-i", plate_jpg, "-vf", background.plate_chain(W, H, fps, sig, gains).replace(f",fps={fps}", "").replace(",format=yuv420p", ",format=rgb24"),
                "-frames:v", "1", str(tp)], check=True)
plate = cv2.cvtColor(cv2.imread(str(tp)), cv2.COLOR_BGR2RGB).astype(np.float32)
n = int(round(WAVE * fps)) + 2
dec = subprocess.Popen([FFMPEG, "-v", "error", "-ss", f"{src_t:.4f}", "-i", str(pd / p["source"]["file"]), "-fps_mode", "passthrough",
                        "-frames:v", str(n), "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
frames = []
while len(frames) < n:
    b = dec.stdout.read(W * H * 3)
    if len(b) < W * H * 3:
        break
    frames.append(np.frombuffer(b, np.uint8).reshape(H, W, 3))
dec.wait()
hand = None
try:
    import objc
    with objc.autorelease_pool():
        hand = estalo.hand_point(frames[0])
except Exception as e:  # noqa: BLE001
    print("mão:", e)
hand = hand or (0.5, 0.55)
print("mão em", hand, "quadros", len(frames), flush=True)
enc = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-",
                        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
for k, fr in enumerate(frames):
    z = k0 + (k1 - k0) * (on0 + k) / nfr                      # o mesmo zoom do trecho (apoio em 50% × 40%)
    if abs(z - 1) > 1e-4:
        M = np.float32([[z, 0, W / 2 * (1 - z)], [0, z, 0.4 * H * (1 - z)]])
        fr = cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    o = estalo.transition(fr, plate, k / fps, hand, W, H, dur=WAVE)
    enc.stdin.write(np.clip(o, 0, 255).astype(np.uint8).tobytes())
for _ in range(3):
    enc.stdin.write(plate.astype(np.uint8).tobytes())
enc.stdin.close(); enc.wait()
print("ok", out, flush=True)

"""Fala um texto na voz do Roberto (Chatterbox Multilingual, MIT, local). Roda no .venv-voz (Python 3.11).
Uso: .venv-voz/bin/python tools/voz_tts.py <ref.wav> <saida.wav> <texto|@arquivo.txt> [exaggeration] [cfg]
Com @lista.json ([{"text","out"}]) gera várias falas carregando o modelo uma vez só."""
import json
import sys
import time

import torch
import torchaudio as ta

ref, out, txt = sys.argv[1], sys.argv[2], sys.argv[3]
exg = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
cfg = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
import os
dev = os.environ.get("VOZ_DEV", "cpu")   # MPS falha no gerador (canais > 65536) — CPU funciona
from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: E402

t0 = time.time()
try:
    model = ChatterboxMultilingualTTS.from_pretrained(device=dev)
except Exception as e:  # noqa: BLE001
    print("mps falhou, indo de cpu:", e, flush=True)
    dev = "cpu"
    model = ChatterboxMultilingualTTS.from_pretrained(device=dev)
print(f"modelo pronto em {time.time() - t0:.0f}s ({dev})", flush=True)
jobs = json.load(open(txt[1:])) if txt.startswith("@") and txt.endswith(".json") else \
    [{"text": open(txt[1:]).read() if txt.startswith("@") else txt, "out": out}]
for j in jobs:
    t0 = time.time()
    wav = model.generate(j["text"], language_id="pt", audio_prompt_path=ref, exaggeration=j.get("exaggeration", exg),
                         cfg_weight=j.get("cfg", cfg))
    ta.save(j["out"], wav, model.sr)
    print(f"ok {j['out']} {wav.shape[-1] / model.sr:.1f}s em {time.time() - t0:.0f}s", flush=True)

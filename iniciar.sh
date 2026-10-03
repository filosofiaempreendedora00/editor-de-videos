#!/bin/bash
# Inicia o editor. Na primeira vez instala tudo sozinho (pode levar alguns minutos).
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Instalando dependências (só na primeira vez)…"
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt || exit 1
fi
[ -f .env ] || cp .env.example .env
PORT=${PORT:-8765}
(sleep 2 && open "http://localhost:$PORT") &
unset ANTHROPIC_BASE_URL
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port "$PORT"

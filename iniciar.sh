#!/bin/bash
# Inicia o editor. Na primeira vez instala tudo sozinho (pode levar alguns minutos).
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Instalando dependências (só na primeira vez)…"
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt || exit 1
fi
[ -f .env ] || cp .env.example .env
PORT=${PORT:-8765}
# Porta FIXA: mata qualquer instância antiga que esteja segurando a porta,
# pra SEMPRE abrir na mesma (http://localhost:8765 — o link do /sales aponta pra cá).
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null
(sleep 2 && open "http://localhost:$PORT") &
unset ANTHROPIC_BASE_URL
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port "$PORT"

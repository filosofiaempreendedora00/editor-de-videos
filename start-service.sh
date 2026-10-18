#!/bin/bash
# Sobe o editor em background pra launchd (sem abrir navegador). Porta fixa 8765.
cd "/Users/roberto/Projetos do Claude/Editor de vídeos" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8765

#!/bin/bash
# Sobe o editor em background pra launchd (sem abrir navegador). Porta fixa 8765.
cd "/Users/roberto/Projetos do Claude/Editor de vídeos" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
# --reload: o editor acompanha o código novo sozinho (sem ele, a prévia calculava a timeline VELHA até reiniciar o Mac)
exec .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8765 --reload --reload-dir app --reload-include "*.py"

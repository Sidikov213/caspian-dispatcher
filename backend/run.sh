#!/usr/bin/env bash
# Запуск бэкенда одной командой (macOS/Linux/Git Bash): ./run.sh
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv || python -m venv .venv
PY=.venv/bin/python; [ -x "$PY" ] || PY=.venv/Scripts/python
"$PY" -m pip install -q --disable-pip-version-check -r requirements.txt
[ -f .env ] || cp .env.example .env
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

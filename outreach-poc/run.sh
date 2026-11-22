#!/usr/bin/env bash
# One-command local start: creates .venv on first run, installs dependencies, starts the app.
#   ./run.sh            -> http://localhost:8000
#   PORT=9000 ./run.sh  -> custom port
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment (.venv)…"
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/pip install -q "anthropic==2.12.0"   # re-assert after crewai (see requirements.txt)
fi

[ -f .env ] || { [ -f .env.example ] && echo "Tip: copy .env.example to .env to enable Claude or Gemini (template mode otherwise)."; }

export CREWAI_TRACING_ENABLED=${CREWAI_TRACING_ENABLED:-false}
export OTEL_SDK_DISABLED=${OTEL_SDK_DISABLED:-true}
echo "Starting SalesAssist Outreach Assist on http://localhost:${PORT:-8000}"
exec .venv/bin/uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"

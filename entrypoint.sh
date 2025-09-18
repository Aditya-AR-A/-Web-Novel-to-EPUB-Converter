#!/usr/bin/env bash
set -euo pipefail

# Allow dynamic port (HF Spaces sets PORT)
PORT=${PORT:-7860}
WORKERS=${UVICORN_WORKERS:-1}
LOG_LEVEL=${LOG_LEVEL:-info}

echo "[entrypoint] Starting FastAPI on port ${PORT} with ${WORKERS} worker(s)"
exec uvicorn main_api:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level ${LOG_LEVEL}

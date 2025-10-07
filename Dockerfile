# syntax=docker/dockerfile:1
# Minimal production image for FastAPI + scraping
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# System deps (add more if needed: libxml2, curl, tor, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Create non-root user (uid 1000 per HF recommendation)
RUN useradd -m -u 1000 appuser
ENV HOME=/home/appuser \
    PATH=/home/appuser/.local/bin:$PATH
WORKDIR /home/appuser/app

# Install dependencies (as root first, then chown)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code then fix ownership
COPY . .
RUN chown -R appuser:appuser /home/appuser

# Switch to non-root user for runtime and create writable dirs
USER appuser
RUN chmod +x entrypoint.sh && mkdir -p books media

EXPOSE 7860

# Healthcheck (simple)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://127.0.0.1:$PORT/health || exit 1

# Allow override of workers via env if needed
ENV UVICORN_WORKERS=1

# Start the FastAPI app (working dir already set)
CMD ["./entrypoint.sh"]

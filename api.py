from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, engine
from app.routers.epubs_enhanced import router as epub_router
from app.routers.logs import router as logs_router, setup_logging
from app.storage import get_storage

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Web Novel to EPUB Converter API",
    description="Scrape web novels, convert them into EPUB files, and manage downloads with multiple storage backends.",
    version="2.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    
    # Only check storage if not using local mode
    if settings.storage_backend != "local":
        try:
            storage = get_storage()
            if hasattr(storage, 'generate_presigned_url'):
                storage.generate_presigned_url("healthcheck", expires_in=1)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Failed to initialize storage layer")
            raise RuntimeError("Storage initialization failed") from exc
    
    # Setup logging system
    setup_logging(app)


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    """Serve the main UI or JSON response based on Accept header."""
    accept = request.headers.get('accept', '')
    if 'application/json' in accept:
        return JSONResponse({"message": "Web Novel to EPUB Converter API is running."})
    
    # Try to serve static HTML
    root_dir = os.path.dirname(__file__)
    index_path = os.path.join(root_dir, 'static', 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    return HTMLResponse("<h1>Web Novel → EPUB</h1><p>API is running. UI missing.</p>", status_code=200)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def get_config() -> dict[str, object]:
    return {"ok": True, "data": {"storage_backend": settings.storage_backend}}


# Mount static files
root_dir = os.path.dirname(__file__)
static_dir = os.path.join(root_dir, "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include routers
app.include_router(epub_router, tags=["epubs"])
app.include_router(logs_router, tags=["logs"])

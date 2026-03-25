from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.db import Base, engine
from app.routers.epubs_enhanced import router as epub_router
from app.routers.logs import router as logs_router, setup_logging
from app.storage import get_storage

logger = logging.getLogger(__name__)

settings = get_settings()
startup_status = {
    "ready": False,
    "db_ok": False,
    "storage_ok": settings.storage_backend == "local",
    "error": None,
}

app = FastAPI(
    title="Web Novel to EPUB Converter API",
    description="Scrape web novels, convert them into EPUB files, and manage downloads with multiple storage backends.",
    version="2.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        mongo_uri_present = bool(os.getenv("MONGO_URI"))
        logger.info(
            "[startup.env] backend=%s db_url_prefix=%s mongo_uri_present=%s",
            settings.storage_backend,
            settings.database_url.split(":", 1)[0],
            mongo_uri_present,
        )
        if mongo_uri_present:
            logger.info("MONGO_URI is set but this build uses SQLAlchemy DATABASE_URL. MongoDB metadata is not used unless migrated to a SQL database.")

        if settings.storage_backend == "s3":
            logger.info(
                "[startup.s3] bucket_set=%s access_key_set=%s secret_set=%s endpoint_set=%s region=%s",
                bool(settings.resolved_s3_bucket),
                bool(settings.resolved_s3_access_key_id),
                bool(settings.resolved_s3_secret_access_key),
                bool(settings.resolved_s3_endpoint_url),
                settings.resolved_s3_region,
            )

        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        startup_status["db_ok"] = True

        # Only check storage if not using local mode
        if settings.storage_backend != "local":
            storage = get_storage()
            if hasattr(storage, 'generate_presigned_url'):
                storage.generate_presigned_url("healthcheck", expires_in=1)
            startup_status["storage_ok"] = True

        # Setup logging system
        setup_logging(app)
        startup_status["ready"] = True
        startup_status["error"] = None
    except Exception as exc:  # pragma: no cover - defensive guard
        startup_status["ready"] = False
        startup_status["error"] = str(exc)
        logger.exception("Startup initialization failed")
        raise


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
    status = "ok" if startup_status["ready"] else "degraded"
    return {
        "status": status,
        "db": "ok" if startup_status["db_ok"] else "error",
        "storage": "ok" if startup_status["storage_ok"] else "error",
        "backend": settings.storage_backend,
        "error": startup_status["error"] or "",
    }


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

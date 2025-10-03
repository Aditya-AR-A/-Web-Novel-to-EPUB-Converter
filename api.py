from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.db import Base, engine
from app.routers import epub_router
from app.storage import get_s3_storage

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Web Novel to EPUB Converter API",
    description="Scrape web novels, convert them into EPUB files, and manage downloads backed by AWS S3 storage.",
    version="2.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    try:
        storage = get_s3_storage()
        storage.generate_presigned_url("healthcheck", expires_in=1)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to initialize storage layer")
        raise RuntimeError("S3 storage initialization failed") from exc


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Web Novel to EPUB Converter API is running."}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(epub_router)

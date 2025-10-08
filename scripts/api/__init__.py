import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes_epub import router as epub_router
from .routes_files import router as files_router
from .routes_root import router as root_router
from .logs import setup_logging, router as logs_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Web Novel to EPUB Converter API",
        description="API to scrape web novels and convert them into EPUB files",
        version="1.0.0",
    )

    # Mount static files
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    static_dir = os.path.join(root_dir, "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Routers
    app.include_router(root_router)
    app.include_router(epub_router)
    app.include_router(files_router)
    app.include_router(logs_router)

    # Logging & websocket broadcaster
    setup_logging(app)

    return app


app = create_app()

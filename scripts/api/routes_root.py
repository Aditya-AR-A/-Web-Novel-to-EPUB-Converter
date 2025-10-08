import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from .utils import ROOT_DIR

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    accept = request.headers.get('accept', '')
    if 'application/json' in accept:
        return JSONResponse({"message": "Web Novel to EPUB Converter API is running."})
    index_path = os.path.join(ROOT_DIR, 'static', 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Web Novel → EPUB</h1><p>UI missing. Ensure static/index.html exists.</p>", status_code=200)


@router.get("/health")
def health():
    return {"status": "ok"}

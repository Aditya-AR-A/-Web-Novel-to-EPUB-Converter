from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas import (
    DownloadManyRequest,
    DownloadOneRequest,
    EpubCreateResponse,
    EpubListResponse,
)
from app.services import EpubService

router = APIRouter(prefix="/epubs", tags=["epubs"])


def get_service() -> EpubService:
    return EpubService()


def _stream_bytesio(buffer: BytesIO):
    buffer.seek(0)
    while True:
        chunk = buffer.read(1024 * 1024)
        if not chunk:
            break
        yield chunk


@router.post("/generate", response_model=EpubCreateResponse, status_code=status.HTTP_201_CREATED)
def generate_epub(
    url: str = Form(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    genres: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    cover: Optional[UploadFile] = None,
    service: EpubService = Depends(get_service),
):
    try:
        record = service.create_epub(
            url=url,
            title=title,
            author=author,
            genres=[g.strip() for g in (genres or "").split(",") if g.strip()],
            tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
            cover=cover,
        )
        return record
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/", response_model=EpubListResponse)
def list_epubs(service: EpubService = Depends(get_service)):
    records = service.list_epubs()
    return EpubListResponse(epubs=records)


@router.get("/{ebook_id}", response_model=EpubCreateResponse)
def get_epub(ebook_id: int, service: EpubService = Depends(get_service)):
    record = service.get_epub(ebook_id)
    if not record:
        raise HTTPException(status_code=404, detail="Epub not found")
    return record


@router.delete("/{ebook_id}")
def delete_epub(ebook_id: int, service: EpubService = Depends(get_service)):
    deleted = service.delete_epub(ebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Epub not found")
    return JSONResponse({"message": "Deleted", "id": ebook_id})


@router.post("/download", response_class=StreamingResponse)
def download_epub(
    request: DownloadOneRequest,
    service: EpubService = Depends(get_service),
):
    records = service.find_by_keys([request.key])
    if not records:
        raise HTTPException(status_code=404, detail="Epub not found")
    record = records[0]
    buffer = service.download_buffer(record.s3_key)
    filename = Path(record.s3_key).name
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(_stream_bytesio(buffer), media_type="application/epub+zip", headers=headers)


@router.post("/download/many", response_class=StreamingResponse)
def download_many_epubs(
    request: DownloadManyRequest,
    service: EpubService = Depends(get_service),
):
    if not request.keys:
        raise HTTPException(status_code=400, detail="keys list cannot be empty")

    records = service.find_by_keys(request.keys)
    if not records:
        raise HTTPException(status_code=404, detail="No matching epubs found")

    missing = set(request.keys) - {record.s3_key for record in records}
    if missing:
        raise HTTPException(status_code=404, detail=f"Missing epubs: {', '.join(missing)}")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for record in records:
            file_buffer = service.download_buffer(record.s3_key)
            zipf.writestr(Path(record.s3_key).name, file_buffer.getvalue())
    zip_buffer.seek(0)

    headers = {"Content-Disposition": "attachment; filename=epubs.zip"}
    return StreamingResponse(_stream_bytesio(zip_buffer), media_type="application/zip", headers=headers)


@router.post("/download/all", response_class=StreamingResponse)
def download_all_epubs(service: EpubService = Depends(get_service)):
    records = service.get_all()
    if not records:
        raise HTTPException(status_code=404, detail="No epubs available")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for record in records:
            file_buffer = service.download_buffer(record.s3_key)
            zipf.writestr(Path(record.s3_key).name, file_buffer.getvalue())
    zip_buffer.seek(0)

    headers = {"Content-Disposition": "attachment; filename=all_epubs.zip"}
    return StreamingResponse(_stream_bytesio(zip_buffer), media_type="application/zip", headers=headers)

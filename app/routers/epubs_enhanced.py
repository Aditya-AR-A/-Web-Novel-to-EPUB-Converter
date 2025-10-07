from __future__ import annotations

import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.schemas import (
    DownloadManyRequest,
    DownloadOneRequest,
)
from app.services import EpubService
from scripts import convert_to_epub, scraper
from scripts.cancellation import (
    CancelledError,
    end_job,
    request_cancel,
    request_stop,
    start_job,
)

router = APIRouter()


def get_service() -> EpubService:
    return EpubService()


def _stream_bytesio(buffer: BytesIO):
    buffer.seek(0)
    while True:
        chunk = buffer.read(1024 * 1024)
        if not chunk:
            break
        yield chunk


def success(data=None):
    return {"ok": True, "data": data}


def _serialize_epub(record):
    return {
        "id": record.id,
        "title": record.title,
        "author": record.author,
        "source_url": record.source_url,
        "storage_key": record.storage_key,
        "storage_url": record.storage_url,
        "file_size": record.file_size,
        "status": record.status,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat() if getattr(record, "created_at", None) else None,
        "updated_at": record.updated_at.isoformat() if getattr(record, "updated_at", None) else None,
    }


def error(message: str, code: str = "error", status: int = 400):
    return JSONResponse({"ok": False, "error": {"code": code, "message": message}}, status_code=status)


# ===== Database-backed endpoints (S3/Google Drive storage) =====


@router.post("/epubs/generate", status_code=status.HTTP_201_CREATED)
def generate_epub_db(
    url: str = Form(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    genres: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    cover: Optional[UploadFile] = None,
    service: EpubService = Depends(get_service),
):
    """Generate EPUB with database storage (S3/Google Drive)."""
    try:
        record = service.create_epub(
            url=url,
            title=title,
            author=author,
            genres=[g.strip() for g in (genres or "").split(",") if g.strip()],
            tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
            cover=cover,
        )
        return success({"epub": _serialize_epub(record)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class GenerateEpubRequest(BaseModel):
    url: str
    chapters_per_book: int | None = 500
    chapter_workers: int | None = 1
    chapter_limit: int | None = 0
    start_chapter: int | None = 1


@router.post("/epub/generate")
def generate_epub_local(req: GenerateEpubRequest, service: EpubService = Depends(get_service)):
    """Generate EPUB with local file storage (HuggingFace mode)."""
    settings = get_settings()
    books_dir = settings.local_storage_path
    os.makedirs(books_dir, exist_ok=True)
    
    job_id = "gen-api"
    try:
        start_job(job_id)
        metadata = scraper.get_chapter_metadata(req.url)
        if settings.storage_backend != "local":
            title = metadata.get("title") or req.url
            author = metadata.get("author")
            raw_genres = metadata.get("genres") or []
            raw_tags = metadata.get("tags") or []
            genres = raw_genres if isinstance(raw_genres, list) else [g.strip() for g in str(raw_genres).split(",") if g.strip()]
            tags = raw_tags if isinstance(raw_tags, list) else [t.strip() for t in str(raw_tags).split(",") if t.strip()]
            try:
                record = service.create_epub(
                    url=req.url,
                    title=title,
                    author=author,
                    genres=genres,
                    tags=tags,
                    cover=None,
                )
            except CancelledError as ce:
                end_job(job_id)
                return error(str(ce), code="cancelled", status=499)
            except Exception as e:
                end_job(job_id)
                return error(f"Remote generation failed: {e}", code="storage_upload_failed", status=502)
            end_job(job_id)
            return success({"epub": _serialize_epub(record)})
        chapters = scraper.get_chapters(
            req.url if (req.chapter_workers or 0) > 0 else metadata.get("starting_url", req.url),
            chapter_workers=req.chapter_workers or 0,
            chapter_limit=(req.chapter_limit if req.chapter_limit and req.chapter_limit > 0 else None),
            start_chapter=(req.start_chapter if req.start_chapter and req.start_chapter > 0 else 1)
        )
    except CancelledError as ce:
        end_job(job_id)
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        return error(f"Chapter fetch failed: {e}", code="chapter_fetch_failed", status=502)

    titles = chapters.get('title', [])
    texts = chapters.get('text', [])
    if not any(x and x.strip() for x in texts):
        end_job(job_id)
    return error("No valid chapter content collected.", code="no_chapters", status=422)
    
    try:
        convert_to_epub.to_epub(
            metadata,
            chapters,
            chapters_per_book=req.chapters_per_book or 500
        )
        end_job(job_id)
    except CancelledError as ce:
        end_job(job_id)
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        return error(f"EPUB generation failed: {e}", code="epub_generation_failed", status=500)

    base = (metadata.get('title', 'untitled').replace(' ', '_').replace(':', '_').lower())
    produced = []
    for name in sorted(os.listdir(books_dir)):
        if name.startswith(base + '-') and name.endswith('.epub'):
            produced.append(name)
    if not produced:
        for name in sorted(os.listdir(books_dir)):
            if name.endswith('.epub') and base in name:
                produced.append(name)

    return success({
        "filenames": produced,
        "count": len(produced),
        "chapters": len(titles)
    })


@router.post("/epub/cancel")
def cancel_generation():
    """Cancel ongoing EPUB generation."""
    request_cancel()
    return success({"message": "Cancellation requested"})


@router.post("/epub/stop")
def stop_generation():
    """Stop ongoing EPUB generation."""
    request_stop()
    return success({"message": "Stop requested"})


# ===== List/Get endpoints =====


@router.get("/epubs")
def list_epubs(
    offset: int = 0,
    limit: int = 100,
    service: EpubService = Depends(get_service),
):
    """List EPUBs from the configured storage backend."""
    settings = get_settings()
    if offset < 0:
        offset = 0
    if limit <= 0:
        limit = 100
    if limit > 500:
        limit = 500

    if settings.storage_backend == "local":
        books_dir = settings.local_storage_path
        if not os.path.exists(books_dir):
            return success({"epubs": [], "total": 0, "offset": offset, "limit": limit})

        files_all = [f for f in os.listdir(books_dir) if f.endswith(".epub")]
        files_all.sort()
        slice_ = files_all[offset: offset + limit]
        return success({"epubs": slice_, "total": len(files_all), "offset": offset, "limit": limit})

    records = service.list_epubs()
    sliced = records[offset: offset + limit]
    serialized = [_serialize_epub(record) for record in sliced]
    return success({"epubs": serialized, "total": len(records), "offset": offset, "limit": limit})


@router.get("/{ebook_id}")
def get_epub(ebook_id: int, service: EpubService = Depends(get_service)):
    """Get EPUB metadata from database."""
    record = service.get_epub(ebook_id)
    if not record:
        raise HTTPException(status_code=404, detail="Epub not found")
    return success({"epub": _serialize_epub(record)})


# ===== Download endpoints =====


@router.get("/epub/download")
def download_one_epub_local(name: str):
    """Download single EPUB from local storage."""
    settings = get_settings()
    books_dir = settings.local_storage_path
    epub_path = os.path.join(books_dir, name)
    
    if not os.path.exists(epub_path):
        return error("File not found", code="not_found", status=404)
    return FileResponse(epub_path, filename=name)


@router.post("/epubs/download/one", response_class=StreamingResponse)
def download_epub_db(
    request: DownloadOneRequest,
    service: EpubService = Depends(get_service),
):
    """Download EPUB from database storage."""
    records = service.find_by_keys([request.key])
    if not records:
        raise HTTPException(status_code=404, detail="Epub not found")
    record = records[0]
    buffer = service.download_buffer(record.storage_key)
    filename = Path(record.storage_key).name
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(_stream_bytesio(buffer), media_type="application/epub+zip", headers=headers)


class DownloadManyLocalRequest(BaseModel):
    names: List[str]


@router.post("/epub/download-many")
def download_many_epubs_local(req: DownloadManyLocalRequest):
    """Download multiple EPUBs from local storage as ZIP."""
    settings = get_settings()
    books_dir = settings.local_storage_path
    
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        for name in req.names:
            epub_path = os.path.join(books_dir, name)
            if os.path.exists(epub_path):
                zipf.write(epub_path, arcname=name)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=epubs.zip"})


@router.post("/epub/download-all")
def download_all_epubs_local():
    """Download all EPUBs from local storage as ZIP."""
    settings = get_settings()
    books_dir = settings.local_storage_path
    
    if not os.path.exists(books_dir):
        return error("No books directory", code="not_found", status=404)
    
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        for name in os.listdir(books_dir):
            if name.endswith(".epub"):
                epub_path = os.path.join(books_dir, name)
                zipf.write(epub_path, arcname=name)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=all_epubs.zip"})


@router.post("/epubs/download/many", response_class=StreamingResponse)
def download_many_epubs_db(
    request: DownloadManyRequest,
    service: EpubService = Depends(get_service),
):
    """Download multiple EPUBs from database storage."""
    if not request.keys:
        raise HTTPException(status_code=400, detail="keys list cannot be empty")

    records = service.find_by_keys(request.keys)
    if not records:
        raise HTTPException(status_code=404, detail="No matching epubs found")

    missing = set(request.keys) - {record.storage_key for record in records}
    if missing:
        raise HTTPException(status_code=404, detail=f"Missing epubs: {', '.join(missing)}")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for record in records:
            file_buffer = service.download_buffer(record.storage_key)
            zipf.writestr(Path(record.storage_key).name, file_buffer.getvalue())
    zip_buffer.seek(0)

    headers = {"Content-Disposition": "attachment; filename=epubs.zip"}
    return StreamingResponse(_stream_bytesio(zip_buffer), media_type="application/zip", headers=headers)


@router.post("/epubs/download/all", response_class=StreamingResponse)
def download_all_epubs_db(service: EpubService = Depends(get_service)):
    """Download all EPUBs from database storage."""
    records = service.get_all()
    if not records:
        raise HTTPException(status_code=404, detail="No epubs available")

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for record in records:
            file_buffer = service.download_buffer(record.storage_key)
            zipf.writestr(Path(record.storage_key).name, file_buffer.getvalue())
    zip_buffer.seek(0)

    headers = {"Content-Disposition": "attachment; filename=all_epubs.zip"}
    return StreamingResponse(_stream_bytesio(zip_buffer), media_type="application/zip", headers=headers)


# ===== Delete endpoints =====


@router.delete("/epubs/{ebook_id}")
def delete_epub_db(ebook_id: int, service: EpubService = Depends(get_service)):
    """Delete EPUB from database."""
    deleted = service.delete_epub(ebook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Epub not found")
    return success({"message": "Deleted", "id": ebook_id})


@router.delete("/epub")
def delete_many_epubs_local(names: List[str]):
    """Delete multiple EPUBs from local storage."""
    settings = get_settings()
    books_dir = settings.local_storage_path
    
    deleted, errors = [], []
    for name in names:
        epub_path = os.path.join(books_dir, name)
        if os.path.exists(epub_path):
            try:
                os.remove(epub_path)
                deleted.append(name)
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
        else:
            errors.append({"name": name, "error": "File not found."})
    return success({"deleted": deleted, "errors": errors})


@router.delete("/epub/all")
def delete_all_epubs_local():
    """Delete all EPUBs from local storage."""
    settings = get_settings()
    books_dir = settings.local_storage_path
    
    if not os.path.exists(books_dir):
        return success({"deleted": [], "errors": []})
    
    files = [f for f in os.listdir(books_dir) if f.endswith(".epub")]
    deleted, errors = [], []
    for name in files:
        try:
            os.remove(os.path.join(books_dir, name))
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "error": str(e)})
    return success({"deleted": deleted, "errors": errors})

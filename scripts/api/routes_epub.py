import zipfile
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from scripts import scraper, convert_to_epub
from scripts.cancellation import start_job, end_job, request_cancel, request_stop, CancelledError
from .utils import success, error, BOOKS_DIR
from scripts.db.operations import save_scraped_novel_to_db
from scripts.db.mongo import db
from scripts.storage import download_r2_bytes


router = APIRouter()
BOOKS_PATH = Path(BOOKS_DIR)


def _local_file_candidates(name: str, doc: Optional[dict] = None) -> List[Path]:
    candidates: List[Path] = []
    direct = BOOKS_PATH / name
    candidates.append(direct)

    if doc:
        local_path = doc.get("local_path")
        if local_path:
            candidates.append(Path(local_path))
        novel_key = doc.get("novel_key")
        if novel_key:
            candidates.append(BOOKS_PATH / novel_key / name)

    unique: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except FileNotFoundError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _existing_local_path(name: str, doc: Optional[dict] = None) -> Optional[str]:
    for candidate in _local_file_candidates(name, doc):
        if candidate.exists():
            return str(candidate)
    if doc is None:
        try:
            for candidate in BOOKS_PATH.rglob(name):
                if candidate.is_file():
                    return str(candidate)
        except Exception:
            return None
    return None


def _resolve_epub_source(name: str) -> tuple[Optional[str], Optional[bytes], str]:
    """Return (local_path, bytes, mime_type) for the requested EPUB."""
    mime_type = "application/epub+zip"
    initial_local = _existing_local_path(name)
    if initial_local:
        return initial_local, None, mime_type

    doc = db.novel_files.find_one(
        {"file_name": name},
        {"file_data": 1, "storage_key": 1, "mime_type": 1, "novel_key": 1, "local_path": 1},
    )

    local_path = _existing_local_path(name, doc)
    if local_path:
        return local_path, None, mime_type

    if not doc:
        return None, None, mime_type

    mime_type = doc.get("mime_type") or mime_type
    data = doc.get("file_data")
    if data:
        if isinstance(data, memoryview):
            data = data.tobytes()
        return None, bytes(data), mime_type

    storage_key = doc.get("storage_key")
    if storage_key:
        r2_bytes = download_r2_bytes(storage_key)
        if r2_bytes:
            return None, r2_bytes, mime_type

    return None, None, mime_type


class GenerateEpubRequest(BaseModel):
    url: str
    chapters_per_book: int | None = 500
    chapter_workers: int | None = 1
    chapter_limit: int | None = 0
    start_chapter: int | None = 1


@router.post("/epub/generate")
def generate_epub(req: GenerateEpubRequest):
    job_id = "gen-api"
    try:
        start_job(job_id)
        metadata = scraper.get_chapter_metadata(req.url)
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
        return error("No valid chapter content collected.", code="no_chapters", status=422)
    try:
        produced = convert_to_epub.to_epub(
            metadata,
            chapters,
            chapters_per_book=req.chapters_per_book or 500,
            output_dir=BOOKS_DIR,
        )
    except CancelledError as ce:
        end_job(job_id)
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        return error(f"EPUB generation failed: {e}", code="epub_generation_failed", status=500)

    produced = produced or []

    # Save to database
    try:
        save_scraped_novel_to_db(metadata, produced, BOOKS_DIR)
    except Exception as e:
        print(f"Failed to save to DB: {e}")  # Log but don't fail the request

    return success({
        "filenames": produced,
        "count": len(produced),
        "chapters": len(titles)
    })


class DeleteManyRequest(BaseModel):
    names: List[str]


class DownloadManyRequest(BaseModel):
    names: List[str]


@router.post("/epub/cancel")
def cancel_generation():
    request_cancel()
    return success({"message": "Cancellation requested"})


@router.post("/epub/stop")
def stop_generation():
    request_stop()
    return success({"message": "Stop requested"})


@router.get("/epub/download")
def download_one_epub(name: str):
    path, data, mime = _resolve_epub_source(name)
    if path:
        return FileResponse(path, filename=name)
    if data:
        buf = BytesIO(data)
        buf.seek(0)
        headers = {"Content-Disposition": f"attachment; filename={name}"}
        return StreamingResponse(buf, media_type=mime, headers=headers)
    return error("File not found", code="not_found", status=404)


@router.post("/epubs/download/all")
def download_all_epubs():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        docs = list(
            db.novel_files.find(
                {},
                {
                    "file_name": 1,
                    "file_data": 1,
                    "storage_key": 1,
                    "novel_key": 1,
                    "local_path": 1,
                },
            )
        )
        if not docs:
            seen: set[str] = set()
            for path in BOOKS_PATH.rglob("*.epub"):
                arcname = path.name
                if arcname in seen:
                    continue
                seen.add(arcname)
                zipf.write(path, arcname=arcname)
        else:
            for doc in docs:
                name = doc.get("file_name")
                if not name:
                    continue
                path = _existing_local_path(name, doc)
                if path:
                    zipf.write(path, arcname=name)
                    continue
                data = doc.get("file_data")
                if data:
                    if isinstance(data, memoryview):
                        data = data.tobytes()
                    zipf.writestr(name, data)
                    continue
                storage_key = doc.get("storage_key")
                if storage_key:
                    remote_bytes = download_r2_bytes(storage_key)
                    if remote_bytes:
                        zipf.writestr(name, remote_bytes)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=all_epubs.zip"})


@router.post("/epubs/download")
def download_many_epubs(req: DownloadManyRequest):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        for name in req.names:
            path = _existing_local_path(name)
            if path:
                zipf.write(path, arcname=name)
                continue
            doc = db.novel_files.find_one(
                {"file_name": name},
                {"file_data": 1, "storage_key": 1, "novel_key": 1, "local_path": 1},
            )
            if not doc:
                continue
            path = _existing_local_path(name, doc)
            if path:
                zipf.write(path, arcname=name)
                continue
            data = doc.get("file_data")
            if data:
                if isinstance(data, memoryview):
                    data = data.tobytes()
                zipf.writestr(name, data)
                continue
            storage_key = doc.get("storage_key")
            if storage_key:
                remote_bytes = download_r2_bytes(storage_key)
                if remote_bytes:
                    zipf.writestr(name, remote_bytes)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=epubs.zip"})

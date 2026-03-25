import zipfile
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from scripts import scraper, convert_to_epub
from scripts.cancellation import start_job, end_job, request_cancel, request_stop, CancelledError, session_id_var
from .utils import success, error, BOOKS_DIR
from scripts.db.operations import save_scraped_novel_to_db, generate_novel_key
from scripts.db.mongo import db
from scripts.storage import download_r2_bytes


router = APIRouter()
BOOKS_PATH = Path(BOOKS_DIR)


def _local_file_candidates(name: str, doc: Optional[dict] = None) -> List[Path]:
    candidates: List[Path] = []
    direct = BOOKS_PATH / name
    candidates.append(direct)

    if doc:
        novel_id = doc.get("novel_id")
        if novel_id:
            candidates.append(BOOKS_PATH / str(novel_id) / name)
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

    doc = db.novel_links.find_one(
        {"file_name": name},
        {"storage_key": 1, "mime_type": 1, "novel_id": 1, "novel_key": 1},
    )

    local_path = _existing_local_path(name, doc)
    if local_path:
        return local_path, None, mime_type

    if not doc:
        return None, None, mime_type

    mime_type = doc.get("mime_type") or mime_type
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
    session_id: str | None = None


@router.post("/epub/generate")
def generate_epub(req: GenerateEpubRequest):
    job_id = "gen-api"
    try:
        start_job(job_id)
        start_ch = req.start_chapter if req.start_chapter and req.start_chapter > 0 else 1
        ch_limit = req.chapter_limit if req.chapter_limit and req.chapter_limit > 0 else None
        print(f"[PROGRESS] Fetching chapters starting at ch {start_ch}" + (f", limit {ch_limit}" if ch_limit else "") + "...")
        metadata = scraper.get_chapter_metadata(req.url)
        chapters = scraper.get_chapters(
            req.url,
            metadata.get("starting_url", req.url),
            chapter_workers=req.chapter_workers or 0,
            chapter_limit=ch_limit,
            start_chapter=start_ch,
        )
    except CancelledError as ce:
        end_job(job_id)
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        return error(f"Chapter fetch failed: {e}", code="chapter_fetch_failed", status=502)

    titles = chapters.get('title', [])
    texts = chapters.get('text', [])
    valid_count = sum(1 for x in texts if x and x.strip())
    if not valid_count:
        end_job(job_id)
        return error("No valid chapter content collected.", code="no_chapters", status=422)

    print(f"[PROGRESS] Fetched {valid_count} valid chapters. Building EPUB...")
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
    end_job(job_id)

    # Save to database
    try:
        save_scraped_novel_to_db(metadata, produced, BOOKS_DIR)
    except Exception as e:
        print(f"Failed to save to DB: {e}")

    return success({
        "filenames": produced,
        "count": len(produced),
        "chapters": len(titles)
    })


class AppendEpubRequest(BaseModel):
    url: str
    start_chapter: int | None = 0          # 0 or null means "auto-detect latest"
    chapters_per_book: int | None = 500
    chapter_workers: int | None = 1
    chapter_limit: int | None = 0
    session_id: str | None = None


class ActionRequest(BaseModel):
    session_id: str | None = None


class DeleteManyRequest(BaseModel):
    names: List[str]


class DownloadManyRequest(BaseModel):
    names: List[str]


@router.post("/epub/cancel")
def cancel_generation(req: ActionRequest = None):
    request_cancel(req.session_id if req else None)
    return success({"message": "Cancellation requested"})


@router.post("/epub/stop")
def stop_generation(req: ActionRequest = None):
    request_stop(req.session_id if req else None)
    return success({"message": "Stop requested"})


@router.post("/epub/append")
def append_epub_chapters(req: AppendEpubRequest):
    """Scrape chapters starting from req.start_chapter and produce new EPUB volume(s)
    that sit alongside the existing volumes — no rebuilding of old ones."""
    job_id = "append-api"
    try:
        start_job(job_id)
        metadata = scraper.get_chapter_metadata(req.url)
        
        start_ch = req.start_chapter
        if not start_ch or start_ch <= 0:
            import re
            title_clean = metadata.get('title') or 'Unknown'
            author_clean = metadata.get('author') or 'Unknown'
            novel_key = generate_novel_key(title_clean, author_clean)
            
            links = list(db.novel_links.find({"novel_key": novel_key}, {"file_name": 1}))
            if not links:
                slug = title_clean.replace(" ", "_").replace(":", "_").lower()
                links = list(db.novel_links.find({"file_name": {"$regex": f"^{slug}-ch-"}}, {"file_name": 1}))
                
            max_ch = 0
            for link in links:
                fname = link.get("file_name", "")
                m = re.search(r'-ch-\d+-(\d+)\.epub$', fname)
                if m:
                    max_ch = max(max_ch, int(m.group(1)))
            
            start_ch = max_ch + 1 if max_ch > 0 else 1

        print(f"[APPEND] Fetching new chapters from ch {start_ch}...")
        
        ch_limit = req.chapter_limit if req.chapter_limit and req.chapter_limit > 0 else None
        chapters = scraper.get_chapters(
            req.url,
            metadata.get("starting_url", req.url),
            chapter_workers=req.chapter_workers or 0,
            chapter_limit=ch_limit,
            start_chapter=start_ch,
        )
    except CancelledError as ce:
        end_job(job_id)
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        return error(f"Chapter fetch failed: {e}", code="chapter_fetch_failed", status=502)

    texts = chapters.get('text', [])
    valid_count = sum(1 for x in texts if x and x.strip())
    if not valid_count:
        end_job(job_id)
        return error("No new chapter content found.", code="no_chapters", status=422)

    start_ch_int = start_ch if start_ch else 1
    print(f"[APPEND] Got {valid_count} new chapters starting at ch {start_ch_int}. Building...")
    try:
        produced = convert_to_epub.to_epub(
            metadata,
            chapters,
            chapters_per_book=req.chapters_per_book or 500,
            output_dir=BOOKS_DIR,
            start_chapter_offset=start_ch_int - 1,   # so filenames say ch-501-1000 etc.
        )
    except CancelledError as ce:
        end_job(job_id)
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        return error(f"EPUB append failed: {e}", code="epub_generation_failed", status=500)

    produced = produced or []
    end_job(job_id)

    try:
        save_scraped_novel_to_db(metadata, produced, BOOKS_DIR)
    except Exception as e:
        print(f"Failed to save append to DB: {e}")

    return success({
        "new_filenames": produced,
        "new_chapters": valid_count,
        "start_chapter": start_ch,
    })


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
            db.novel_links.find(
                {},
                {
                    "file_name": 1,
                    "storage_key": 1,
                    "novel_id": 1,
                    "novel_key": 1,
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
            doc = db.novel_links.find_one(
                {"file_name": name},
                {"storage_key": 1, "novel_id": 1, "novel_key": 1},
            )
            if not doc:
                continue
            path = _existing_local_path(name, doc)
            if path:
                zipf.write(path, arcname=name)
                continue
            storage_key = doc.get("storage_key")
            if storage_key:
                remote_bytes = download_r2_bytes(storage_key)
                if remote_bytes:
                    zipf.writestr(name, remote_bytes)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=epubs.zip"})

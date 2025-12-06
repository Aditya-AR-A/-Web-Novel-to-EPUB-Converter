from typing import Optional, List
from pathlib import Path
from io import BytesIO
import zipfile
import json
import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
import requests
import cloudscraper

from scripts.api.utils import success, error, BOOKS_DIR
from scripts.config import MANGA_DIR, MANGA_MANIFEST_NAME
from scripts.cancellation import start_job, end_job, request_cancel, request_stop, CancelledError
from scripts.manga.scraper import get_manga_metadata as _get_manga_metadata, get_manga_manifest as _get_manga_manifest, get_supported_sources
from scripts.db.manga_operations import save_manga_manifest, get_manga_list, get_manga_by_key, delete_manga


router = APIRouter()


def _log(msg: str):
    """Log message to stdout for the log panel."""
    print(f"[manga-api] {msg}")


def _auto_upload_to_mega(manga_key: str, chapters: list, manga_info: dict) -> dict:
    """
    Auto-upload chapter CBZs to MEGA after manga generation.
    
    Returns:
        Dict with upload results or None if failed
    """
    import time
    from scripts.storage.mega_storage import get_mega_storage
    
    try:
        mega = get_mega_storage()
        if not mega:
            return None
        
        manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
        cbz_dir = manga_dir / "cbz"
        cbz_dir.mkdir(exist_ok=True)
        
        uploaded_files = []
        failed_files = []
        
        for ch in chapters:
            ch_num = ch.get("chapter", "0")
            
            # Create the CBZ
            cbz_path = _create_chapter_cbz(manga_key, ch, manga_info, cbz_dir)
            
            if not cbz_path or not cbz_path.exists():
                failed_files.append(ch_num)
                continue
            
            # Upload to MEGA (with dedup check)
            mega_url = mega.upload_cbz(str(cbz_path), manga_key, ch_num, skip_existing=True)
            
            if mega_url:
                uploaded_files.append({
                    "chapter": ch_num,
                    "mega_url": mega_url
                })
                ch["cbz_mega_url"] = mega_url
            else:
                failed_files.append(ch_num)
            
            # Small delay to avoid rate limiting
            time.sleep(1)
        
        # Get folder link
        folder_url = mega.get_folder_link(f"manga/{manga_key}")
        
        # Update manifest
        mf = manga_dir / MANGA_MANIFEST_NAME
        if mf.exists():
            try:
                payload = json.loads(mf.read_text(encoding="utf-8"))
                payload["mega_cbz"] = {
                    "enabled": True,
                    "folder_url": folder_url,
                    "uploaded_at": __import__("datetime").datetime.utcnow().isoformat(),
                    "chapter_count": len(uploaded_files)
                }
                mf.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                _log(f"⚠️ Failed to update manifest with MEGA info: {e}")
        
        return {
            "uploaded": len(uploaded_files),
            "failed": len(failed_files),
            "folder_url": folder_url,
            "files": uploaded_files
        }
        
    except Exception as e:
        _log(f"⚠️ Auto-upload to MEGA failed: {e}")
        return None


@router.get("/manga/sources")
def list_sources():
    """Get list of supported manga sources."""
    return success(get_supported_sources())


@router.post("/manga/cancel")
def cancel_manga_generation():
    """Cancel the current manga generation immediately."""
    request_cancel()
    _log("⚠️ Manga generation cancellation requested")
    return success({"message": "Cancellation requested"})


@router.post("/manga/stop")
def stop_manga_generation():
    """Gracefully stop manga generation after current chapter."""
    request_stop()
    _log("⏸️ Manga generation stop requested (will finish current chapter)")
    return success({"message": "Stop requested"})


class GenerateMangaRequest(BaseModel):
    url: str
    translated_language: Optional[str] = None
    use_data_saver: bool = True
    chapter_limit: Optional[int] = None
    page_workers: Optional[int] = 4
    auto_upload_mega: Optional[bool] = False


@router.post("/manga/generate")
def generate_manga(req: GenerateMangaRequest):
    job_id = "manga-gen"
    _log(f"🚀 Starting manga generation for: {req.url}")
    try:
        start_job(job_id)
        _log("📖 Fetching manga metadata...")
        meta = _get_manga_metadata(req.url)
        _log(f"✅ Metadata: {meta.get('title', 'Unknown')}")
        
        _log("📚 Fetching chapter manifest...")
        manifest = _get_manga_manifest(
            req.url,
            translated_language=req.translated_language,
            use_data_saver=req.use_data_saver,
            limit=req.chapter_limit,
            page_workers=req.page_workers or 4,
        )
        chapter_count = len(manifest.get("chapters") or [])
        _log(f"✅ Found {chapter_count} chapters")
    except CancelledError as ce:
        end_job(job_id)
        _log(f"⚠️ Manga generation cancelled: {ce}")
        return error(str(ce), code="cancelled", status=499)
    except Exception as e:
        end_job(job_id)
        _log(f"❌ Manga scrape failed: {e}")
        return error(f"Manga scrape failed: {e}", code="scrape_failed", status=502)
    
    try:
        _log("💾 Saving manga manifest...")
        saved = save_manga_manifest(meta, manifest)
        _log(f"✅ Saved to: {saved.get('local_path', 'unknown')}")
        if saved.get('public_url'):
            _log(f"☁️ Uploaded to R2: {saved.get('public_url')}")
    except Exception as e:
        _log(f"⚠️ Failed to save manifest: {e}")
        saved = None
    
    # Auto-upload to MEGA if requested
    mega_result = None
    if req.auto_upload_mega and saved:
        try:
            from scripts.storage.mega_storage import get_mega_storage, is_mega_configured
            if is_mega_configured():
                _log("☁️ Auto-uploading to MEGA...")
                manga_key = saved.get("manga_key") or meta.get("manga_key")
                if manga_key:
                    # Trigger the MEGA upload
                    mega_upload_result = _auto_upload_to_mega(manga_key, manifest.get("chapters") or [], meta)
                    if mega_upload_result:
                        mega_result = mega_upload_result
                        _log(f"☁️ ✅ Auto-uploaded {mega_result.get('uploaded', 0)} chapters to MEGA")
            else:
                _log("☁️ MEGA not configured, skipping auto-upload")
        except Exception as e:
            _log(f"☁️ ⚠️ Auto-upload to MEGA failed: {e}")
    
    end_job(job_id)
    _log("🎉 Manga generation complete!")
    return success({
        "metadata": meta,
        "chapters": len(manifest.get("chapters") or []),
        "saved": saved,
        "mega_upload": mega_result,
    })


@router.get("/manga")
def list_manga(offset: int = 0, limit: int = 100, search: Optional[str] = None):
    """List manga from MongoDB (with fallback to local files)."""
    try:
        # Try MongoDB first
        result = get_manga_list(offset=offset, limit=limit, search=search)
        if result["items"]:
            return success(result)
    except Exception as e:
        print(f"MongoDB manga list failed: {e}")
    
    # Fallback to local file scan
    base = Path(str(MANGA_DIR)).resolve()
    items: List[dict] = []
    keys: List[str] = []
    
    if base.exists():
        for p in base.iterdir():
            if not p.is_dir():
                continue
            keys.append(p.name)
    
    keys.sort()
    if offset < 0:
        offset = 0
    if limit <= 0:
        limit = 100
    keys = keys[offset: offset + limit]
    
    for k in keys:
        mf = base / k / MANGA_MANIFEST_NAME
        if not mf.exists():
            continue
        try:
            raw = mf.read_text(encoding="utf-8")
        except Exception:
            raw = None
        if not raw:
            continue
        try:
            import json
            payload = json.loads(raw)
        except Exception:
            payload = None
        if not payload:
            continue
        info = payload.get("manga") or {}
        chapters = payload.get("chapters") or []
        
        # Check for cached CBZ file size
        cbz_path = base / k / f"{k}_complete.cbz"
        cbz_size = None
        cbz_size_formatted = None
        if cbz_path.exists():
            cbz_size = cbz_path.stat().st_size
            cbz_size_formatted = _format_size(cbz_size)
        
        # Check if uploaded to MEGA (CBZ mode)
        mega_cbz_enabled = payload.get("mega_cbz", {}).get("enabled", False)
        
        items.append({
            "manga_key": k,
            "title": info.get("title"),
            "author": info.get("author"),
            "artist": info.get("artist"),
            "status": info.get("status"),
            "cover_image": info.get("cover_image"),
            "chapter_count": len(chapters),
            "total_pages": sum(len(ch.get("pages") or []) for ch in chapters),
            "source_url": info.get("source_url"),
            "description": info.get("description", "")[:300] if info.get("description") else "",
            "genre": info.get("genre"),
            "cbz_size": cbz_size,
            "cbz_size_formatted": cbz_size_formatted,
            "mega_cbz_enabled": mega_cbz_enabled,
        })
    
    return success({"items": items, "total": len(items), "offset": offset, "limit": limit})


@router.get("/manga/{manga_key}")
def get_manga_details(manga_key: str):
    """Get detailed manga info by key."""
    # Try MongoDB first
    try:
        doc = get_manga_by_key(manga_key)
        if doc:
            doc.pop("_id", None)
            return success(doc)
    except Exception as e:
        print(f"MongoDB manga get failed: {e}")
    
    # Fallback to local manifest
    mf = Path(str(MANGA_DIR)).resolve() / manga_key / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        raw = mf.read_text(encoding="utf-8")
        import json
        payload = json.loads(raw)
        return success(payload)
    except Exception as e:
        return error(f"Failed to read manga: {e}", code="read_error", status=500)


@router.get("/manga/manifest/{manga_key}")
def get_manga_manifest_by_key(manga_key: str):
    """Get full manga manifest including chapters."""
    mf = Path(str(MANGA_DIR)).resolve() / manga_key / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manifest not found", code="not_found", status=404)
    try:
        raw = mf.read_text(encoding="utf-8")
        import json
        payload = json.loads(raw)
        return success(payload)
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="manifest_read_error", status=500)


@router.delete("/manga/{manga_key}")
def delete_manga_by_key(manga_key: str):
    """Delete a manga by key."""
    import shutil
    
    _log(f"🗑️ Deleting manga: {manga_key}")
    
    # Delete from MongoDB
    try:
        delete_manga(manga_key)
        _log(f"   ✅ Removed from MongoDB")
    except Exception as e:
        _log(f"   ⚠️ Failed to delete from MongoDB: {e}")
    
    # Delete local files
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    if manga_dir.exists():
        try:
            shutil.rmtree(manga_dir)
            _log(f"   ✅ Removed local files")
        except Exception as e:
            _log(f"   ❌ Failed to delete local files: {e}")
            return error(f"Failed to delete manga files: {e}", code="delete_error", status=500)
    
    _log(f"✅ Manga '{manga_key}' deleted")
    return success({"deleted": manga_key})


# ============== DOWNLOAD ROUTES ==============

# Create cloudscraper session for better download reliability
_cbz_scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)


def _generate_cbz(manga_key: str, chapters: List[dict], manga_info: dict, output_path: Path, 
                  max_retries: int = 3) -> bool:
    """
    Generate CBZ file from chapters and save to disk.
    Uses cloudscraper for better reliability with protected sites.
    Returns True if successful.
    """
    title = manga_info.get("title") or manga_key
    source_url = manga_info.get("source_url", "")
    is_webtoons = "webtoons.com" in source_url
    is_manga18 = "manga18" in source_url
    
    _log(f"   📦 Generating CBZ with {len(chapters)} chapter(s)...")
    
    # Use a temporary file first, then rename to avoid partial files
    temp_path = output_path.with_suffix('.cbz.tmp')
    
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            total_downloaded = 0
            total_failed = 0
            
            for ch in chapters:
                ch_num = ch.get("chapter") or "0"
                pages = ch.get("pages") or []
                
                _log(f"   📖 Chapter {ch_num}: {len(pages)} pages")
                
                for i, page_url in enumerate(pages):
                    success = False
                    
                    for retry in range(max_retries):
                        try:
                            headers = {
                                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                                "Accept-Language": "en-US,en;q=0.9",
                            }
                            
                            # Set appropriate referer for different sources
                            if is_webtoons:
                                headers["Referer"] = "https://www.webtoons.com/"
                            elif is_manga18:
                                headers["Referer"] = "https://manga18.club/"
                            elif "mangadex" in source_url:
                                headers["Referer"] = "https://mangadex.org/"
                            
                            # Use cloudscraper for protected sites
                            resp = _cbz_scraper.get(page_url, timeout=45, headers=headers)
                            resp.raise_for_status()
                            
                            # Validate image content
                            content = resp.content
                            if len(content) < 1000:  # Too small, probably an error page
                                raise ValueError(f"Image too small ({len(content)} bytes), likely error page")
                            
                            # Determine extension from content type or URL
                            content_type = resp.headers.get('content-type', '')
                            ext = ".jpg"
                            if 'png' in content_type or ".png" in page_url.lower():
                                ext = ".png"
                            elif 'webp' in content_type or ".webp" in page_url.lower():
                                ext = ".webp"
                            elif 'gif' in content_type or ".gif" in page_url.lower():
                                ext = ".gif"
                            
                            filename = f"Chapter_{ch_num.zfill(4)}/{i+1:04d}{ext}"
                            zf.writestr(filename, content)
                            total_downloaded += 1
                            success = True
                            break
                            
                        except Exception as e:
                            if retry < max_retries - 1:
                                import time
                                time.sleep(1)  # Wait before retry
                            else:
                                _log(f"   ⚠️ Failed page {i+1} after {max_retries} retries: {e}")
                                total_failed += 1
            
            # Add a simple ComicInfo.xml for comic readers
            comic_info = f"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>{title}</Title>
  <Writer>{manga_info.get('author', 'Unknown')}</Writer>
  <Penciller>{manga_info.get('artist', manga_info.get('author', 'Unknown'))}</Penciller>
  <Genre>{manga_info.get('genre', '')}</Genre>
  <Summary>{manga_info.get('description', '')[:500] if manga_info.get('description') else ''}</Summary>
  <PageCount>{total_downloaded}</PageCount>
</ComicInfo>"""
            zf.writestr("ComicInfo.xml", comic_info.encode('utf-8'))
        
        # Move temp file to final location
        if temp_path.exists():
            if output_path.exists():
                output_path.unlink()
            temp_path.rename(output_path)
        
        file_size = output_path.stat().st_size / (1024 * 1024)  # MB
        _log(f"   ✅ CBZ saved: {output_path.name} ({file_size:.1f} MB, {total_downloaded} pages, {total_failed} failed)")
        return True
        
    except Exception as e:
        _log(f"   ❌ CBZ generation failed: {e}")
        # Clean up temp file on failure
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        return False


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


@router.get("/manga/{manga_key}/files")
def list_manga_files(manga_key: str):
    """
    List available download files for a manga with their sizes.
    """
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    if not manga_dir.exists():
        return error("Manga not found", code="not_found", status=404)
    
    files = []
    
    # Check for complete CBZ
    complete_cbz = manga_dir / f"{manga_key}_complete.cbz"
    if complete_cbz.exists():
        stat = complete_cbz.stat()
        files.append({
            "type": "cbz",
            "name": f"{manga_key}_complete.cbz",
            "label": "Complete CBZ",
            "size": stat.st_size,
            "size_formatted": _format_size(stat.st_size),
            "url": f"/manga/{manga_key}/download/cbz"
        })
    
    # Check for split CBZ files (chapters X to Y)
    for f in manga_dir.glob(f"{manga_key}_ch*.cbz"):
        stat = f.stat()
        name = f.name
        # Parse chapter range from filename
        label = name.replace(manga_key + "_", "").replace(".cbz", "").replace("ch", "Chapter ")
        files.append({
            "type": "cbz_split",
            "name": name,
            "label": label,
            "size": stat.st_size,
            "size_formatted": _format_size(stat.st_size),
            "url": f"/manga/{manga_key}/download/file/{name}"
        })
    
    return success({"files": files, "manga_key": manga_key})


@router.get("/manga/{manga_key}/download/file/{filename}")
def download_manga_file(manga_key: str, filename: str):
    """Download a specific file from manga directory."""
    # Security: ensure filename doesn't contain path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return error("Invalid filename", code="invalid_filename", status=400)
    
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    file_path = manga_dir / filename
    
    if not file_path.exists():
        return error("File not found", code="not_found", status=404)
    
    return FileResponse(
        path=str(file_path),
        media_type="application/x-cbz" if filename.endswith('.cbz') else "application/octet-stream",
        filename=filename
    )


@router.get("/manga/{manga_key}/download/cbz")
def download_manga_cbz(manga_key: str, chapter: Optional[str] = None, 
                       chapter_start: Optional[int] = None, chapter_end: Optional[int] = None,
                       regenerate: bool = False):
    """
    Download manga chapter(s) as CBZ (Comic Book ZIP) format.
    CBZ is generated on first request and cached for subsequent downloads.
    
    Args:
        manga_key: The manga identifier
        chapter: Optional specific chapter number (for single chapter)
        chapter_start: Start chapter for range download
        chapter_end: End chapter for range download
        regenerate: Force regeneration of CBZ even if cached
    """
    _log(f"📦 CBZ download requested: {manga_key}" + (f" chapter {chapter}" if chapter else " (all chapters)"))
    
    # Load manifest
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    all_chapters = payload.get("chapters") or []
    title = manga_info.get("title") or manga_key
    
    if not all_chapters:
        return error("No chapters available", code="no_chapters", status=404)
    
    # Determine which chapters to include
    if chapter:
        # Single chapter download
        chapters = [ch for ch in all_chapters if ch.get("chapter") == chapter]
        if not chapters:
            return error(f"Chapter {chapter} not found", code="chapter_not_found", status=404)
        cbz_filename = f"{manga_key}_ch{chapter}.cbz"
    elif chapter_start is not None or chapter_end is not None:
        # Chapter range download
        start = chapter_start or 1
        end = chapter_end or len(all_chapters)
        
        chapters = []
        for ch in all_chapters:
            try:
                ch_num = int(ch.get("chapter", 0))
                if start <= ch_num <= end:
                    chapters.append(ch)
            except (ValueError, TypeError):
                continue
        
        if not chapters:
            return error(f"No chapters found in range {start}-{end}", code="no_chapters_in_range", status=404)
        
        chapters.sort(key=lambda x: int(x.get("chapter", 0)))
        cbz_filename = f"{manga_key}_ch{start}-{end}.cbz"
    else:
        # All chapters
        chapters = all_chapters
        cbz_filename = f"{manga_key}_complete.cbz"
    
    # Check for cached CBZ
    cbz_path = manga_dir / cbz_filename
    
    if cbz_path.exists() and not regenerate:
        _log(f"   📁 Serving cached CBZ: {cbz_filename}")
        # Serve cached file
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
        download_name = f"{safe_title}_Chapter_{chapter}.cbz" if chapter else f"{safe_title}_Complete.cbz"
        
        return FileResponse(
            path=str(cbz_path),
            media_type="application/x-cbz",
            filename=download_name
        )
    
    # Generate CBZ
    _log(f"   🔨 Generating CBZ (not cached)...")
    if not _generate_cbz(manga_key, chapters, manga_info, cbz_path):
        return error("Failed to generate CBZ", code="cbz_generation_failed", status=500)
    
    # Serve the generated file
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    download_name = f"{safe_title}_Chapter_{chapter}.cbz" if chapter else f"{safe_title}_Complete.cbz"
    
    _log(f"✅ CBZ ready: {download_name}")
    
    return FileResponse(
        path=str(cbz_path),
        media_type="application/x-cbz",
        filename=download_name
    )


@router.get("/manga/{manga_key}/download/pdf")
def download_manga_pdf(manga_key: str, chapter: Optional[str] = None):
    """
    Download manga chapter(s) as PDF format.
    Requires pillow library.
    """
    try:
        from PIL import Image
    except ImportError:
        return error("PDF generation requires Pillow library", code="missing_dependency", status=500)
    
    _log(f"📄 PDF download requested: {manga_key}" + (f" chapter {chapter}" if chapter else " (all chapters)"))
    
    # Load manifest
    mf = Path(str(MANGA_DIR)).resolve() / manga_key / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    chapters = payload.get("chapters") or []
    title = manga_info.get("title") or manga_key
    
    if not chapters:
        return error("No chapters available", code="no_chapters", status=404)
    
    # Filter to specific chapter if requested
    if chapter:
        chapters = [ch for ch in chapters if ch.get("chapter") == chapter]
        if not chapters:
            return error(f"Chapter {chapter} not found", code="chapter_not_found", status=404)
    
    _log(f"   Creating PDF with {len(chapters)} chapter(s)...")
    
    images = []
    for ch in chapters:
        ch_num = ch.get("chapter") or "0"
        pages = ch.get("pages") or []
        
        _log(f"   📖 Chapter {ch_num}: {len(pages)} pages")
        
        for i, page_url in enumerate(pages):
            try:
                resp = requests.get(page_url, timeout=30, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp.raise_for_status()
                
                img = Image.open(BytesIO(resp.content))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                images.append(img)
                
            except Exception as e:
                _log(f"   ⚠️ Failed to download page {i+1}: {e}")
    
    if not images:
        return error("No images could be downloaded", code="no_images", status=500)
    
    # Create PDF
    buffer = BytesIO()
    images[0].save(buffer, format='PDF', save_all=True, append_images=images[1:])
    buffer.seek(0)
    
    # Generate filename
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    if chapter:
        filename = f"{safe_title}_Chapter_{chapter}.pdf"
    else:
        filename = f"{safe_title}_Complete.pdf"
    
    _log(f"✅ PDF created: {filename}")
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/manga/{manga_key}/split")
def generate_split_cbz(manga_key: str, chapters_per_file: int = 10):
    """
    Generate split CBZ files for a manga (e.g., chapters 1-10, 11-20, etc.).
    """
    _log(f"📦 Generating split CBZ files for: {manga_key} ({chapters_per_file} chapters each)")
    
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    all_chapters = payload.get("chapters") or []
    
    if not all_chapters:
        return error("No chapters available", code="no_chapters", status=404)
    
    # Sort chapters by number
    all_chapters.sort(key=lambda x: int(x.get("chapter", "0") or "0"))
    
    generated_files = []
    total_chapters = len(all_chapters)
    
    for start_idx in range(0, total_chapters, chapters_per_file):
        end_idx = min(start_idx + chapters_per_file, total_chapters)
        chapters_slice = all_chapters[start_idx:end_idx]
        
        if not chapters_slice:
            continue
        
        start_ch = chapters_slice[0].get("chapter", str(start_idx + 1))
        end_ch = chapters_slice[-1].get("chapter", str(end_idx))
        
        cbz_filename = f"{manga_key}_ch{start_ch}-{end_ch}.cbz"
        cbz_path = manga_dir / cbz_filename
        
        # Skip if already exists
        if cbz_path.exists():
            _log(f"   ⏭️ Skipping {cbz_filename} (already exists)")
            generated_files.append({
                "filename": cbz_filename,
                "chapters": f"{start_ch}-{end_ch}",
                "size": cbz_path.stat().st_size,
                "size_formatted": _format_size(cbz_path.stat().st_size),
                "skipped": True
            })
            continue
        
        if _generate_cbz(manga_key, chapters_slice, manga_info, cbz_path):
            generated_files.append({
                "filename": cbz_filename,
                "chapters": f"{start_ch}-{end_ch}",
                "size": cbz_path.stat().st_size,
                "size_formatted": _format_size(cbz_path.stat().st_size),
                "skipped": False
            })
        else:
            _log(f"   ❌ Failed to generate {cbz_filename}")
    
    _log(f"✅ Split CBZ generation complete: {len(generated_files)} files")
    
    return success({
        "manga_key": manga_key,
        "files": generated_files,
        "total_files": len(generated_files)
    })


@router.get("/manga/{manga_key}/chapters")
def get_manga_chapters(manga_key: str):
    """Get list of chapters for a manga (without page URLs for lighter response)."""
    mf = Path(str(MANGA_DIR)).resolve() / manga_key / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    chapters = payload.get("chapters") or []
    chapter_list = []
    
    for ch in chapters:
        chapter_list.append({
            "chapter": ch.get("chapter"),
            "title": ch.get("title"),
            "volume": ch.get("volume"),
            "language": ch.get("translatedLanguage"),
            "pages": len(ch.get("pages") or []),
            "published_at": ch.get("publishAt"),
        })
    
    return success({
        "manga_key": manga_key,
        "chapters": chapter_list,
        "total": len(chapter_list)
    })


@router.get("/manga/{manga_key}/chapter/{chapter_num}/pages")
def get_chapter_pages(manga_key: str, chapter_num: str):
    """Get page URLs for a specific chapter."""
    mf = Path(str(MANGA_DIR)).resolve() / manga_key / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    chapters = payload.get("chapters") or []
    for ch in chapters:
        if ch.get("chapter") == chapter_num:
            return success({
                "chapter": chapter_num,
                "title": ch.get("title"),
                "pages": ch.get("pages") or [],
                "total_pages": len(ch.get("pages") or [])
            })
    
    return error(f"Chapter {chapter_num} not found", code="chapter_not_found", status=404)


# ============== MEGA STORAGE ROUTES ==============

@router.get("/manga/mega/status")
def mega_status():
    """Check MEGA storage configuration and quota."""
    from scripts.storage.mega_storage import is_mega_configured, get_mega_storage
    
    if not is_mega_configured():
        return success({
            "configured": False,
            "message": "MEGA credentials not configured. Set MEGA_EMAIL and MEGA_PASSWORD environment variables."
        })
    
    try:
        mega = get_mega_storage()
        if mega:
            quota = mega.get_storage_quota()
            return success({
                "configured": True,
                "connected": True,
                "quota": quota
            })
    except Exception as e:
        return success({
            "configured": True,
            "connected": False,
            "error": str(e)
        })
    
    return success({"configured": True, "connected": False})


def _create_chapter_cbz(manga_key: str, chapter: dict, manga_info: dict, output_dir: Path) -> Optional[Path]:
    """
    Create a CBZ file for a single chapter.
    Downloads images and packages them into a CBZ.
    """
    import time
    
    ch_num = chapter.get("chapter", "0")
    pages = chapter.get("pages") or []
    
    if not pages:
        return None
    
    cbz_filename = f"ch_{ch_num}.cbz"
    cbz_path = output_dir / cbz_filename
    
    # Skip if already exists
    if cbz_path.exists():
        _log(f"   📦 Chapter {ch_num} CBZ already exists")
        return cbz_path
    
    _log(f"   📥 Creating CBZ for chapter {ch_num} ({len(pages)} pages)...")
    
    # Determine referer
    source_url = manga_info.get("source_url", "")
    referer = None
    if "webtoons.com" in source_url:
        referer = "https://www.webtoons.com/"
    elif "manga18" in source_url:
        referer = "https://manga18.club/"
    elif "mangadex" in source_url:
        referer = "https://mangadex.org/"
    
    # Create scraper
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
    
    # Download images and create CBZ
    try:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, page_url in enumerate(pages):
                # Determine extension
                ext = ".jpg"
                if ".png" in page_url.lower():
                    ext = ".png"
                elif ".webp" in page_url.lower():
                    ext = ".webp"
                
                filename = f"{idx+1:04d}{ext}"
                
                # Download image
                headers = {"Accept": "image/*"}
                if referer:
                    headers["Referer"] = referer
                
                for attempt in range(3):
                    try:
                        resp = scraper.get(page_url, timeout=30, headers=headers)
                        resp.raise_for_status()
                        if len(resp.content) > 1000:
                            zf.writestr(filename, resp.content)
                            break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(1)
                        else:
                            _log(f"      ⚠️ Failed to download page {idx+1}")
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
        
        # Write CBZ to disk
        buffer.seek(0)
        cbz_path.write_bytes(buffer.getvalue())
        _log(f"   ✅ Created: {cbz_filename}")
        return cbz_path
        
    except Exception as e:
        _log(f"   ❌ Failed to create CBZ: {e}")
        return None


@router.post("/manga/{manga_key}/create-chapter-cbz")
def create_chapter_cbz(manga_key: str, chapter_start: Optional[str] = None, chapter_end: Optional[str] = None):
    """
    Create chapter-wise CBZ files for a manga.
    
    Args:
        manga_key: Manga identifier
        chapter_start: Start chapter (optional, defaults to first)
        chapter_end: End chapter (optional, defaults to last)
    """
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    chapters = payload.get("chapters") or []
    
    if not chapters:
        return error("No chapters in manifest", code="no_chapters", status=404)
    
    # Create cbz directory
    cbz_dir = manga_dir / "cbz"
    cbz_dir.mkdir(exist_ok=True)
    
    # Filter chapters by range
    if chapter_start or chapter_end:
        filtered = []
        for ch in chapters:
            ch_num = ch.get("chapter", "0")
            try:
                ch_float = float(ch_num)
                start_ok = not chapter_start or ch_float >= float(chapter_start)
                end_ok = not chapter_end or ch_float <= float(chapter_end)
                if start_ok and end_ok:
                    filtered.append(ch)
            except:
                filtered.append(ch)
        chapters = filtered
    
    _log(f"📦 Creating {len(chapters)} chapter CBZ files for: {manga_key}")
    
    created_cbz = []
    for ch in chapters:
        cbz_path = _create_chapter_cbz(manga_key, ch, manga_info, cbz_dir)
        if cbz_path:
            created_cbz.append({
                "chapter": ch.get("chapter"),
                "filename": cbz_path.name,
                "size": cbz_path.stat().st_size,
                "path": str(cbz_path)
            })
    
    return success({
        "manga_key": manga_key,
        "cbz_created": len(created_cbz),
        "files": created_cbz
    })


@router.post("/manga/{manga_key}/upload-cbz-to-mega")
def upload_cbz_to_mega(manga_key: str, chapter_start: Optional[str] = None, chapter_end: Optional[str] = None):
    """
    Create chapter-wise CBZ files and upload them to MEGA.
    
    Args:
        manga_key: Manga identifier
        chapter_start: Start chapter (optional)
        chapter_end: End chapter (optional)
    """
    from scripts.storage.mega_storage import get_mega_storage, is_mega_configured
    
    if not is_mega_configured():
        return error("MEGA credentials not configured", code="mega_not_configured", status=400)
    
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    chapters = payload.get("chapters") or []
    
    if not chapters:
        return error("No chapters in manifest", code="no_chapters", status=404)
    
    # Filter chapters by range
    if chapter_start or chapter_end:
        filtered = []
        for ch in chapters:
            ch_num = ch.get("chapter", "0")
            try:
                ch_float = float(ch_num)
                start_ok = not chapter_start or ch_float >= float(chapter_start)
                end_ok = not chapter_end or ch_float <= float(chapter_end)
                if start_ok and end_ok:
                    filtered.append(ch)
            except:
                filtered.append(ch)
        chapters = filtered
    
    # Create cbz directory
    cbz_dir = manga_dir / "cbz"
    cbz_dir.mkdir(exist_ok=True)
    
    _log(f"☁️ Starting MEGA CBZ upload for: {manga_key} ({len(chapters)} chapters)")
    
    # Get MEGA storage
    try:
        mega = get_mega_storage()
        if not mega:
            return error("Failed to connect to MEGA", code="mega_connection_failed", status=500)
    except Exception as e:
        return error(f"MEGA connection error: {e}", code="mega_error", status=500)
    
    uploaded_files = []
    failed_files = []
    
    import time
    
    for ch in chapters:
        ch_num = ch.get("chapter", "0")
        
        # First create the CBZ
        cbz_path = _create_chapter_cbz(manga_key, ch, manga_info, cbz_dir)
        
        if not cbz_path or not cbz_path.exists():
            failed_files.append(ch_num)
            continue
        
        # Upload to MEGA
        mega_url = mega.upload_cbz(str(cbz_path), manga_key, ch_num)
        
        if mega_url:
            uploaded_files.append({
                "chapter": ch_num,
                "filename": cbz_path.name,
                "mega_url": mega_url,
                "size": cbz_path.stat().st_size
            })
            
            # Update chapter in manifest
            ch["cbz_mega_url"] = mega_url
        else:
            failed_files.append(ch_num)
        
        # Delay between uploads to avoid rate limiting
        time.sleep(2)
    
    # Get folder link for easy download
    folder_url = mega.get_folder_link(f"manga/{manga_key}")
    
    # Save updated manifest
    try:
        payload["mega_cbz"] = {
            "enabled": True,
            "folder_url": folder_url,
            "uploaded_at": __import__("datetime").datetime.utcnow().isoformat(),
            "chapter_count": len(uploaded_files)
        }
        mf.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        _log(f"⚠️ Failed to update manifest: {e}")
    
    _log(f"✅ MEGA upload complete: {len(uploaded_files)} CBZ files uploaded, {len(failed_files)} failed")
    
    return success({
        "manga_key": manga_key,
        "uploaded": len(uploaded_files),
        "failed": len(failed_files),
        "folder_url": folder_url,
        "files": uploaded_files
    })


@router.get("/manga/{manga_key}/mega-folder")
def get_mega_folder(manga_key: str):
    """Get MEGA folder URL for direct download."""
    mf = Path(str(MANGA_DIR)).resolve() / manga_key / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    mega_cbz = payload.get("mega_cbz") or {}
    
    if not mega_cbz.get("enabled"):
        return error("Manga not uploaded to MEGA yet", code="not_uploaded", status=404)
    
    return success({
        "manga_key": manga_key,
        "folder_url": mega_cbz.get("folder_url"),
        "chapter_count": mega_cbz.get("chapter_count", 0),
        "uploaded_at": mega_cbz.get("uploaded_at")
    })


@router.get("/manga/{manga_key}/cbz-list")
def list_chapter_cbz(manga_key: str):
    """List available chapter CBZ files (local and MEGA)."""
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    chapters = payload.get("chapters") or []
    cbz_dir = manga_dir / "cbz"
    
    cbz_list = []
    for ch in chapters:
        ch_num = ch.get("chapter", "0")
        cbz_filename = f"ch_{ch_num}.cbz"
        local_path = cbz_dir / cbz_filename
        
        cbz_info = {
            "chapter": ch_num,
            "title": ch.get("title"),
            "pages": len(ch.get("pages") or []),
            "local_exists": local_path.exists(),
            "local_size": local_path.stat().st_size if local_path.exists() else None,
            "mega_url": ch.get("cbz_mega_url"),
        }
        cbz_list.append(cbz_info)
    
    mega_cbz = payload.get("mega_cbz") or {}
    
    return success({
        "manga_key": manga_key,
        "mega_folder_url": mega_cbz.get("folder_url"),
        "mega_enabled": mega_cbz.get("enabled", False),
        "chapters": cbz_list
    })


@router.get("/manga/{manga_key}/download/chapter/{chapter_num}")
def download_chapter_cbz(manga_key: str, chapter_num: str):
    """Download a single chapter CBZ file."""
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    cbz_dir = manga_dir / "cbz"
    cbz_path = cbz_dir / f"ch_{chapter_num}.cbz"
    
    if cbz_path.exists():
        return FileResponse(
            path=str(cbz_path),
            media_type="application/zip",
            filename=cbz_path.name
        )
    
    # Try to create it on the fly
    mf = manga_dir / MANGA_MANIFEST_NAME
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except:
        return error("Failed to read manifest", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    chapters = payload.get("chapters") or []
    
    for ch in chapters:
        if ch.get("chapter") == chapter_num:
            cbz_dir.mkdir(exist_ok=True)
            cbz_path = _create_chapter_cbz(manga_key, ch, manga_info, cbz_dir)
            if cbz_path and cbz_path.exists():
                return FileResponse(
                    path=str(cbz_path),
                    media_type="application/zip",
                    filename=cbz_path.name
                )
    
    return error(f"Chapter {chapter_num} not found", code="chapter_not_found", status=404)


@router.get("/manga/{manga_key}/download/range")
def download_chapter_range(
    manga_key: str, 
    from_chapter: Optional[str] = None, 
    to_chapter: Optional[str] = None
):
    """
    Download multiple chapters as a single ZIP containing CBZ files.
    
    Args:
        manga_key: Manga identifier
        from_chapter: Start chapter number (inclusive, optional - defaults to first)
        to_chapter: End chapter number (inclusive, optional - defaults to last)
    """
    import zipfile
    import tempfile
    
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:
        return error(f"Failed to read manifest: {e}", code="read_error", status=500)
    
    manga_info = payload.get("manga") or {}
    chapters = payload.get("chapters") or []
    
    if not chapters:
        return error("No chapters available", code="no_chapters", status=404)
    
    # Sort chapters numerically
    def chapter_sort_key(ch):
        try:
            return float(ch.get("chapter", "0"))
        except:
            return 0
    
    chapters_sorted = sorted(chapters, key=chapter_sort_key)
    
    # Filter by range
    filtered_chapters = []
    for ch in chapters_sorted:
        ch_num = ch.get("chapter", "0")
        try:
            ch_float = float(ch_num)
            start_ok = not from_chapter or ch_float >= float(from_chapter)
            end_ok = not to_chapter or ch_float <= float(to_chapter)
            if start_ok and end_ok:
                filtered_chapters.append(ch)
        except:
            # Non-numeric chapters: include if no range specified
            if not from_chapter and not to_chapter:
                filtered_chapters.append(ch)
    
    if not filtered_chapters:
        return error("No chapters in specified range", code="no_chapters_in_range", status=404)
    
    # Create CBZ directory
    cbz_dir = manga_dir / "cbz"
    cbz_dir.mkdir(exist_ok=True)
    
    # Create temp file for the ZIP
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip_path = temp_zip.name
    temp_zip.close()
    
    _log(f"📦 Creating range download for {manga_key}: {len(filtered_chapters)} chapters")
    
    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zf:
            for ch in filtered_chapters:
                ch_num = ch.get("chapter", "0")
                cbz_filename = f"ch_{ch_num}.cbz"
                cbz_path = cbz_dir / cbz_filename
                
                # Create CBZ if it doesn't exist
                if not cbz_path.exists():
                    cbz_path = _create_chapter_cbz(manga_key, ch, manga_info, cbz_dir)
                
                if cbz_path and cbz_path.exists():
                    zf.write(cbz_path, cbz_filename)
                    _log(f"   Added: {cbz_filename}")
        
        # Determine filename
        range_str = ""
        if from_chapter and to_chapter:
            range_str = f"_ch{from_chapter}-{to_chapter}"
        elif from_chapter:
            range_str = f"_ch{from_chapter}-end"
        elif to_chapter:
            range_str = f"_ch1-{to_chapter}"
        
        download_filename = f"{manga_key}{range_str}.zip"
        
        return FileResponse(
            path=temp_zip_path,
            media_type="application/zip",
            filename=download_filename,
            background=BackgroundTask(lambda: os.unlink(temp_zip_path))
        )
        
    except Exception as e:
        # Clean up on error
        try:
            os.unlink(temp_zip_path)
        except:
            pass
        return error(f"Failed to create ZIP: {e}", code="zip_error", status=500)


@router.get("/manga/{manga_key}/chapters-info")
def get_chapters_info(manga_key: str):
    """Get chapter information for range selection."""
    manga_dir = Path(str(MANGA_DIR)).resolve() / manga_key
    mf = manga_dir / MANGA_MANIFEST_NAME
    
    if not mf.exists():
        return error("Manga not found", code="not_found", status=404)
    
    try:
        payload = json.loads(mf.read_text(encoding="utf-8"))
    except:
        return error("Failed to read manifest", code="read_error", status=500)
    
    chapters = payload.get("chapters") or []
    
    # Sort chapters numerically
    def chapter_sort_key(ch):
        try:
            return float(ch.get("chapter", "0"))
        except:
            return 0
    
    chapters_sorted = sorted(chapters, key=chapter_sort_key)
    
    chapter_list = []
    for ch in chapters_sorted:
        ch_num = ch.get("chapter", "0")
        cbz_path = manga_dir / "cbz" / f"ch_{ch_num}.cbz"
        chapter_list.append({
            "chapter": ch_num,
            "title": ch.get("title", f"Chapter {ch_num}"),
            "pages": len(ch.get("pages") or []),
            "has_cbz": cbz_path.exists(),
            "mega_url": ch.get("cbz_mega_url")
        })
    
    first_ch = chapter_list[0]["chapter"] if chapter_list else "1"
    last_ch = chapter_list[-1]["chapter"] if chapter_list else "1"
    
    return success({
        "manga_key": manga_key,
        "total_chapters": len(chapter_list),
        "first_chapter": first_ch,
        "last_chapter": last_ch,
        "chapters": chapter_list
    })

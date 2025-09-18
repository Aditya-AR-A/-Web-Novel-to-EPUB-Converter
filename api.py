from fastapi import FastAPI, UploadFile, File, Form, Body, Request
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, List
import os
import tempfile
from scripts import scraper, convert_to_epub
import zipfile
from io import BytesIO
from pydantic import BaseModel

# Path to store epubs
BOOKS_DIR = os.path.join(os.path.dirname(__file__), "books")
if not os.path.exists(BOOKS_DIR):
    os.makedirs(BOOKS_DIR)

app = FastAPI(
    title="Web Novel to EPUB Converter API",
    description="API to scrape web novels and convert them into EPUB files",
    version="1.0.0"
)

# ------------------ MODELS ------------------ #
class GenerateEpubRequest(BaseModel):
    url: str
    chapters_per_book: int | None = 500
    chapter_workers: int | None = 0
    chapter_limit: int | None = 0

    @classmethod
    def validate_positive(cls, v, field_name):
        if v is None:
            return v
        if not isinstance(v, int):
            raise ValueError(f"{field_name} must be integer")
        if v < 0:
            raise ValueError(f"{field_name} must be >= 0")
        return v

    def model_post_init(self, __context):  # pydantic v2 style hook; silently coerce invalid to default handled by BaseModel earlier
        self.chapters_per_book = self.validate_positive(self.chapters_per_book, 'chapters_per_book') or 500
        self.chapter_workers = self.validate_positive(self.chapter_workers, 'chapter_workers') or 0
        self.chapter_limit = self.validate_positive(self.chapter_limit, 'chapter_limit') or 0


def success(data=None):
    return {"ok": True, "data": data}


def error(message: str, code: str = "error", status: int = 400):
    return JSONResponse({"ok": False, "error": {"code": code, "message": message}}, status_code=status)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return error(str(exc), code="internal_error", status=500)

class DeleteManyRequest(BaseModel):
    names: List[str]

class DownloadManyRequest(BaseModel):
    names: List[str]

# ------------------ ROUTES ------------------ #

@app.get("/", summary="Root endpoint", description="Check if the API is running")
def root():
    return {"message": "Web Novel to EPUB Converter API is running."}


@app.post("/epub/generate", summary="Generate EPUB from URL", description="Scrape chapters and build one or more EPUB volumes based on chapters_per_book.")
def generate_epub(req: GenerateEpubRequest):
    """Mimic the CLI behaviour in main.py for a single URL.

    Returns list of produced EPUB filenames.
    """
    try:
        metadata = scraper.get_chapter_metadata(req.url)
    except Exception as e:
        return error(f"Metadata fetch failed: {e}", code="metadata_fetch_failed", status=502)
    try:
        chapters = scraper.get_chapters(
            req.url if (req.chapter_workers or 0) > 0 else metadata.get("starting_url", req.url),
            chapter_workers=req.chapter_workers or 0,
            chapter_limit=(req.chapter_limit if req.chapter_limit and req.chapter_limit > 0 else None)
        )
    except Exception as e:
        return error(f"Chapter fetch failed: {e}", code="chapter_fetch_failed", status=502)

    titles = chapters.get('title', [])
    texts = chapters.get('text', [])
    valid = [1 for t, x in zip(titles, texts) if x and x.strip()]
    if not valid:
        return error("No valid chapter content collected.", code="no_chapters", status=422)
    try:
        convert_to_epub.to_epub(
            metadata,
            chapters,
            chapters_per_book=req.chapters_per_book or 500
        )
    except Exception as e:
        return error(f"EPUB generation failed: {e}", code="epub_generation_failed", status=500)

    base = (metadata.get('title', 'untitled').replace(' ', '_').replace(':', '_').lower())
    produced = []
    for name in sorted(os.listdir(BOOKS_DIR)):
        if name.startswith(base + '-') and name.endswith('.epub'):
            produced.append(name)
    if not produced:
        for name in sorted(os.listdir(BOOKS_DIR)):
            if name.endswith('.epub') and base in name:
                produced.append(name)
    return success({"filenames": produced, "count": len(produced)})


@app.post("/epub/download", summary="Download single EPUB by filename")
def download_one_epub(name: str = Body(..., embed=True, description="Name of the EPUB file to download")):
    epub_path = os.path.join(BOOKS_DIR, name)
    if not os.path.exists(epub_path):
        return error("File not found", code="not_found", status=404)
    return FileResponse(epub_path, filename=name)


@app.post("/epubs/download/all", summary="Download all EPUBs as a ZIP")
def download_all_epubs():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        for name in os.listdir(BOOKS_DIR):
            if name.endswith(".epub"):
                epub_path = os.path.join(BOOKS_DIR, name)
                zipf.write(epub_path, arcname=name)
    buf.seek(0)
    return FileResponse(buf, media_type="application/zip", filename="all_epubs.zip")


@app.post("/epubs/download", summary="Download multiple EPUBs as a ZIP")
def download_many_epubs(req: DownloadManyRequest):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        for name in req.names:
            epub_path = os.path.join(BOOKS_DIR, name)
            if os.path.exists(epub_path):
                zipf.write(epub_path, arcname=name)
    buf.seek(0)
    return FileResponse(buf, media_type="application/zip", filename="epubs.zip")


@app.delete("/epubs/all", summary="Delete all EPUBs")
def delete_all_epubs():
    files = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".epub")]
    deleted, errors = [], []
    for name in files:
        try:
            os.remove(os.path.join(BOOKS_DIR, name))
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "error": str(e)})
    return success({"deleted": deleted, "errors": errors})


@app.delete("/epubs", summary="Delete multiple EPUBs by filenames")
def delete_many_epubs(req: DeleteManyRequest):
    deleted, errors = [], []
    for name in req.names:
        epub_path = os.path.join(BOOKS_DIR, name)
        if os.path.exists(epub_path):
            try:
                os.remove(epub_path)
                deleted.append(name)
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
        else:
            errors.append({"name": name, "error": "File not found."})
    return success({"deleted": deleted, "errors": errors})


@app.delete("/epub/{name}", summary="Delete single EPUB by filename")
def delete_epub(name: str):
    epub_path = os.path.join(BOOKS_DIR, name)
    if not os.path.exists(epub_path):
        return error("File not found", code="not_found", status=404)
    try:
        os.remove(epub_path)
        return success({"message": f"Deleted {name}"})
    except Exception as e:
        return error(str(e), code="delete_failed", status=500)


@app.get("/epubs", summary="List all EPUBs")
def list_epubs():
    files = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".epub")]
    return success({"epubs": files})


@app.post("/convert", summary="Convert novel with optional cover", description="Accepts form-data with URL and builds EPUB volumes.")
def convert_novel(
    url: str = Form(..., description="URL of the novel"),
    chapters_per_book: int = Form(500),
    chapter_workers: int = Form(0),
    chapter_limit: int = Form(0),
    cover: Optional[UploadFile] = File(None, description="Cover image file (optional; overrides downloaded image)"),
):
    try:
        metadata = scraper.get_chapter_metadata(url)
    except Exception as e:
        return error(f"Metadata fetch failed: {e}", code="metadata_fetch_failed", status=502)

    try:
        chapters = scraper.get_chapters(
            url if chapter_workers > 0 else metadata.get("starting_url", url),
            chapter_workers=chapter_workers,
            chapter_limit=(chapter_limit if chapter_limit and chapter_limit > 0 else None)
        )
    except Exception as e:
        return error(f"Chapter fetch failed: {e}", code="chapter_fetch_failed", status=502)

    titles = chapters.get('title', [])
    texts = chapters.get('text', [])
    if not any(x and x.strip() for x in texts):
        return error("No valid chapter content collected.", code="no_chapters", status=422)

    # Handle cover override
    if cover:
        try:
            os.makedirs('media', exist_ok=True)
            cover_path = os.path.join('media', f"upload_{cover.filename}")
            with open(cover_path, 'wb') as f:
                f.write(cover.file.read())
            metadata['image_path'] = cover_path
        except Exception as e:
            return error(f"Cover save failed: {e}", code="cover_save_failed", status=400)

    try:
        convert_to_epub.to_epub(metadata, chapters, chapters_per_book=chapters_per_book)
    except Exception as e:
        return error(f"EPUB generation failed: {e}", code="epub_generation_failed", status=500)

    base = (metadata.get('title', 'untitled').replace(' ', '_').replace(':', '_').lower())
    produced = [n for n in sorted(os.listdir(BOOKS_DIR)) if n.startswith(base + '-') and n.endswith('.epub')]
    if not produced:
        produced = [n for n in sorted(os.listdir(BOOKS_DIR)) if n.endswith('.epub') and base in n]
    return success({"filenames": produced, "count": len(produced)})


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}

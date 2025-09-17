from fastapi import FastAPI, UploadFile, File, Form, Body
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
    title: str
    author: Optional[str] = None
    genres: Optional[str] = None
    tags: Optional[str] = None

class DeleteManyRequest(BaseModel):
    names: List[str]

class DownloadManyRequest(BaseModel):
    names: List[str]

# ------------------ ROUTES ------------------ #

@app.get("/", summary="Root endpoint", description="Check if the API is running")
def root():
    return {"message": "Web Novel to EPUB Converter API is running."}


@app.post("/epub/generate", summary="Generate EPUB from URL")
def generate_epub(req: GenerateEpubRequest):
    chapters, metadata = scraper.scrape_novel(req.url, tempfile.gettempdir())
    epub_filename = f"{req.title}.epub"
    epub_path = os.path.join(tempfile.gettempdir(), epub_filename)

    convert_to_epub.create_epub(
        chapters=chapters,
        title=req.title,
        author=req.author,
        cover_image=None,
        genres=req.genres.split(",") if req.genres else [],
        tags=req.tags.split(",") if req.tags else [],
        output_path=epub_path,
        metadata=metadata
    )

    final_path = os.path.join(BOOKS_DIR, epub_filename)
    with open(epub_path, "rb") as src, open(final_path, "wb") as dst:
        dst.write(src.read())

    return {"filename": epub_filename, "status": "success"}


@app.post("/epub/download", summary="Download single EPUB by filename")
def download_one_epub(name: str = Body(..., embed=True, description="Name of the EPUB file to download")):
    epub_path = os.path.join(BOOKS_DIR, name)
    if not os.path.exists(epub_path):
        return JSONResponse({"error": "File not found."}, status_code=404)
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
    return {"deleted": deleted, "errors": errors}


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
    return {"deleted": deleted, "errors": errors}


@app.delete("/epub/{name}", summary="Delete single EPUB by filename")
def delete_epub(name: str):
    epub_path = os.path.join(BOOKS_DIR, name)
    if not os.path.exists(epub_path):
        return JSONResponse({"error": "File not found."}, status_code=404)
    try:
        os.remove(epub_path)
        return {"message": f"Deleted {name}"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/epubs", summary="List all EPUBs")
def list_epubs():
    files = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".epub")]
    return {"epubs": files}


@app.post("/convert", summary="Convert novel with optional cover", description="Accepts form-data with URL, title, author, cover, genres, and tags")
def convert_novel(
    url: str = Form(..., description="URL of the novel"),
    title: str = Form(..., description="Title of the EPUB"),
    author: Optional[str] = Form(None, description="Author name"),
    cover: Optional[UploadFile] = File(None, description="Cover image file"),
    genres: Optional[str] = Form(None, description="Comma-separated list of genres"),
    tags: Optional[str] = Form(None, description="Comma-separated list of tags")
):
    with tempfile.TemporaryDirectory() as tmpdir:
        chapters, metadata = scraper.scrape_novel(url, tmpdir)

        cover_path = None
        if cover:
            cover_path = os.path.join(tmpdir, cover.filename)
            with open(cover_path, "wb") as f:
                f.write(cover.file.read())

        epub_filename = f"{title}.epub"
        epub_path = os.path.join(tmpdir, epub_filename)

        convert_to_epub.create_epub(
            chapters=chapters,
            title=title,
            author=author,
            cover_image=cover_path,
            genres=genres.split(",") if genres else [],
            tags=tags.split(",") if tags else [],
            output_path=epub_path,
            metadata=metadata
        )

        final_path = os.path.join(BOOKS_DIR, epub_filename)
        with open(epub_path, "rb") as src, open(final_path, "wb") as dst:
            dst.write(src.read())

        return FileResponse(final_path, filename=epub_filename)


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}

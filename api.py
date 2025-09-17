


from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import os
import tempfile
from scripts import scraper, convert_to_epub
import zipfile
from io import BytesIO


BOOKS_DIR = os.path.join(os.path.dirname(__file__), "books")
app = FastAPI()

@app.get("/epub/{name}")
def download_epub(name: str):
    epub_path = os.path.join(BOOKS_DIR, name)
    if not os.path.exists(epub_path):
        return JSONResponse({"error": "File not found."}, status_code=404)
    return FileResponse(epub_path, filename=name)

@app.get("/epubs/download/all")
def download_all_epubs():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        if os.path.exists(BOOKS_DIR):
            for name in os.listdir(BOOKS_DIR):
                if name.endswith(".epub"):
                    epub_path = os.path.join(BOOKS_DIR, name)
                    zipf.write(epub_path, arcname=name)
    buf.seek(0)
    return FileResponse(buf, media_type="application/zip", filename="all_epubs.zip")

@app.post("/epubs/download")
def download_many_epubs(names: list[str] = Body(...)):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zipf:
        for name in names:
            epub_path = os.path.join(BOOKS_DIR, name)
            if os.path.exists(epub_path):
                zipf.write(epub_path, arcname=name)
    buf.seek(0)
    return FileResponse(buf, media_type="application/zip", filename="epubs.zip")
@app.delete("/epubs/all")
def delete_all_epubs():
    if not os.path.exists(BOOKS_DIR):
        return JSONResponse({"deleted": [], "errors": ["Books folder not found."]})
    files = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".epub")]
    deleted = []
    errors = []
    for name in files:
        epub_path = os.path.join(BOOKS_DIR, name)
        try:
            os.remove(epub_path)
            deleted.append(name)
        except Exception as e:
            errors.append({"name": name, "error": str(e)})
    return JSONResponse({"deleted": deleted, "errors": errors})

@app.delete("/epubs")
def delete_many_epubs(names: list[str] = Body(...)):
    deleted = []
    not_found = []
    for name in names:
        epub_path = os.path.join(BOOKS_DIR, name)
        if os.path.exists(epub_path):
            try:
                os.remove(epub_path)
                deleted.append(name)
            except Exception as e:
                not_found.append({"name": name, "error": str(e)})
        else:
            not_found.append({"name": name, "error": "File not found."})
    return JSONResponse({"deleted": deleted, "errors": not_found})


BOOKS_DIR = os.path.join(os.path.dirname(__file__), "books")
app = FastAPI()

@app.delete("/epub/{name}")
def delete_epub(name: str):
    epub_path = os.path.join(BOOKS_DIR, name)
    if not os.path.exists(epub_path):
        return JSONResponse({"error": "File not found."}, status_code=404)
    try:
        os.remove(epub_path)
        return JSONResponse({"message": f"Deleted {name}"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/")
def root():
    return {"message": "Web Novel to EPUB Converter API is running."}

@app.get("/epubs")
def list_epubs():
    if not os.path.exists(BOOKS_DIR):
        return JSONResponse({"epubs": []})
    files = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".epub")]
    return JSONResponse({"epubs": files})


@app.post("/convert")
def convert_novel(
    url: str = Form(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    cover: Optional[UploadFile] = File(None),
    genres: Optional[str] = Form(None),
    tags: Optional[str] = Form(None)
):
    # Download chapters using scraper
    with tempfile.TemporaryDirectory() as tmpdir:
        chapters, metadata = scraper.scrape_novel(url, tmpdir)
        cover_path = None
        if cover:
            cover_path = os.path.join(tmpdir, cover.filename)
            with open(cover_path, "wb") as f:
                f.write(cover.file.read())
        # Convert to EPUB
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
        # Save to books folder
        if not os.path.exists(BOOKS_DIR):
            os.makedirs(BOOKS_DIR)
        final_path = os.path.join(BOOKS_DIR, epub_filename)
        with open(epub_path, "rb") as src, open(final_path, "wb") as dst:
            dst.write(src.read())
        return FileResponse(final_path, filename=epub_filename)

@app.post("/health")
def health():
    return JSONResponse({"status": "ok"})

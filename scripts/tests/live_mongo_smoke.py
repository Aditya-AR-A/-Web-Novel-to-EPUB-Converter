"""End-to-end smoke test that exercises the Mongo integration using the
current environment's `MONGO_URI`.

It will:
1. Ensure sample EPUB and cover image assets exist locally.
2. Call `save_scraped_novel_to_db` with synthetic metadata.
3. Read back the inserted documents to verify they landed in each collection.
4. Drop the temporary documents so the remote database stays clean.

Run with:

    python -m scripts.tests.live_mongo_smoke

You should see a short success report. Failures will raise exceptions so
errors are easy to spot in CI or manual runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from scripts.db import operations
from scripts.db.mongo import db


ROOT_DIR = Path(__file__).resolve().parents[2]
BOOKS_DIR = Path(os.getenv("BOOKS_DIR", ROOT_DIR / "books")).resolve()
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", ROOT_DIR / "media")).resolve()

SAMPLE_NOVEL_KEY = "sample_novel_author_name"
SAMPLE_FILE_NAME = "sample_novel-1.epub"
SAMPLE_IMAGE_NAME = "image Sample Novel.jpeg"


def _ensure_sample_assets() -> None:
    BOOKS_DIR.mkdir(exist_ok=True)
    MEDIA_DIR.mkdir(exist_ok=True)

    epub_path = BOOKS_DIR / SAMPLE_FILE_NAME
    if not epub_path.exists():
        epub_path.write_bytes(b"EPUB-DATA")

    image_path = MEDIA_DIR / SAMPLE_IMAGE_NAME
    if not image_path.exists():
        image_path.write_bytes(b"JPEGDATA")


def _collect_documents() -> Dict[str, Any]:
    return {
        "novel": db.novels.find_one({"novel_key": SAMPLE_NOVEL_KEY}),
        "links": list(db.novel_links.find({"novel_key": SAMPLE_NOVEL_KEY})),
        "files": list(db.novel_files.find({"link_key": {"$regex": SAMPLE_NOVEL_KEY}})),
    }


def _cleanup() -> None:
    db.novel_files.delete_many({"link_key": {"$regex": SAMPLE_NOVEL_KEY}})
    db.novel_files.delete_many({"novel_key": SAMPLE_NOVEL_KEY})
    db.novel_links.delete_many({"novel_key": SAMPLE_NOVEL_KEY})
    db.novels.delete_many({"novel_key": SAMPLE_NOVEL_KEY})


def main() -> None:
    _cleanup()  # ensure we start from a clean slate
    _ensure_sample_assets()

    metadata = {
        "title": "Sample Novel",
        "author": "Author Name",
        "synopsis": "Sample synopsis",
        "genres": ["Fantasy", "Adventure"],
        "starting_url": "https://example.com/novel",
        "image_url": "https://example.com/cover.jpg",
        "image_path": str(MEDIA_DIR / SAMPLE_IMAGE_NAME),
    }

    produced_files = [SAMPLE_FILE_NAME]
    operations.save_scraped_novel_to_db(metadata, produced_files, str(BOOKS_DIR))

    docs = _collect_documents()
    assert docs["novel"], "Novel document missing"
    assert docs["links"], "Novel link document missing"
    assert docs["files"], "Novel file document missing"

    novel_doc = docs["novel"]
    cover_image = novel_doc.get("cover_image")
    assert cover_image, "Cover image link missing from novel metadata"
    assert isinstance(cover_image, str), "Cover image must be a string URL"
    storage_key = novel_doc.get("cover_image_storage_key")
    if storage_key is not None:
        assert isinstance(storage_key, str), "Cover image storage key must be a string"
    mime = novel_doc.get("cover_image_mime")
    if storage_key:
        assert mime, "Cover image MIME type required when storage key is set"

    file_doc = docs["files"][0]
    assert file_doc.get("novel_key") == SAMPLE_NOVEL_KEY, "Novel key not stored on file"
    assert file_doc.get("file_data"), "Stored EPUB binary missing"
    expected_size = (BOOKS_DIR / SAMPLE_FILE_NAME).stat().st_size
    assert len(file_doc["file_data"]) == expected_size, "Stored EPUB size mismatch"

    print("Mongo smoke test inserted documents:")
    print({k: len(v) if isinstance(v, list) else 1 for k, v in docs.items()})

    _cleanup()
    print("Cleanup complete. Mongo integration OK.")


if __name__ == "__main__":
    main()

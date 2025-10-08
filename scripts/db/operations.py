import json
import os
import mimetypes
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from bson import ObjectId

from scripts.db.models import NovelMetadata, NovelLinks, NovelFile
from scripts.db.mongo import db
from scripts.storage import (
    r2_enabled,
    upload_file_to_r2,
    upload_bytes_to_r2,
    r2_connection_status,
    r2_object_exists,
)
from scripts.config import METADATA_FILENAME


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def generate_novel_key(title: str, author: str) -> str:
    """Generate a unique key for the novel based on title and author."""
    key = f"{title.lower().strip()}_{author.lower().strip()}"
    return key.replace(" ", "_").replace(":", "_")


def generate_link_key(novel_key: str, file_name: str) -> str:
    """Generate a unique key for the link."""
    return f"{novel_key}_{file_name}"


def _guess_mime(path: str, fallback: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    return mime_type or fallback


def _build_storage_key(folder: str, novel_key: str, filename: str) -> str:
    clean_folder = folder.strip("/")
    clean_key = novel_key.strip("/")
    return f"{clean_folder}/{clean_key}/{filename}".replace("//", "/")


def _image_extension(original_name: Optional[str], mime_type: Optional[str]) -> str:
    if original_name:
        suffix = Path(original_name).suffix
        if suffix:
            return suffix.lower()
    if mime_type:
        lower = mime_type.lower()
        if "png" in lower:
            return ".png"
        if "webp" in lower:
            return ".webp"
        if "gif" in lower:
            return ".gif"
    return ".jpg"


def save_scraped_novel_to_db(metadata: dict, produced_files: List[str], books_dir: str):
    """
    Save the scraped novel data to the database.

    :param metadata: Dict from scraper.get_chapter_metadata
    :param produced_files: List of filenames produced (e.g., ['title_part1.epub'])
    :param books_dir: Directory where files are stored
    """
    novel_key = generate_novel_key(metadata['title'], metadata['author'])

    existing = db.novels.find_one({"novel_key": novel_key})
    now = datetime.utcnow()
    created_at = existing.get('created_at') if existing and existing.get('created_at') else now
    novel_id: ObjectId = existing.get('_id') if existing else ObjectId()
    existing_cover = (existing or {}).get('cover_image')
    existing_storage_key = (existing or {}).get('cover_image_storage_key')
    existing_cover_mime = (existing or {}).get('cover_image_mime')

    # Prepare image data upfront to capture remote uploads and metadata
    image_path = metadata.get('image_path')
    image_name: Optional[str] = None
    image_mime: Optional[str] = None
    image_url: Optional[str] = metadata.get('image_url')
    image_storage_key: Optional[str] = None

    if image_path and os.path.exists(image_path):
        image_name = os.path.basename(image_path)
        guessed_mime = _guess_mime(image_name, "image/jpeg")

        if r2_enabled():
            try:
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
            except OSError as exc:
                image_bytes = None
                print(f"[R2] Failed to read cover image {image_name}: {exc}")

            if image_bytes:
                storage_extension = _image_extension(image_name, guessed_mime)
                storage_key = f"images/{novel_id}{storage_extension}"
                uploaded_url = upload_bytes_to_r2(image_bytes, storage_key, content_type=guessed_mime)
                if uploaded_url:
                    image_url = uploaded_url
                    image_storage_key = storage_key
                    image_mime = guessed_mime
                else:
                    print(f"[R2] Failed to upload cover image {image_name}; leaving metadata image URL as-is.")
        else:
            status = r2_connection_status()
            missing = ", ".join(status.get("missing", [])) or "credentials unavailable"
            print(f"[R2] Skipping cover upload; client disabled ({missing}).")
        if image_mime is None:
            image_mime = guessed_mime

    novel = NovelMetadata(
        id=novel_id,
        novel_key=novel_key,
        title=metadata['title'],
        author=metadata['author'],
        description=metadata.get('synopsis'),
        genre=', '.join(metadata.get('genres', [])),
        source_url=metadata.get('starting_url'),
        cover_image=image_url or metadata.get('image_url') or existing_cover,
        cover_image_storage_key=image_storage_key or existing_storage_key,
        cover_image_mime=image_mime or existing_cover_mime,
        status='ready',
        created_at=created_at,
        updated_at=now
    )
    novel_data = novel.model_dump(by_alias=True, exclude_none=True)
    novel_data.pop('_id', None)
    if not existing:
        novel_data.setdefault('created_at', now)
    set_fields = novel_data.copy()
    set_fields.pop("created_at", None)

    set_on_insert = {"_id": novel_id}
    if not existing:
        set_on_insert["created_at"] = novel_data.get("created_at", now)

    update_doc = {"$set": set_fields}
    if set_on_insert:
        update_doc["$setOnInsert"] = set_on_insert

    db.novels.update_one({"novel_key": novel_key}, update_doc, upsert=True)

    books_base = Path(books_dir).expanduser().resolve()
    books_base.mkdir(parents=True, exist_ok=True)
    novel_dir = books_base / novel_key
    novel_dir.mkdir(parents=True, exist_ok=True)

    file_records: List[dict] = []

    # Save files
    for file_name in produced_files:
        source_path = books_base / file_name
        target_path = novel_dir / file_name

        if source_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.resolve() != target_path.resolve():
                if target_path.exists():
                    target_path.unlink()
                shutil.move(str(source_path), str(target_path))
        elif target_path.exists():
            pass
        else:
            continue

        file_path = target_path
        file_size = file_path.stat().st_size
        link_key = generate_link_key(novel_key, file_name)

        # Insert NovelLinks
        storage_key = None
        public_url = None
        if r2_enabled():
            storage_key = _build_storage_key("books", novel_key, file_name)
            public_url = upload_file_to_r2(str(file_path), storage_key, content_type='application/epub+zip')
            if not public_url:
                print(f"[R2] Failed to upload {file_name}; keeping local/Mongo copy only.")
            elif not r2_object_exists(storage_key):
                print(f"[R2] Warning: upload of {storage_key} not confirmed via head_object.")
        else:
            status = r2_connection_status()
            missing = ", ".join(status.get("missing", [])) or "credentials unavailable"
            print(f"[R2] Skipping remote upload for {file_name}; client disabled ({missing}).")

        download_links = []
        if public_url:
            download_links.append(public_url)
        download_links.append(str(file_path))

        link = NovelLinks(
            novel_key=novel_key,
            link_key=link_key,
            file_type='epub',
            download_links=download_links,
            note='Generated EPUB'
        )
        link_doc = link.model_dump(by_alias=True, exclude_none=True)
        link_doc.pop('_id', None)
        db.novel_links.update_one(
            {"novel_key": novel_key, "link_key": link_key},
            {"$set": link_doc},
            upsert=True
        )

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        checksum = hashlib.md5(file_bytes).hexdigest()

        existing_file = db.novel_files.find_one(
            {"link_key": link_key, "file_name": file_name},
            {"created_at": 1}
        )

        created_at_value = existing_file.get('created_at') if existing_file and existing_file.get('created_at') else datetime.utcnow()
        file_entry = NovelFile(
            link_key=link_key,
            novel_key=novel_key,
            file_name=file_name,
            file_url=public_url or str(file_path),
            storage_key=storage_key,
            file_size=file_size,
            mime_type='application/epub+zip',
            checksum=checksum,
            file_data=file_bytes,
            local_path=str(file_path)
        )
        file_doc = file_entry.model_dump(by_alias=True, exclude_none=True)
        file_doc.pop('_id', None)
        if existing_file and existing_file.get('created_at'):
            file_doc['created_at'] = existing_file['created_at']
            created_at_value = existing_file['created_at']
        db.novel_files.update_one(
            {"link_key": link_key, "file_name": file_name},
            {"$set": file_doc},
            upsert=True
        )

        file_records.append(
            {
                "file_name": file_name,
                "file_size": file_size,
                "checksum": checksum,
                "storage_key": storage_key,
                "file_url": public_url or str(file_path),
                "local_path": str(file_path),
                "mime_type": 'application/epub+zip',
                "created_at": _isoformat(created_at_value),
                "download_links": download_links,
            }
        )

    metadata_payload = {
        "version": 1,
        "generated_at": _isoformat(now),
        "updated_at": _isoformat(now),
        "novel": {
            "novel_key": novel_key,
            "title": novel.title,
            "author": novel.author,
            "description": novel.description,
            "genre": novel.genre,
            "source_url": novel.source_url,
            "cover_image": novel.cover_image,
            "cover_image_storage_key": novel.cover_image_storage_key,
            "cover_image_mime": novel.cover_image_mime,
            "status": novel.status,
            "created_at": _isoformat(novel.created_at),
            "updated_at": _isoformat(novel.updated_at),
        },
        "files": file_records,
    }

    metadata_bytes = json.dumps(metadata_payload, ensure_ascii=False, indent=2).encode("utf-8")
    metadata_path = novel_dir / METADATA_FILENAME
    metadata_path.write_bytes(metadata_bytes)

    if r2_enabled():
        metadata_storage_key = _build_storage_key("books", novel_key, METADATA_FILENAME)
        upload_bytes_to_r2(metadata_bytes, metadata_storage_key, content_type="application/json")

    print(f"Saved novel {novel_key} to database with {len(produced_files)} files.")
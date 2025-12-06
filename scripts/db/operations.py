import os
import mimetypes
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from bson import ObjectId

from scripts.db.models import NovelMetadata, NovelLink
from scripts.db.mongo import db
from scripts.storage import (
    r2_enabled,
    upload_file_to_r2,
    upload_bytes_to_r2,
    r2_connection_status,
    r2_object_exists,
)


def generate_novel_key(title: str, author: str) -> str:
    """Generate a unique key for the novel based on title and author."""
    key = f"{title.lower().strip()}_{author.lower().strip()}"
    return key.replace(" ", "_").replace(":", "_")


def _guess_mime(path: str, fallback: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    return mime_type or fallback


def _build_storage_key(folder: str, novel_id: ObjectId, filename: str) -> str:
    clean_folder = folder.strip("/")
    clean_key = str(novel_id).strip("/")
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

    db.novels.update_one({"_id": novel_id}, update_doc, upsert=True)

    books_base = Path(books_dir).expanduser().resolve()
    books_base.mkdir(parents=True, exist_ok=True)
    storage_folder = str(novel_id)
    novel_dir = books_base / storage_folder
    novel_dir.mkdir(parents=True, exist_ok=True)
    legacy_dir = books_base / novel_key if novel_key else None

    # Save files
    for file_name in produced_files:
        candidate_paths = [books_base / file_name]
        if legacy_dir:
            candidate_paths.append(legacy_dir / file_name)
        candidate_paths.append(novel_dir / file_name)

        source_path: Optional[Path] = None
        for candidate in candidate_paths:
            if candidate and candidate.exists():
                source_path = candidate
                break

        if source_path is None:
            continue

        target_path = novel_dir / file_name
        if source_path.resolve() != target_path.resolve():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                target_path.unlink()
            shutil.move(str(source_path), str(target_path))

        file_path = target_path
        file_size = file_path.stat().st_size
        # Upload to remote storage when enabled
        storage_key = None
        public_url = None
        if r2_enabled():
            storage_key = _build_storage_key("books", novel_id, file_name)
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
        download_links.append(f"/epub/download?name={file_name}")
        download_links = list(dict.fromkeys(download_links))

        with open(file_path, 'rb') as f:
            checksum = hashlib.md5(f.read()).hexdigest()

        existing_link = db.novel_links.find_one(
            {"novel_id": novel_id, "file_name": file_name},
            {"created_at": 1}
        )

        link_key = f"{novel_id}_{file_name}"
        created_at_value = existing_link.get('created_at') if existing_link and existing_link.get('created_at') else datetime.utcnow()
        updated_at_value = datetime.utcnow()
        link_entry = NovelLink(
            novel_id=novel_id,
            novel_key=novel_key,
            link_key=link_key,
            file_name=file_name,
            file_url=public_url,
            storage_key=storage_key,
            file_size=file_size,
            mime_type='application/epub+zip',
            checksum=checksum,
            download_links=download_links,
            created_at=created_at_value,
            updated_at=updated_at_value,
        )

        link_doc = link_entry.model_dump(by_alias=True, exclude_none=True)
        link_doc.pop('_id', None)

        set_on_insert: dict[str, object] = {}
        if not existing_link:
            set_on_insert["created_at"] = created_at_value

        set_fields = {k: v for k, v in link_doc.items() if k != "created_at"}
        set_fields["updated_at"] = updated_at_value

        update_ops = {"$set": set_fields}
        if set_on_insert:
            update_ops["$setOnInsert"] = set_on_insert

        db.novel_links.update_one(
            {"novel_id": novel_id, "file_name": file_name},
            update_ops,
            upsert=True
        )

        if legacy_dir and legacy_dir.exists() and legacy_dir != novel_dir:
            try:
                if not any(legacy_dir.iterdir()):
                    legacy_dir.rmdir()
            except OSError:
                pass

    print(f"Saved novel {novel_id} to database with {len(produced_files)} files.")
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from scripts.storage import (
    r2_enabled,
    upload_bytes_to_r2,
    r2_connection_status,
)
from scripts.config import MANGA_DIR, MANGA_MANIFEST_NAME
from scripts.db.mongo import db


def generate_manga_key(title: str) -> str:
    key = title.lower().strip()
    key = key.replace(" ", "_").replace(":", "_")
    # Remove special characters that could cause issues
    key = "".join(c for c in key if c.isalnum() or c in "_-")
    return key


def save_manga_to_db(metadata: Dict, manifest: Dict, manga_key: str, local_path: str, storage_key: Optional[str] = None, public_url: Optional[str] = None) -> Dict:
    """Save manga metadata to MongoDB."""
    now = datetime.utcnow()
    chapters = manifest.get("chapters") or []
    
    doc = {
        "manga_key": manga_key,
        "title": metadata.get("title"),
        "author": metadata.get("author"),
        "artist": metadata.get("artist"),
        "status": metadata.get("status"),
        "language": metadata.get("language"),
        "tags": metadata.get("tags") or [],
        "source_url": metadata.get("source_url"),
        "cover_image": metadata.get("cover_image"),
        "chapter_count": len(chapters),
        "total_pages": sum(len(ch.get("pages") or []) for ch in chapters),
        "local_path": local_path,
        "storage_key": storage_key,
        "public_url": public_url,
        "updated_at": now,
    }
    
    # Upsert into MongoDB
    existing = db.manga.find_one({"manga_key": manga_key})
    if existing:
        doc["created_at"] = existing.get("created_at", now)
        db.manga.update_one({"manga_key": manga_key}, {"$set": doc})
    else:
        doc["created_at"] = now
        db.manga.insert_one(doc)
    
    return doc


def get_manga_list(offset: int = 0, limit: int = 100, search: Optional[str] = None) -> Dict:
    """Get list of manga from MongoDB with pagination."""
    query = {}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"author": {"$regex": search, "$options": "i"}},
            {"artist": {"$regex": search, "$options": "i"}},
        ]
    
    total = db.manga.count_documents(query)
    cursor = db.manga.find(query).sort("updated_at", -1).skip(offset).limit(limit)
    
    items = []
    for doc in cursor:
        items.append({
            "manga_key": doc.get("manga_key"),
            "title": doc.get("title"),
            "author": doc.get("author"),
            "artist": doc.get("artist"),
            "status": doc.get("status"),
            "cover_image": doc.get("cover_image"),
            "chapter_count": doc.get("chapter_count", 0),
            "total_pages": doc.get("total_pages", 0),
            "source_url": doc.get("source_url"),
            "public_url": doc.get("public_url"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        })
    
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def get_manga_by_key(manga_key: str) -> Optional[Dict]:
    """Get a single manga by key from MongoDB."""
    return db.manga.find_one({"manga_key": manga_key})


def delete_manga(manga_key: str) -> bool:
    """Delete manga from MongoDB."""
    result = db.manga.delete_one({"manga_key": manga_key})
    return result.deleted_count > 0


def save_manga_manifest(metadata: Dict, manifest: Dict) -> Dict:
    now = datetime.utcnow().isoformat()
    title = metadata.get("title") or ""
    manga_key = generate_manga_key(title)
    base = Path(os.getenv("MANGA_DIR", str(MANGA_DIR))).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    target_dir = base / manga_key
    target_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "generated_at": now,
        "updated_at": now,
        "manga": metadata,
        "chapters": manifest.get("chapters") or [],
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path = target_dir / MANGA_MANIFEST_NAME
    path.write_bytes(raw)

    public_url = None
    storage_key = f"manga/{manga_key}/{MANGA_MANIFEST_NAME}"
    if r2_enabled():
        public_url = upload_bytes_to_r2(raw, storage_key, content_type="application/json")
    else:
        status = r2_connection_status()
        _ = status

    # Also save to MongoDB
    try:
        save_manga_to_db(metadata, manifest, manga_key, str(path), storage_key if public_url else None, public_url)
    except Exception as e:
        print(f"Failed to save manga to MongoDB: {e}")

    return {
        "manga_key": manga_key,
        "local_path": str(path),
        "storage_key": storage_key if public_url else None,
        "public_url": public_url,
    }


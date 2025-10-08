import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

from .utils import success, error, BOOKS_DIR
from scripts.db.mongo import db
from scripts.storage import delete_r2_object, r2_enabled, download_r2_bytes, upload_bytes_to_r2
from scripts.config import METADATA_FILENAME

router = APIRouter()
BOOKS_PATH = Path(BOOKS_DIR)


def _metadata_storage_key(novel_key: str) -> Optional[str]:
    if not novel_key:
        return None
    clean_key = novel_key.strip("/")
    if not clean_key:
        return None
    return f"books/{clean_key}/{METADATA_FILENAME}"


def _prune_empty_dirs(path: Path) -> None:
    try:
        root = BOOKS_PATH.resolve()
        target = path if path.is_dir() else path.parent
        current = target.resolve()
        while current != root and root in current.parents:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
    except Exception:
        # Directory cleanup is best-effort; ignore errors like permission issues.
        return


def _update_metadata_catalog(doc: dict, removed_name: str) -> None:
    novel_key = doc.get("novel_key") if doc else None
    if not novel_key:
        return
    metadata_path = BOOKS_PATH / novel_key / METADATA_FILENAME
    if not metadata_path.exists():
        return
    try:
        raw = metadata_path.read_text(encoding="utf-8")
        payload = json.loads(raw) if raw else {}
    except (OSError, json.JSONDecodeError):
        return

    files = payload.get("files")
    if not isinstance(files, list):
        files = []
    filtered = [entry for entry in files if entry.get("file_name") != removed_name]
    if len(filtered) == len(files):
        return

    if filtered:
        payload["files"] = filtered
        payload["updated_at"] = datetime.utcnow().isoformat()
        try:
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            metadata_path.write_text(serialized, encoding="utf-8")
        except OSError:
            serialized = None
        if serialized and r2_enabled():
            storage_key = _metadata_storage_key(novel_key)
            if storage_key:
                try:
                    upload_bytes_to_r2(serialized.encode("utf-8"), storage_key, content_type="application/json")
                except Exception:
                    # Remote metadata update failures shouldn't block local removal.
                    pass
    else:
        try:
            metadata_path.unlink()
        except OSError:
            payload["files"] = filtered
            payload["updated_at"] = datetime.utcnow().isoformat()
            try:
                metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                return
        if r2_enabled():
            storage_key = _metadata_storage_key(novel_key)
            if storage_key:
                try:
                    delete_r2_object(storage_key)
                except Exception:
                    pass


def _local_file_candidates(name: str, doc: Optional[dict] = None) -> List[Path]:
    candidates: List[Path] = [BOOKS_PATH / name]
    if doc:
        local_path = doc.get("local_path")
        if local_path:
            candidates.append(Path(local_path))
        novel_key = doc.get("novel_key")
        if novel_key:
            candidates.append(BOOKS_PATH / novel_key / name)

    seen: set[str] = set()
    unique: List[Path] = []
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


@router.get("/epubs")
def list_epubs(offset: int = 0, limit: int = 100):
    if limit <= 0:
        limit = 100
    if limit > 500:
        limit = 500
    try:
        total = db.novel_files.count_documents({})
        cursor = db.novel_files.find({}, {"file_name": 1}).sort("created_at", -1).skip(offset).limit(limit)
        names = [doc.get("file_name") for doc in cursor if doc.get("file_name")]
    except Exception as exc:
        return error(f"Failed to list EPUBs: {exc}", code="mongo_error", status=500)
    return success({"epubs": names, "total": total, "offset": offset, "limit": limit})


@router.get("/epubs/details")
def list_epub_details(offset: int = 0, limit: int = 20, search: Optional[str] = None):
    if limit <= 0:
        limit = 20
    if limit > 100:
        limit = 100

    file_filter: Dict[str, object] = {}
    if search:
        try:
            regex = re.compile(re.escape(search), re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(search), re.IGNORECASE)

        file_filter["$or"] = [{"file_name": regex}]

        try:
            novel_matches = db.novels.find(
                {
                    "$or": [
                        {"title": regex},
                        {"author": regex},
                        {"novel_key": regex},
                        {"description": regex},
                    ]
                },
                {"novel_key": 1}
            )
            matching_novel_keys = [doc.get("novel_key") for doc in novel_matches if doc.get("novel_key")]
            if matching_novel_keys:
                file_filter["$or"].append({"novel_key": {"$in": matching_novel_keys}})
        except Exception as exc:
            return error(f"Failed to search novels: {exc}", code="mongo_error", status=500)

    try:
        file_cursor = db.novel_files.find(file_filter, {"file_data": 0}).sort("created_at", -1)
    except Exception as exc:
        return error(f"Failed to fetch EPUB metadata: {exc}", code="mongo_error", status=500)

    grouped: Dict[str, dict] = {}
    fallback_key = "__ungrouped__"
    for doc in file_cursor:
        novel_key = doc.get("novel_key") or fallback_key
        entry = grouped.setdefault(
            novel_key,
            {
                "novel_key": novel_key,
                "files": [],
                "latest": None,
            },
        )

        created_at = doc.get("created_at") if isinstance(doc.get("created_at"), datetime) else None
        if created_at and (entry["latest"] is None or created_at > entry["latest"]):
            entry["latest"] = created_at

        file_name = doc.get("file_name")
        api_download_url = f"/epub/download?name={quote(file_name)}" if file_name else None
        entry["files"].append(
            {
                "file_name": file_name,
                "file_size": doc.get("file_size"),
                "created_at": created_at,
                "download_url": doc.get("file_url") or api_download_url,
                "api_download_url": api_download_url,
            }
        )

    if fallback_key in grouped:
        # Drop any entries without a valid novel key.
        grouped.pop(fallback_key, None)

    total = len(grouped)
    sorted_groups = sorted(
        grouped.values(),
        key=lambda item: item["latest"] or datetime.min,
        reverse=True,
    )

    paged_groups = sorted_groups[offset: offset + limit]
    novel_keys = [group["novel_key"] for group in paged_groups]
    novel_map: Dict[str, dict] = {}

    if novel_keys:
        try:
            novel_cursor = db.novels.find({"novel_key": {"$in": novel_keys}})
            for novel in novel_cursor:
                key = novel.get("novel_key")
                if key:
                    novel_map[key] = novel
        except Exception as exc:
            return error(f"Failed to fetch novel metadata: {exc}", code="mongo_error", status=500)

    items: List[dict] = []
    for group in paged_groups:
        key = group["novel_key"]
        novel = novel_map.get(key, {})

        cover_image: Optional[str] = None
        if novel.get("cover_image_storage_key"):
            cover_image = f"/epubs/cover/{key}"
        elif novel.get("cover_image"):
            cover_image = novel.get("cover_image")

        files: List[dict] = []
        group["files"].sort(
            key=lambda f: f["created_at"] or datetime.min,
            reverse=True,
        )
        for file_entry in group["files"]:
            created_at = file_entry["created_at"]
            files.append(
                {
                    "file_name": file_entry["file_name"],
                    "file_size": file_entry["file_size"],
                    "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
                    "download_url": file_entry["download_url"],
                    "api_download_url": file_entry["api_download_url"],
                }
            )

        items.append(
            {
                "novel_key": key,
                "title": novel.get("title") or (files[0]["file_name"] if files else key),
                "author": novel.get("author"),
                "description": novel.get("description"),
                "cover_image": cover_image,
                "file_count": len(files),
                "latest_created": group["latest"].isoformat() if isinstance(group["latest"], datetime) else None,
                "files": files,
            }
        )

    return success(
        {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )


@router.get("/epubs/cover/{novel_key}")
def get_epub_cover_image(novel_key: str):
    try:
        novel = db.novels.find_one(
            {"novel_key": novel_key},
            {"cover_image": 1, "cover_image_storage_key": 1, "cover_image_mime": 1}
        )
    except Exception as exc:
        return error(f"Failed to fetch cover image: {exc}", code="mongo_error", status=500)

    if not novel:
        return error("Cover image not found", code="cover_not_found", status=404)

    storage_key = novel.get("cover_image_storage_key")
    if storage_key:
        data = download_r2_bytes(storage_key)
        if data:
            media_type = novel.get("cover_image_mime") or "image/jpeg"
            return Response(content=data, media_type=media_type)

    cover_url = novel.get("cover_image")
    if cover_url:
        return RedirectResponse(cover_url)

    return error("Cover image unavailable", code="cover_unavailable", status=404)


def _remove_file_entry(name: str, doc: Optional[dict], deleted: List[str], errors: List[dict]):
    if not doc:
        errors.append({"name": name, "error": "File not found in database."})
        return

    storage_key = doc.get("storage_key")
    if storage_key:
        remote_deleted = delete_r2_object(storage_key)
        if not remote_deleted and r2_enabled():
            errors.append({"name": name, "error": "Failed to delete remote object."})
            return

    file_path = _existing_local_path(name, doc)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as exc:
            errors.append({"name": name, "error": f"Failed to delete local file: {exc}"})
        else:
            _prune_empty_dirs(Path(file_path))

    db.novel_files.delete_one({"_id": doc.get("_id")})
    _update_metadata_catalog(doc, name)

    link_key = doc.get("link_key")
    if link_key:
        download_links = [doc.get("file_url"), doc.get("local_path"), file_path]
        for link in download_links:
            if link:
                db.novel_links.update_one({"link_key": link_key}, {"$pull": {"download_links": link}})
        if db.novel_files.count_documents({"link_key": link_key}) == 0:
            db.novel_links.delete_one({"link_key": link_key})

    if doc.get("novel_key"):
        remaining = db.novel_files.count_documents({"novel_key": doc.get("novel_key")})
        if remaining == 0:
            metadata_path = BOOKS_PATH / doc.get("novel_key") / METADATA_FILENAME
            if metadata_path.exists():
                try:
                    metadata_path.unlink()
                except OSError:
                    pass
            if r2_enabled():
                storage_key = _metadata_storage_key(doc.get("novel_key"))
                if storage_key:
                    try:
                        delete_r2_object(storage_key)
                    except Exception:
                        pass
            _prune_empty_dirs(BOOKS_PATH / doc.get("novel_key"))

    deleted.append(name)


@router.delete("/epubs/all")
def delete_all_epubs():
    deleted: List[str] = []
    errors: List[dict] = []
    try:
        docs = list(
            db.novel_files.find(
                {},
                {
                    "_id": 1,
                    "file_name": 1,
                    "storage_key": 1,
                    "link_key": 1,
                    "file_url": 1,
                    "local_path": 1,
                    "novel_key": 1,
                },
            )
        )
    except Exception as exc:
        return error(f"Failed to fetch EPUBs for deletion: {exc}", code="mongo_error", status=500)

    for doc in docs:
        name = doc.get("file_name")
        if not name:
            continue
        _remove_file_entry(name, doc, deleted, errors)

    return success({"deleted": deleted, "errors": errors})


@router.delete("/epubs")
def delete_many_epubs(names: List[str]):
    deleted: List[str] = []
    errors: List[dict] = []
    for name in names:
        try:
            doc = db.novel_files.find_one(
                {"file_name": name},
                {
                    "_id": 1,
                    "file_name": 1,
                    "storage_key": 1,
                    "link_key": 1,
                    "file_url": 1,
                    "local_path": 1,
                    "novel_key": 1,
                },
            )
        except Exception as exc:
            errors.append({"name": name, "error": f"Database error: {exc}"})
            continue
        _remove_file_entry(name, doc, deleted, errors)

    return success({"deleted": deleted, "errors": errors})

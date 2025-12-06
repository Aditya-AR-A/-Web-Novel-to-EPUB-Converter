import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse
from bson import ObjectId

from .utils import success, error, BOOKS_DIR
from scripts.db.mongo import db
from scripts.storage import delete_r2_object, r2_enabled, download_r2_bytes

router = APIRouter()
BOOKS_PATH = Path(BOOKS_DIR)

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


def _local_file_candidates(name: str, doc: Optional[dict] = None) -> List[Path]:
    candidates: List[Path] = [BOOKS_PATH / name]
    if doc:
        novel_id = doc.get("novel_id")
        if novel_id:
            candidates.append(BOOKS_PATH / str(novel_id) / name)
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
        total = db.novel_links.count_documents({})
        cursor = db.novel_links.find({}, {"file_name": 1}).sort("created_at", -1).skip(offset).limit(limit)
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

        or_filters: List[Dict[str, object]] = [{"file_name": regex}]

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
                {"_id": 1, "novel_key": 1}
            )
            matching_novel_ids: List[ObjectId] = []
            legacy_keys: List[str] = []
            for doc in novel_matches:
                if doc.get("_id"):
                    matching_novel_ids.append(doc["_id"])
                if doc.get("novel_key"):
                    legacy_keys.append(doc["novel_key"])
            if matching_novel_ids:
                or_filters.append({"novel_id": {"$in": matching_novel_ids}})
            if legacy_keys:
                or_filters.append({"novel_key": {"$in": legacy_keys}})
        except Exception as exc:
            return error(f"Failed to search novels: {exc}", code="mongo_error", status=500)

        file_filter["$or"] = or_filters

    try:
        file_cursor = db.novel_links.find(file_filter).sort("created_at", -1)
    except Exception as exc:
        return error(f"Failed to fetch EPUB metadata: {exc}", code="mongo_error", status=500)

    grouped: Dict[object, dict] = {}
    fallback_key = "__ungrouped__"
    for doc in file_cursor:
        raw_novel_id = doc.get("novel_id")
        novel_id: Optional[ObjectId] = None
        if isinstance(raw_novel_id, ObjectId):
            novel_id = raw_novel_id
        elif isinstance(raw_novel_id, str) and ObjectId.is_valid(raw_novel_id):
            novel_id = ObjectId(raw_novel_id)
        group_key: object
        if novel_id is not None:
            group_key = novel_id
        else:
            group_key = doc.get("novel_key") or fallback_key
        entry = grouped.setdefault(
            group_key,
            {
                "novel_id": novel_id,
                "novel_key": doc.get("novel_key"),
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

    fallback_group = grouped.pop(fallback_key, None)

    orphan_groups: List[dict] = []
    if fallback_group:
        fallback_files = list(fallback_group.get("files", []))
        fallback_files.sort(
            key=lambda f: f.get("created_at") or datetime.min,
            reverse=True,
        )
        for entry in fallback_files:
            orphan_groups.append(
                {
                    "novel_id": None,
                    "novel_key": None,
                    "files": [entry],
                    "latest": entry.get("created_at"),
                }
            )

    grouped_values = list(grouped.values()) + orphan_groups

    total = len(grouped_values)
    sorted_groups = sorted(
        grouped_values,
        key=lambda item: item["latest"] or datetime.min,
        reverse=True,
    )

    paged_groups = sorted_groups[offset: offset + limit]
    novel_ids = [group["novel_id"] for group in paged_groups if group.get("novel_id")]
    novel_map: Dict[str, dict] = {}

    if novel_ids:
        try:
            novel_cursor = db.novels.find({"_id": {"$in": novel_ids}})
            for novel in novel_cursor:
                novel_map[novel.get("_id")] = novel
        except Exception as exc:
            return error(f"Failed to fetch novel metadata: {exc}", code="mongo_error", status=500)

    items: List[dict] = []
    for group in paged_groups:
        novel_id = group.get("novel_id")
        novel = novel_map.get(novel_id, {}) if novel_id else {}
        novel_key = group.get("novel_key") or novel.get("novel_key")
        novel_identifier = str(novel_id) if novel_id else None

        cover_image: Optional[str] = None
        if novel_id and novel.get("cover_image_storage_key"):
            cover_image = f"/epubs/cover/{novel_id}"
        elif novel_key and novel.get("cover_image_storage_key"):
            cover_image = f"/epubs/cover/{novel_key}"
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
                "novel_id": novel_identifier,
                "novel_key": novel_key,
                "title": novel.get("title") or (files[0]["file_name"] if files else (novel_key or novel_identifier)),
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


@router.get("/epubs/cover/{identifier}")
def get_epub_cover_image(identifier: str):
    query: Dict[str, object]
    if ObjectId.is_valid(identifier):
        query = {"_id": ObjectId(identifier)}
    else:
        query = {"novel_key": identifier}
    try:
        novel = db.novels.find_one(
            query,
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

    db.novel_links.delete_one({"_id": doc.get("_id")})

    novel_id = doc.get("novel_id")
    if novel_id:
        remaining = db.novel_links.count_documents({"novel_id": novel_id})
        if remaining == 0:
            _prune_empty_dirs(BOOKS_PATH / str(novel_id))
    elif doc.get("novel_key"):
        remaining = db.novel_links.count_documents({"novel_key": doc.get("novel_key")})
        if remaining == 0:
            _prune_empty_dirs(BOOKS_PATH / doc.get("novel_key"))

    deleted.append(name)


@router.delete("/epubs/all")
def delete_all_epubs():
    deleted: List[str] = []
    errors: List[dict] = []
    try:
        docs = list(
            db.novel_links.find(
                {},
                {
                    "_id": 1,
                    "file_name": 1,
                    "storage_key": 1,
                    "file_url": 1,
                    "novel_id": 1,
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
            doc = db.novel_links.find_one(
                {"file_name": name},
                {
                    "_id": 1,
                    "file_name": 1,
                    "storage_key": 1,
                    "file_url": 1,
                    "novel_id": 1,
                    "novel_key": 1,
                },
            )
        except Exception as exc:
            errors.append({"name": name, "error": f"Database error: {exc}"})
            continue
        _remove_file_entry(name, doc, deleted, errors)

    return success({"deleted": deleted, "errors": errors})

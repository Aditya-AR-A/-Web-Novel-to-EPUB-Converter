from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy import select

from app.db.models import EpubMetadata
from app.db.session import get_session
from app.storage import get_s3_storage
from scripts import convert_to_epub, scraper


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or str(uuid.uuid4())


class EpubService:
    def __init__(self) -> None:
        self.storage = get_s3_storage()

    def create_epub(
        self,
        *,
        url: str,
        title: str,
        author: Optional[str],
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        cover: Optional[UploadFile] = None,
    ) -> EpubMetadata:
        slug = _slugify(title)
        unique_suffix = uuid.uuid4().hex[:8]
        epub_filename = f"{slug}-{unique_suffix}.epub"
        s3_key = f"epubs/{epub_filename}"

        with get_session() as session:
            record = EpubMetadata(
                title=title,
                author=author,
                source_url=url,
                s3_key=s3_key,
                s3_url="",
                file_size=0,
                status="processing",
            )
            session.add(record)
            session.flush()
            session.refresh(record)

        try:
            s3_url, file_size = self._generate_and_upload(
                url=url,
                title=title,
                author=author,
                genres=genres or [],
                tags=tags or [],
                cover=cover,
                epub_filename=epub_filename,
                s3_key=s3_key,
            )
        except Exception as exc:
            with get_session() as session:
                db_record = session.get(EpubMetadata, record.id)
                if db_record:
                    db_record.status = "failed"
                    db_record.error_message = str(exc)
            raise

        with get_session() as session:
            db_record = session.get(EpubMetadata, record.id)
            if not db_record:
                raise RuntimeError("Failed to load metadata after generation.")
            db_record.status = "ready"
            db_record.s3_url = s3_url
            db_record.file_size = file_size
            db_record.error_message = None
            session.flush()
            session.refresh(db_record)
            return db_record

    def list_epubs(self) -> List[EpubMetadata]:
        with get_session() as session:
            result = session.execute(select(EpubMetadata).order_by(EpubMetadata.created_at.desc()))
            return list(result.scalars().all())

    def get_epub(self, ebook_id: int) -> Optional[EpubMetadata]:
        with get_session() as session:
            return session.get(EpubMetadata, ebook_id)

    def delete_epub(self, ebook_id: int) -> bool:
        with get_session() as session:
            record = session.get(EpubMetadata, ebook_id)
            if not record:
                return False
            self.storage.delete_object(record.s3_key)
            session.delete(record)
            return True

    def find_by_keys(self, keys: List[str]) -> List[EpubMetadata]:
        if not keys:
            return []
        with get_session() as session:
            result = session.execute(select(EpubMetadata).where(EpubMetadata.s3_key.in_(keys)))
            return list(result.scalars().all())

    def get_all(self) -> List[EpubMetadata]:
        return self.list_epubs()

    def download_buffer(self, s3_key: str):
        return self.storage.download_object(s3_key)

    def generate_presigned_url(self, s3_key: str) -> str:
        return self.storage.generate_presigned_url(s3_key)

    def _generate_and_upload(
        self,
        *,
        url: str,
        title: str,
        author: Optional[str],
        genres: List[str],
        tags: List[str],
        cover: Optional[UploadFile],
        epub_filename: str,
        s3_key: str,
    ) -> tuple[str, int]:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            chapters, metadata = scraper.scrape_novel(url, tmpdir)

            cover_path = None
            if cover is not None:
                cover_filename = f"cover-{uuid.uuid4().hex}{Path(cover.filename or '').suffix}"
                cover_path = os.path.join(tmpdir, cover_filename)
                with open(cover_path, "wb") as cover_file:
                    cover_bytes = cover.file.read()
                    cover_file.write(cover_bytes)
                    cover.file.seek(0)

            epub_path = os.path.join(tmpdir, epub_filename)
            convert_to_epub.create_epub(
                chapters=chapters,
                title=title,
                author=author,
                cover_image=cover_path,
                genres=genres,
                tags=tags,
                output_path=epub_path,
                metadata=metadata,
            )
            file_size = os.path.getsize(epub_path)
            s3_url = self.storage.upload_file(epub_path, s3_key)
            return s3_url, file_size

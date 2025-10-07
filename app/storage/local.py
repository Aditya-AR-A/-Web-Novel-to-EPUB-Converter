from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path
from typing import Optional

from app.config import get_settings


class LocalStorage:
    """Local file system storage adapter."""

    def __init__(self) -> None:
        settings = get_settings()
        self.storage_path = Path(settings.local_storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def upload_file(self, file_path: str, object_name: str) -> str:
        """Upload file to local storage and return the storage key."""
        dest_path = self.storage_path / object_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(file_path, dest_path)
        return object_name

    def delete_object(self, object_name: str) -> None:
        """Delete file from local storage."""
        file_path = self.storage_path / object_name
        if file_path.exists():
            file_path.unlink()

    def download_object(self, object_name: str) -> BytesIO:
        """Download file from local storage as BytesIO."""
        file_path = self.storage_path / object_name
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {object_name}")
        
        buffer = BytesIO()
        with open(file_path, "rb") as f:
            buffer.write(f.read())
        buffer.seek(0)
        return buffer

    def generate_presigned_url(self, object_name: str, expires_in: Optional[int] = None) -> str:
        """Generate a download URL for local storage (returns file path)."""
        return f"/download/{object_name}"

    def list_objects(self, prefix: str = "") -> list[str]:
        """List all objects in storage."""
        if prefix:
            search_path = self.storage_path / prefix
        else:
            search_path = self.storage_path
        
        if not search_path.exists():
            return []
        
        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                files.append(str(item.relative_to(self.storage_path)))
        return files

    def get_file_size(self, object_name: str) -> int:
        """Get file size in bytes."""
        file_path = self.storage_path / object_name
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {object_name}")
        return file_path.stat().st_size

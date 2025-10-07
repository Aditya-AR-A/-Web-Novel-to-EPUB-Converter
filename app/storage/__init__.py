from typing import Union

from app.config import get_settings
from .google_drive import GoogleDriveStorage
from .local import LocalStorage
from .s3 import S3Storage

StorageBackend = Union[S3Storage, GoogleDriveStorage, LocalStorage]


def get_storage() -> StorageBackend:
    """Get the configured storage backend."""
    settings = get_settings()
    
    if settings.storage_backend == "s3":
        return S3Storage()
    elif settings.storage_backend == "google_drive":
        return GoogleDriveStorage()
    elif settings.storage_backend == "local":
        return LocalStorage()
    else:
        raise ValueError(f"Unknown storage backend: {settings.storage_backend}")


def get_s3_storage() -> S3Storage:
    """Legacy function for S3 storage."""
    return S3Storage()


__all__ = ["S3Storage", "GoogleDriveStorage", "LocalStorage", "get_s3_storage", "get_storage"]

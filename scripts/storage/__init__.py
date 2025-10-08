"""Storage backends used by the application."""

from .r2 import (
    is_enabled as r2_enabled,
    upload_file as upload_file_to_r2,
    upload_bytes as upload_bytes_to_r2,
    delete_object as delete_r2_object,
    download_bytes as download_r2_bytes,
    get_public_url as r2_public_url,
    list_objects as list_r2_objects,
    object_exists as r2_object_exists,
    connection_status as r2_connection_status,
)

__all__ = [
    "r2_enabled",
    "upload_file_to_r2",
    "upload_bytes_to_r2",
    "delete_r2_object",
    "download_r2_bytes",
    "r2_public_url",
    "list_r2_objects",
    "r2_object_exists",
    "r2_connection_status",
]

from __future__ import annotations

import json
import logging
import mimetypes
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from app.config import get_settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


@dataclass(frozen=True)
class StorageUploadResult:
    file_id: str
    download_url: str


class GoogleDriveStorage:
    """Storage adapter backed by Google Drive."""

    def __init__(self) -> None:
        settings = get_settings()
        if settings.google_service_account_json:
            try:
                info = json.loads(settings.google_service_account_json)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise RuntimeError("Invalid GOOGLE_SERVICE_ACCOUNT_JSON value") from exc
            credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        elif settings.google_service_account_file:
            credentials_path = Path(settings.google_service_account_file)
            if not credentials_path.exists():
                raise RuntimeError("Google service account file not found.")
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path), scopes=SCOPES
            )
        else:
            raise RuntimeError("Google service account credentials not provided.")
        if settings.google_impersonated_user:
            credentials = credentials.with_subject(settings.google_impersonated_user)

        if not settings.google_drive_folder_id and not settings.google_impersonated_user:
            raise RuntimeError(
                "Google Drive storage requires either GOOGLE_DRIVE_FOLDER_ID (shared drive ID) "
                "or GOOGLE_IMPERSONATED_USER for delegated uploads."
            )

        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._folder_id = settings.google_drive_folder_id
        self._download_url_template = "https://drive.google.com/uc?id={file_id}&export=download"

    def upload_file(self, file_path: str, object_name: str) -> StorageUploadResult:
        file_name = Path(object_name).name or Path(file_path).name
        file_metadata: dict[str, object] = {"name": file_name}
        if self._folder_id:
            file_metadata["parents"] = [self._folder_id]

        mime_type, _ = mimetypes.guess_type(file_path)
        media = MediaFileUpload(file_path, mimetype=mime_type or "application/octet-stream", resumable=True)

        try:
            created = (
                self._service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except HttpError as exc:
            message = self._humanize_http_error(exc)
            logger.exception(
                "Failed to upload file to Google Drive",
                extra={"file_name": file_name, "status": getattr(exc, "status_code", None), "error": message},
            )
            raise RuntimeError(message) from exc

        file_id = created["id"]
        self._ensure_public_permission(file_id)
        return StorageUploadResult(file_id=file_id, download_url=self._build_download_url(file_id))

    def delete_object(self, file_id: str) -> None:
        if not file_id:
            return
        try:
            self._service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        except HttpError as exc:
            if getattr(exc, "resp", None) and exc.resp.status == 404:
                logger.debug("Attempted to delete non-existent Google Drive file", extra={"file_id": file_id})
                return
            logger.exception("Failed to delete Google Drive file", extra={"file_id": file_id})
            raise RuntimeError("Failed to delete Google Drive file") from exc

    def download_object(self, file_id: str) -> BytesIO:
        buffer = BytesIO()
        try:
            request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        except HttpError as exc:
            logger.exception("Failed to download Google Drive file", extra={"file_id": file_id})
            raise RuntimeError("Failed to download Google Drive file") from exc

        buffer.seek(0)
        return buffer

    def generate_presigned_url(self, file_id: str, expires_in: Optional[int] = None) -> str:
        if not file_id:
            raise ValueError("file_id is required")
        return self._build_download_url(file_id)

    def health_check(self) -> None:
        try:
            if self._folder_id:
                self._service.files().get(
                    fileId=self._folder_id,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()
            else:
                self._service.files().list(
                    pageSize=1,
                    fields="files(id)",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                ).execute()
        except HttpError as exc:
            logger.exception("Google Drive health check failed")
            raise RuntimeError("Google Drive storage initialization failed") from exc

    def _ensure_public_permission(self, file_id: str) -> None:
        try:
            self._service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id",
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            # Ignore errors for existing permissions
            if getattr(exc, "resp", None) and exc.resp.status in {400, 403} and "already" in str(exc).lower():
                logger.debug("Permission already set for file", extra={"file_id": file_id})
                return
            logger.exception("Failed to set Google Drive permissions", extra={"file_id": file_id})
            raise RuntimeError("Failed to set Google Drive permissions") from exc

    def _build_download_url(self, file_id: str) -> str:
        return self._download_url_template.format(file_id=file_id)

    @staticmethod
    def _humanize_http_error(exc: HttpError) -> str:
        """Return a user friendly error message for Drive API failures."""

        status = getattr(exc, "resp", None).status if getattr(exc, "resp", None) else None
        reason = ""
        details = None
        if getattr(exc, "content", None):
            try:
                payload = json.loads(exc.content.decode() if isinstance(exc.content, bytes) else exc.content)
                if isinstance(payload, dict):
                    error = payload.get("error")
                    if isinstance(error, dict):
                        reason = error.get("message") or ""
                        details = error.get("errors")
                        if isinstance(details, list) and details:
                            reason = details[0].get("message", reason)
            except Exception:  # pragma: no cover - best effort parsing
                pass

        if details and isinstance(details, list):
            for item in details:
                if isinstance(item, dict) and item.get("reason") == "storageQuotaExceeded":
                    return (
                        "Google Drive upload failed: service account storage quota exceeded. "
                        "Assign the service account to a shared drive via GOOGLE_DRIVE_FOLDER_ID "
                        "or enable domain-wide delegation with GOOGLE_IMPERSONATED_USER."
                    )

        if status == 403 and reason:
            return f"Google Drive upload failed: {reason}"

        if reason:
            return f"Google Drive upload failed: {reason}"

        return "Failed to upload file to Google Drive"


@lru_cache()
def get_drive_storage() -> GoogleDriveStorage:
    return GoogleDriveStorage()

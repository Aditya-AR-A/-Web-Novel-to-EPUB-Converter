from __future__ import annotations

import logging
from functools import lru_cache
from io import BytesIO
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from app.config import get_settings

logger = logging.getLogger(__name__)


class S3Storage:
    """Wrapper around S3 client to encapsulate storage operations."""

    def __init__(self) -> None:
        settings = get_settings()
        bucket = settings.resolved_s3_bucket
        if not bucket:
            raise RuntimeError("AWS_S3_BUCKET configuration is required.")

        self.bucket = bucket
        session_kwargs = {}
        if settings.resolved_s3_access_key_id and settings.resolved_s3_secret_access_key:
            session_kwargs["aws_access_key_id"] = settings.resolved_s3_access_key_id
            session_kwargs["aws_secret_access_key"] = settings.resolved_s3_secret_access_key
        if settings.resolved_s3_region:
            session_kwargs["region_name"] = settings.resolved_s3_region
        if settings.resolved_s3_endpoint_url:
            session_kwargs["endpoint_url"] = settings.resolved_s3_endpoint_url

        try:
            self._client = boto3.client("s3", **session_kwargs)
        except (BotoCoreError, NoCredentialsError) as exc:
            raise RuntimeError("Failed to initialize S3 client.") from exc

        self._presign_expiration = settings.s3_presign_expiration

    def upload_file(self, file_path: str, object_key: str) -> str:
        try:
            self._client.upload_file(file_path, self.bucket, object_key)
        except (ClientError, FileNotFoundError) as exc:
            logger.exception("Failed to upload file to S3", extra={"key": object_key})
            raise RuntimeError("Failed to upload file to S3") from exc
        return self.generate_presigned_url(object_key)

    def delete_object(self, object_key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=object_key)
        except ClientError as exc:
            logger.exception("Failed to delete S3 object", extra={"key": object_key})
            raise RuntimeError("Failed to delete S3 object") from exc

    def download_object(self, object_key: str) -> BytesIO:
        buffer = BytesIO()
        try:
            self._client.download_fileobj(self.bucket, object_key, buffer)
        except ClientError as exc:
            logger.exception("Failed to download S3 object", extra={"key": object_key})
            raise RuntimeError("Failed to download S3 object") from exc
        buffer.seek(0)
        return buffer

    def generate_presigned_url(self, object_key: str, expires_in: Optional[int] = None) -> str:
        expiration = expires_in or self._presign_expiration
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=expiration,
            )
        except ClientError as exc:
            logger.exception("Failed to generate presigned URL", extra={"key": object_key})
            raise RuntimeError("Failed to generate presigned URL") from exc

    def list_objects(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item.get("Key")
                    if key:
                        keys.append(key)
        except ClientError as exc:
            logger.exception("Failed to list S3 objects", extra={"prefix": prefix})
            raise RuntimeError("Failed to list S3 objects") from exc
        return keys


@lru_cache()
def get_s3_storage() -> S3Storage:
    return S3Storage()

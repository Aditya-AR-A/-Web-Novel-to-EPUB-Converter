from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

DEFAULT_BUCKET = "webnovel"
DEFAULT_S3_API_WITH_BUCKET = "https://d34b8bd1d8c0a61aca5f3c55056313c6.r2.cloudflarestorage.com/webnovel"


@lru_cache(maxsize=1)
def _settings() -> dict:
    bucket = (
        os.getenv("R2_BUCKET")
        or os.getenv("CLOUDFLARE_R2_BUCKET")
        or DEFAULT_BUCKET
    )
    raw_endpoint = (
        os.getenv("R2_ENDPOINT_URL")
        or os.getenv("R2_S3_API_URL")
        or os.getenv("CLOUDFLARE_R2_S3_API")
        or DEFAULT_S3_API_WITH_BUCKET
    )
    public_base = (
        os.getenv("R2_PUBLIC_BASE_URL")
        or os.getenv("CLOUDFLARE_R2_PUBLIC_BASE_URL")
        or None
    )
    access_key = (
        os.getenv("R2_ACCESS_KEY_ID")
        or os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID")
        or None
    )
    secret_key = (
        os.getenv("R2_SECRET_ACCESS_KEY")
        or os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
        or None
    )
    account_id = (
        os.getenv("R2_ACCOUNT_ID")
        or os.getenv("CLOUDFLARE_R2_ACCOUNT_ID")
        or None
    )
    region = os.getenv("R2_REGION") or os.getenv("CLOUDFLARE_R2_REGION") or "auto"

    endpoint = None
    normalized_public = public_base.rstrip("/") if public_base else None

    if raw_endpoint:
        raw_endpoint = raw_endpoint.rstrip("/")
        suffix = f"/{bucket}"
        if raw_endpoint.endswith(suffix):
            endpoint = raw_endpoint[: -len(suffix)]
            if not normalized_public:
                normalized_public = raw_endpoint
        else:
            endpoint = raw_endpoint
            if not normalized_public:
                normalized_public = f"{raw_endpoint}/{bucket}".rstrip("/")

    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        if not normalized_public:
            normalized_public = f"{endpoint}/{bucket}".rstrip("/")

    return {
        "bucket": bucket,
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "region": region,
        "public_base": normalized_public,
    }


@lru_cache(maxsize=1)
def _client():
    settings = _settings()
    if not settings["endpoint"] or not settings["access_key"] or not settings["secret_key"]:
        return None
    session = boto3.session.Session()
    return session.client(
        "s3",
        endpoint_url=settings["endpoint"],
        aws_access_key_id=settings["access_key"],
        aws_secret_access_key=settings["secret_key"],
        region_name=settings["region"],
        config=BotoConfig(signature_version="s3v4"),
    )


def is_enabled() -> bool:
    return _client() is not None


def _sanitize_key(key: str) -> str:
    return key.lstrip("/")


def get_public_url(key: str) -> Optional[str]:
    settings = _settings()
    base = settings.get("public_base")
    if not base:
        return None
    clean_key = _sanitize_key(key)
    return f"{base}/{clean_key}"


def upload_file(path: str, key: str, content_type: Optional[str] = None) -> Optional[str]:
    client = _client()
    if not client:
        return None
    clean_key = _sanitize_key(key)
    extra_args = {"ContentType": content_type} if content_type else None
    try:
        if extra_args:
            client.upload_file(path, _settings()["bucket"], clean_key, ExtraArgs=extra_args)
        else:
            client.upload_file(path, _settings()["bucket"], clean_key)
    except (ClientError, BotoCoreError) as exc:
        print(f"[R2] Failed to upload {clean_key}: {exc}")
        return None
    return get_public_url(clean_key)


def upload_bytes(data: bytes, key: str, content_type: Optional[str] = None) -> Optional[str]:
    client = _client()
    if not client:
        return None
    clean_key = _sanitize_key(key)
    try:
        kwargs = {
            "Bucket": _settings()["bucket"],
            "Key": clean_key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        client.put_object(**kwargs)
    except (ClientError, BotoCoreError) as exc:
        print(f"[R2] Failed to upload bytes for {clean_key}: {exc}")
        return None
    return get_public_url(clean_key)


def download_bytes(key: str) -> Optional[bytes]:
    client = _client()
    if not client:
        return None
    clean_key = _sanitize_key(key)
    try:
        obj = client.get_object(Bucket=_settings()["bucket"], Key=clean_key)
        return obj["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        print(f"[R2] Failed to download {clean_key}: {exc}")
        return None


def delete_object(key: str) -> bool:
    client = _client()
    if not client:
        return False
    clean_key = _sanitize_key(key)
    try:
        client.delete_object(Bucket=_settings()["bucket"], Key=clean_key)
        return True
    except (ClientError, BotoCoreError) as exc:
        print(f"[R2] Failed to delete {clean_key}: {exc}")
        return False


def connection_status() -> Dict[str, Any]:
    """Return a diagnostic snapshot of the current R2 configuration."""

    settings = _settings()
    required_fields = {
        "endpoint": "R2_ENDPOINT_URL",
        "access_key": "R2_ACCESS_KEY_ID",
        "secret_key": "R2_SECRET_ACCESS_KEY",
    }
    missing = [env for key, env in required_fields.items() if not settings.get(key)]

    return {
        "enabled": is_enabled(),
        "bucket": settings.get("bucket"),
        "endpoint": settings.get("endpoint"),
        "public_base": settings.get("public_base"),
        "missing": missing,
        "region": settings.get("region"),
    }


def list_objects(prefix: Optional[str] = None, max_keys: int = 100) -> List[Dict[str, Any]]:
    """Return a shallow listing of objects under the optional prefix."""

    client = _client()
    if not client:
        return []

    clean_prefix = _sanitize_key(prefix) if prefix else None
    params: Dict[str, Any] = {
        "Bucket": _settings()["bucket"],
        "MaxKeys": max(1, min(max_keys, 1000)),
    }
    if clean_prefix:
        params["Prefix"] = clean_prefix

    try:
        response = client.list_objects_v2(**params)
    except (ClientError, BotoCoreError) as exc:
        print(f"[R2] Failed to list objects: {exc}")
        return []

    contents = response.get("Contents", [])
    output: List[Dict[str, Any]] = []
    for item in contents:
        key = item.get("Key")
        if not key:
            continue
        output.append(
            {
                "key": key,
                "size": item.get("Size"),
                "last_modified": item.get("LastModified"),
            }
        )
    return output


def object_exists(key: str) -> bool:
    client = _client()
    if not client:
        return False

    clean_key = _sanitize_key(key)
    try:
        client.head_object(Bucket=_settings()["bucket"], Key=clean_key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code") if hasattr(exc, "response") else None
        if error_code in {"404", "NoSuchKey"}:
            return False
        print(f"[R2] Error checking object {clean_key}: {exc}")
        return False
    except BotoCoreError as exc:
        print(f"[R2] Error checking object {clean_key}: {exc}")
        return False

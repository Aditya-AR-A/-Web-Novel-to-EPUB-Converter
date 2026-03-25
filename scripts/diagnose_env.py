#!/usr/bin/env python3
"""Safe environment diagnostics for deployment debugging.

This script helps verify that runtime secrets are loaded, without exposing
full secret values. It is safe to run in logs because values are masked.
"""

from __future__ import annotations

import os
from typing import Iterable

CHECK_GROUPS = {
    "Core": [
        "STORAGE_BACKEND",
        "DATABASE_URL",
        "LOCAL_STORAGE_PATH",
    ],
    "AWS S3 (app native)": [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_S3_BUCKET",
        "AWS_REGION",
        "AWS_S3_ENDPOINT_URL",
    ],
    "Cloudflare R2 (alias support)": [
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
        "R2_REGION",
        "R2_ENDPOINT_URL",
        "CLOUDFLARE_API_TOKEN",
        "CLOUD_FLARE_ACCOUNT_ID",
        "CLOUDFLARE_S3_API",
    ],
    "Google Drive": [
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "GOOGLE_DRIVE_FOLDER_ID",
        "GOOGLE_IMPERSONATED_USER",
    ],
}


def mask_value(value: str) -> str:
    value = value.strip()
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} (len={len(value)})"


def print_group(title: str, keys: Iterable[str]) -> None:
    print(f"\n[{title}]")
    for key in keys:
        raw = os.getenv(key)
        if raw is None:
            print(f"- {key}: MISSING")
        elif raw == "":
            print(f"- {key}: SET but empty")
        else:
            print(f"- {key}: SET {mask_value(raw)}")


def main() -> None:
    print("Environment diagnostics (masked)\n")
    for group, keys in CHECK_GROUPS.items():
        print_group(group, keys)

    storage_backend = os.getenv("STORAGE_BACKEND", "local")
    print("\n[Quick checks]")
    if storage_backend == "s3":
        required_any = [
            ("AWS_S3_BUCKET", "R2_BUCKET"),
            ("AWS_ACCESS_KEY_ID", "R2_ACCESS_KEY_ID"),
            ("AWS_SECRET_ACCESS_KEY", "R2_SECRET_ACCESS_KEY"),
        ]
        missing = []
        for a, b in required_any:
            if not os.getenv(a) and not os.getenv(b):
                missing.append(f"{a} or {b}")
        if missing:
            print("- S3 backend requirements: MISSING -> " + ", ".join(missing))
        else:
            print("- S3 backend requirements: looks OK")
    elif storage_backend == "google_drive":
        if not os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") and not os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"):
            print("- Google Drive requirements: MISSING service account JSON/file")
        else:
            print("- Google Drive requirements: looks OK")
    else:
        print("- Local backend selected; cloud credentials not required")


if __name__ == "__main__":
    main()

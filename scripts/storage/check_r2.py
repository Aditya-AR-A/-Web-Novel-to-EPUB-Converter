"""Utility CLI to verify Cloudflare R2 connectivity and basic operations.

Usage:
    python -m scripts.storage.check_r2 [--prefix books/] [--max-keys 20] [--probe]

The command prints the current connection status, lists a subset of objects,
and (optionally) performs an upload/download/delete probe to ensure end-to-end
access is functional.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pprint import pprint
from typing import List

from . import (
    delete_r2_object,
    download_r2_bytes,
    list_r2_objects,
    r2_connection_status,
    upload_bytes_to_r2,
)


def _print_listing(items: List[dict]) -> None:
    if not items:
        print("No objects found for the given prefix (or bucket is empty).")
        return

    print(f"Listing {len(items)} object(s):")
    for entry in items:
        modified = entry.get("last_modified")
        if hasattr(modified, "astimezone"):
            modified = modified.astimezone(timezone.utc).isoformat()
        size = entry.get("size")
        print(f"  - {entry.get('key')} (size={size} bytes, modified={modified})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose Cloudflare R2 connectivity")
    parser.add_argument("--prefix", default="", help="Prefix to filter the listing (e.g. books/)")
    parser.add_argument("--max-keys", type=int, default=25, help="Maximum objects to list (default: 25)")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Upload, download, and delete a temporary object to verify full access",
    )
    args = parser.parse_args(argv)

    status = r2_connection_status()
    print("R2 connection status:")
    pprint(status)

    if not status.get("enabled"):
        print("Cloudflare R2 client is not enabled. Check missing credentials above.")
        return 1

    listing = list_r2_objects(prefix=args.prefix or None, max_keys=args.max_keys)
    _print_listing(listing)

    if not args.probe:
        return 0

    probe_key = f"diagnostics/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_probe.txt"
    payload = f"diagnostic probe at {datetime.now(timezone.utc).isoformat()}".encode()

    print(f"\nUploading probe object to {probe_key}...")
    public_url = upload_bytes_to_r2(payload, probe_key, content_type="text/plain")
    if not public_url:
        print("Upload failed; aborting probe.")
        return 2
    print(f"Upload succeeded. Public URL (if configured): {public_url}")

    downloaded = download_r2_bytes(probe_key)
    if downloaded != payload:
        print("Downloaded bytes did not match uploaded payload! Cleaning up anyway.")
    else:
        print("Download verification succeeded.")

    if delete_r2_object(probe_key):
        print("Probe object deleted successfully.")
    else:
        print("Warning: failed to delete probe object. Please remove it manually if needed.")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

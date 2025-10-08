"""Centralized configuration helpers shared across the project."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent


def _resolve_books_dir() -> Path:
    """Determine a writable directory for generated EPUB assets."""

    env_value = os.getenv("BOOKS_DIR")
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    default = ROOT_DIR / "books"
    try:
        default.mkdir(parents=True, exist_ok=True)
        test_file = default / ".write-test"
        with test_file.open("w", encoding="utf-8") as handle:
            handle.write("ok")
        test_file.unlink(missing_ok=True)
        return default
    except OSError:
        tmp_dir = Path(tempfile.gettempdir()) / "webnovel-books"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir


BOOKS_DIR: Final[Path] = _resolve_books_dir()
METADATA_FILENAME: Final[str] = "metadata.json"
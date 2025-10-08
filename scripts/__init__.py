"""Shared package initialization for the `scripts` namespace.

This module eagerly loads environment variables from a `.env` file if
`python-dotenv` is available. Doing so ensures that any modules importing
`scripts` receive the expected configuration without each one repeating
their own loader logic.
"""

from __future__ import annotations

from pathlib import Path


def _load_env() -> None:
    """Load environment variables from a project-local `.env` file.

    We attempt to import `dotenv` lazily so the package remains optional in
    contexts where it is not installed (e.g., production containers that rely
    solely on real environment variables). Missing dependencies simply skip
    the load instead of raising an ImportError at import time.
    """

    if getattr(_load_env, "_loaded", False):
        return

    try:
        from dotenv import load_dotenv  # type: ignore import-not-found
    except Exception:  # pragma: no cover - best-effort optional dependency
        setattr(_load_env, "_loaded", True)
        return

    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"

    if env_file.exists():
        load_dotenv(env_file, override=False)
    else:
        # Fall back to default search behaviour so `python-dotenv` can still
        # pick up an env file placed elsewhere (e.g., parent directory).
        load_dotenv(override=False)

    setattr(_load_env, "_loaded", True)


_load_env()

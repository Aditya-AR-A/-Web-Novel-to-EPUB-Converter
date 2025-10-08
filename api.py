"""
Compatibility wrapper for legacy imports.

This project has been modularized. The FastAPI application is now created in
`scripts.api.create_app()` and exported as `scripts.api.app`. This file simply
re-exports that `app` so existing commands like `uvicorn api:app` continue to work.
"""

from scripts.api import app  # noqa: F401

from fastapi.responses import JSONResponse

from scripts.config import ROOT_DIR as _ROOT_DIR, BOOKS_DIR as _BOOKS_DIR


ROOT_DIR = str(_ROOT_DIR)
BOOKS_DIR = str(_BOOKS_DIR)


def success(data=None):
    return {"ok": True, "data": data}


def error(message: str, code: str = "error", status: int = 400):
    return JSONResponse({"ok": False, "error": {"code": code, "message": message}}, status_code=status)

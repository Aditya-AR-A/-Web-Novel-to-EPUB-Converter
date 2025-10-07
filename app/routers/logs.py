from __future__ import annotations
import asyncio
import threading
from typing import List, Tuple, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import FastAPI

router = APIRouter()

LOG_BUFFER: List[Tuple[int, str]] = []  # (seq, line)
_LOG_SEQ = 0
_LOG_LOCK = threading.Lock()
_WS_CONNECTIONS: Set[WebSocket] = set()
_ASYNC_QUEUE: asyncio.Queue[Tuple[int, str]] | None = None
_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
_BROADCAST_TASK: asyncio.Task | None = None


def _append_log_line(line: str):
    if not line:
        return
    global _LOG_SEQ
    with _LOG_LOCK:
        _LOG_SEQ += 1
        LOG_BUFFER.append((_LOG_SEQ, line))
        if len(LOG_BUFFER) > _StdoutTee.MAX_LINES:
            del LOG_BUFFER[: len(LOG_BUFFER) - _StdoutTee.MAX_LINES]
    if _EVENT_LOOP is not None:
        def _enqueue():
            global _ASYNC_QUEUE
            if _ASYNC_QUEUE is None:
                _ASYNC_QUEUE = asyncio.Queue()
            _ASYNC_QUEUE.put_nowait((_LOG_SEQ, line))
        try:
            _EVENT_LOOP.call_soon_threadsafe(_enqueue)
        except Exception:
            pass


class _StdoutTee:
    MAX_LINES = 1500
    def __init__(self, original_stream):
        self.original = original_stream
        self._buf = ''
    def write(self, data: str):
        if not isinstance(data, str):
            data = str(data)
        self.original.write(data)
        self._buf += data
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            _append_log_line(line.rstrip())
    def flush(self):
        self.original.flush()
    def isatty(self):
        return getattr(self.original, 'isatty', lambda: False)()
    def fileno(self):
        return getattr(self.original, 'fileno', lambda: 1)()
    def writelines(self, lines):
        for line in lines:
            self.write(line)
    def __getattr__(self, item):
        return getattr(self.original, item)


async def _broadcast_worker():
    global _ASYNC_QUEUE
    if _ASYNC_QUEUE is None:
        _ASYNC_QUEUE = asyncio.Queue()
    try:
        while True:
            batch = [await _ASYNC_QUEUE.get()]
            try:
                for _ in range(200):
                    batch.append(_ASYNC_QUEUE.get_nowait())
            except asyncio.QueueEmpty:
                pass
            if not _WS_CONNECTIONS:
                continue
            payload = {"lines": [{"seq": s, "line": line} for s, line in batch]}
            dead = []
            for conn in list(_WS_CONNECTIONS):
                try:
                    await conn.send_json(payload)
                except Exception:
                    dead.append(conn)
            for d in dead:
                _WS_CONNECTIONS.discard(d)
    except asyncio.CancelledError:
        pass


def setup_logging(app: FastAPI):
    import sys
    global _EVENT_LOOP, _BROADCAST_TASK

    if not isinstance(sys.stdout, _StdoutTee):
        sys.stdout = _StdoutTee(sys.stdout)  # type: ignore
    if not isinstance(sys.stderr, _StdoutTee):
        sys.stderr = _StdoutTee(sys.stderr)  # type: ignore

    @app.on_event("startup")
    async def _startup_loop_refs():  # type: ignore
        global _EVENT_LOOP, _BROADCAST_TASK
        _EVENT_LOOP = asyncio.get_running_loop()
        if _BROADCAST_TASK is None or _BROADCAST_TASK.done():
            _BROADCAST_TASK = asyncio.create_task(_broadcast_worker())


@router.get("/logs")
def poll_logs(since: int = 0, limit: int = 400):
    with _LOG_LOCK:
        if since <= 0:
            lines = LOG_BUFFER[-limit:]
        else:
            lines = [t for t in LOG_BUFFER if t[0] > since]
    data = [{"seq": seq, "line": line} for seq, line in lines]
    next_seq = lines[-1][0] if lines else since
    return {"ok": True, "data": {"next": next_seq, "lines": data}}


@router.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket):
    await ws.accept()
    _WS_CONNECTIONS.add(ws)
    with _LOG_LOCK:
        tail = LOG_BUFFER[-300:]
    try:
        if tail:
            await ws.send_json({"lines": [{"seq": s, "line": line} for s, line in tail]})
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"ping": True})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        _WS_CONNECTIONS.discard(ws)

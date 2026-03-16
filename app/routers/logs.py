from __future__ import annotations
import asyncio
import threading
import collections
from typing import List, Tuple, Set, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import FastAPI
from scripts.cancellation import session_id_var

router = APIRouter()

LOG_BUFFER: Dict[str, List[Tuple[int, str]]] = collections.defaultdict(list)
_LOG_SEQ: Dict[str, int] = {}
_LOG_LOCK = threading.Lock()
_WS_CONNECTIONS: Dict[str, Set[WebSocket]] = collections.defaultdict(set)
_ASYNC_QUEUE: asyncio.Queue[Tuple[str, int, str]] | None = None
_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
_BROADCAST_TASK: asyncio.Task | None = None


def _append_log_line(line: str):
    if not line:
        return
    sid = session_id_var.get()
    with _LOG_LOCK:
        seq = _LOG_SEQ.get(sid, 0) + 1
        _LOG_SEQ[sid] = seq
        LOG_BUFFER[sid].append((seq, line))
        if len(LOG_BUFFER[sid]) > _StdoutTee.MAX_LINES:
            del LOG_BUFFER[sid][: len(LOG_BUFFER[sid]) - _StdoutTee.MAX_LINES]
    if _EVENT_LOOP is not None:
        def _enqueue():
            global _ASYNC_QUEUE
            if _ASYNC_QUEUE is None:
                _ASYNC_QUEUE = asyncio.Queue()
            _ASYNC_QUEUE.put_nowait((sid, seq, line))
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
            
            by_sid = collections.defaultdict(list)
            for sid, s, l in batch:
                by_sid[sid].append({"seq": s, "line": l})
            
            for sid, items in by_sid.items():
                payload = {"lines": items}
                targets = list(_WS_CONNECTIONS.get(sid, []))
                # Only broadcast to targets in this session
                targets = list(_WS_CONNECTIONS.get(sid, []))
                    
                if not targets:
                    continue
                    
                dead = []
                for conn in targets:
                    try:
                        await conn.send_json(payload)
                    except Exception:
                        dead.append(conn)
                for d in dead:
                    for s_set in _WS_CONNECTIONS.values():
                        s_set.discard(d)
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
def poll_logs(since: int = 0, limit: int = 400, session_id: str = "default"):
    with _LOG_LOCK:
        buf = LOG_BUFFER[session_id]
        if since <= 0:
            lines = buf[-limit:]
        else:
            lines = [t for t in buf if t[0] > since]
    data = [{"seq": seq, "line": line} for seq, line in lines]
    next_seq = lines[-1][0] if lines else since
    return {"ok": True, "data": {"next": next_seq, "lines": data}}


@router.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket, session_id: str = "default"):
    await ws.accept()
    _WS_CONNECTIONS[session_id].add(ws)
    with _LOG_LOCK:
        tail = LOG_BUFFER[session_id][-300:]
        if session_id != 'default':
            sys_tail = LOG_BUFFER['default'][-300:]
            tail = sorted(tail + sys_tail, key=lambda x: x[0])[-300:]
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
        _WS_CONNECTIONS[session_id].discard(ws)

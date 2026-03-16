import threading
import contextvars

# Global cancellation token system with session isolation.
session_id_var = contextvars.ContextVar('session_id', default='default')

class SessionState:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.stop_event = threading.Event()
        self.active_job_id: str | None = None

_sessions: dict[str, SessionState] = {}
_lock = threading.Lock()

def get_state() -> SessionState:
    sid = session_id_var.get()
    with _lock:
        if sid not in _sessions:
            _sessions[sid] = SessionState()
        return _sessions[sid]

class CancelledError(RuntimeError):
    pass

class StopRequested(RuntimeError):
    """Raised internally to indicate a graceful stop was requested."""
    pass

def request_cancel(sid: str | None = None):
    sid = sid or session_id_var.get()
    with _lock:
        s = _sessions.get(sid)
        if s:
            s.cancel_event.set()

def request_stop(sid: str | None = None):
    sid = sid or session_id_var.get()
    with _lock:
        s = _sessions.get(sid)
        if s:
            s.stop_event.set()

def clear_cancel(job_id: str | None = None):
    s = get_state()
    with _lock:
        s.cancel_event.clear()

def clear_stop():
    s = get_state()
    with _lock:
        s.stop_event.clear()

def is_cancelled() -> bool:
    return get_state().cancel_event.is_set()

def is_stopped() -> bool:
    return get_state().stop_event.is_set()

def raise_if_cancelled():
    if get_state().cancel_event.is_set():
        raise CancelledError("Operation cancelled by user")

def raise_if_stopped():
    if get_state().stop_event.is_set():
        raise StopRequested("Stop requested")

def start_job(job_id: str):
    s = get_state()
    with _lock:
        if s.active_job_id and s.active_job_id != job_id and not s.cancel_event.is_set():
            raise RuntimeError(f"Another job already active for session {session_id_var.get()}")
        s.active_job_id = job_id
        s.cancel_event.clear()
        s.stop_event.clear()

def end_job(job_id: str):
    s = get_state()
    with _lock:
        if s.active_job_id == job_id:
            s.active_job_id = None
        s.cancel_event.clear()
        s.stop_event.clear()

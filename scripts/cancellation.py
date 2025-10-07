import threading

# Simple global cancellation token system.
# For a multi-user system you'd namespace this per job; here we assume single active job.

_cancel_event = threading.Event()
_stop_event = threading.Event()
_lock = threading.Lock()
_active_job_id: str | None = None

class CancelledError(RuntimeError):
    pass

class StopRequested(RuntimeError):
    """Raised internally to indicate a graceful stop was requested."""
    pass

def request_cancel():
    with _lock:
        _cancel_event.set()

def request_stop():
    with _lock:
        _stop_event.set()

def clear_cancel(job_id: str | None = None):
    with _lock:
        # Only clear if job matches or no job tracking specified
        _cancel_event.clear()
        if job_id is not None and _active_job_id == job_id:
            pass

def clear_stop():
    with _lock:
        _stop_event.clear()

def is_cancelled() -> bool:
    return _cancel_event.is_set()

def is_stopped() -> bool:
    return _stop_event.is_set()

def raise_if_cancelled():
    if _cancel_event.is_set():
        raise CancelledError("Operation cancelled by user")

def raise_if_stopped():
    if _stop_event.is_set():
        raise StopRequested("Stop requested")

def start_job(job_id: str):
    global _active_job_id
    with _lock:
        if _active_job_id and _active_job_id != job_id and not _cancel_event.is_set():
            raise RuntimeError("Another job already active")
        _active_job_id = job_id
        _cancel_event.clear()
        _stop_event.clear()

def end_job(job_id: str):
    global _active_job_id
    with _lock:
        if _active_job_id == job_id:
            _active_job_id = None
        _cancel_event.clear()
        _stop_event.clear()

import threading
import contextvars

# Global cancellation token system namespaced by job.
# Context variables allow concurrent tasks/threads to track their own job_id.

_jobs = {}  # job_id -> {"cancel_event": threading.Event(), "stop_event": threading.Event()}
_lock = threading.Lock()
job_context = contextvars.ContextVar('job_id', default=None)

class CancelledError(RuntimeError):
    pass

class StopRequested(RuntimeError):
    """Raised internally to indicate a graceful stop was requested."""
    pass

def request_cancel():
    with _lock:
        for job in _jobs.values():
            job["cancel_event"].set()

def request_stop():
    with _lock:
        for job in _jobs.values():
            job["stop_event"].set()

def clear_cancel(job_id: str | None = None):
    with _lock:
        if job_id and job_id in _jobs:
            _jobs[job_id]["cancel_event"].clear()
        elif not job_id:
            for job in _jobs.values():
                job["cancel_event"].clear()

def clear_stop():
    with _lock:
        for job in _jobs.values():
            job["stop_event"].clear()

def _get_current_job():
    job_id = job_context.get()
    if job_id and job_id in _jobs:
        return _jobs[job_id]
    return None

def is_cancelled() -> bool:
    job = _get_current_job()
    return job["cancel_event"].is_set() if job else False

def is_stopped() -> bool:
    job = _get_current_job()
    return job["stop_event"].is_set() if job else False

def raise_if_cancelled():
    if is_cancelled():
        raise CancelledError("Operation cancelled by user")

def raise_if_stopped():
    if is_stopped():
        raise StopRequested("Stop requested")

def start_job(job_id: str):
    with _lock:
        if job_id not in _jobs:
            _jobs[job_id] = {
                "cancel_event": threading.Event(),
                "stop_event": threading.Event()
            }
        _jobs[job_id]["cancel_event"].clear()
        _jobs[job_id]["stop_event"].clear()
    job_context.set(job_id)

def end_job(job_id: str):
    with _lock:
        if job_id in _jobs:
            del _jobs[job_id]

"""
Background job manager.

Long-running work (model training, bulk prediction) runs on a worker pool
instead of blocking a web request. Job state is persisted in the `jobs`
table, so the UI can poll /jobs/<id> for live progress and results.

The public surface -- submit(), get(), wait(), active() -- is deliberately
the same shape a Celery + Redis deployment would expose. Swapping the
engine later means re-implementing this one module, not touching callers.
"""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import execute, query_one, query_all
from core.logging_setup import get_logger

log = get_logger("jobs")

_executor = None
_executor_lock = threading.Lock()
_futures = {}


def _get_executor():
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=config.JOB_WORKERS, thread_name_prefix="job")
        return _executor


def submit(name, fn, *args, submitted_by=None, **kwargs):
    """Queue `fn(progress, *args, **kwargs)`; returns the job id.
    `progress(percent, message=None)` lets the task report status."""
    job_id = uuid4().hex[:12]
    execute(
        "INSERT INTO jobs (id, name, status, progress, message, submitted_by) VALUES (?, ?, 'queued', 0, 'Queued', ?)",
        (job_id, name, submitted_by),
    )
    if config.JOBS_SYNC:
        _run(job_id, fn, args, kwargs)
    else:
        _futures[job_id] = _get_executor().submit(_run, job_id, fn, args, kwargs)
    return job_id


def _run(job_id, fn, args, kwargs):
    execute("UPDATE jobs SET status='running', started_at=datetime('now'), message='Running' WHERE id=?", (job_id,))

    def progress(percent, message=None):
        execute("UPDATE jobs SET progress=?, message=COALESCE(?, message) WHERE id=?",
                (max(0, min(100, int(percent))), message, job_id))

    try:
        result = fn(progress, *args, **kwargs)
        execute(
            "UPDATE jobs SET status='succeeded', progress=100, message='Done', result_json=?, "
            "finished_at=datetime('now') WHERE id=?",
            (json.dumps(result, default=str), job_id),
        )
    except Exception as exc:  # a failed job must never take the worker down
        log.exception("Job %s failed", job_id)
        execute("UPDATE jobs SET status='failed', message='Failed', error=?, finished_at=datetime('now') WHERE id=?",
                (str(exc), job_id))


def _row_to_dict(row):
    if row is None:
        return None
    data = dict(row)
    raw = data.pop("result_json", None)
    data["result"] = json.loads(raw) if raw else None
    return data


def get(job_id):
    return _row_to_dict(query_one("SELECT * FROM jobs WHERE id = ?", (job_id,)))


def active(name):
    """The id of a queued/running job with this name, if any."""
    row = query_one("SELECT id FROM jobs WHERE name = ? AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1", (name,))
    return row["id"] if row else None


def wait(job_id, timeout=120):
    """Block until the job finishes (tests / scripts). Returns the job dict."""
    future = _futures.get(job_id)
    if future is not None:
        future.result(timeout=timeout)
    return get(job_id)


def recent(limit=10):
    return [_row_to_dict(r) for r in query_all("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))]


def stats():
    rows = query_all("SELECT status, COUNT(*) AS c FROM jobs GROUP BY status")
    return {r["status"]: r["c"] for r in rows}


def recover_stale():
    """Jobs left 'running' by a crashed/restarted process can never finish --
    mark them failed on startup so the UI doesn't wait on them forever."""
    execute("UPDATE jobs SET status='failed', message='Interrupted by restart', error='Process restarted', "
            "finished_at=datetime('now') WHERE status IN ('queued','running')")


def shutdown():
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False)
            _executor = None

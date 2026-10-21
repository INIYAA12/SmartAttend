import time

from flask import Blueprint, jsonify

import config
from database.db import query_one
from core import jobs
from ml import registry

system_bp = Blueprint("system", __name__)
_started = time.time()


@system_bp.route("/health")
def health():
    """Unauthenticated liveness/readiness probe for load balancers and
    uptime monitors. Reports component status only -- no student data."""
    checks = {}
    ok = True
    try:
        row = query_one("SELECT COUNT(*) AS n FROM schema_migrations")
        checks["database"] = {"status": "ok", "migrations_applied": row["n"]}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        ok = False

    live = registry.get_current_version()
    checks["model"] = {"status": "ok" if live else "missing", "version": live}

    try:
        from face_reco import recognizer
        info = recognizer.gallery_info()
    except Exception:
        info = None
    checks["face_gallery"] = {"status": "ok" if info else "empty", **(info or {})}

    try:
        from face_reco.camera_worker import get_manager
        mgr = get_manager()
        checks["camera"] = {"status": "running" if mgr.is_running() else "idle",
                            "session": mgr.current.kind if mgr.current else None}
    except Exception:
        checks["camera"] = {"status": "unknown"}

    try:
        checks["jobs"] = jobs.stats()
    except Exception:
        checks["jobs"] = {}

    body = {"status": "ok" if ok else "degraded", "version": config.APP_VERSION, "env": config.ENV,
            "uptime_seconds": int(time.time() - _started), "checks": checks}
    return jsonify(body), (200 if ok else 503)

"""Audit trail: who did what, when. Never allowed to break the request."""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import execute, query_all
from core.logging_setup import get_logger

log = get_logger("audit")


def log_event(action, entity=None, entity_id=None, details=None, username=None, role=None):
    """Record an event. Username/role/IP come from the Flask request when
    there is one; background jobs pass `username` explicitly."""
    try:
        ip = None
        try:
            from flask import session, request, has_request_context
            if has_request_context():
                username = username or session.get("username")
                role = role or session.get("role")
                ip = request.remote_addr
        except Exception:
            pass
        if details is not None and not isinstance(details, str):
            details = json.dumps(details, default=str)
        execute(
            "INSERT INTO audit_log (username, role, ip, action, entity, entity_id, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, role, ip, action, entity, None if entity_id is None else str(entity_id), details),
        )
    except Exception:
        log.exception("Failed to write audit event %s", action)


def recent_events(limit=200, action_prefix=None):
    if action_prefix:
        return query_all("SELECT * FROM audit_log WHERE action LIKE ? ORDER BY id DESC LIMIT ?",
                         (action_prefix + "%", limit))
    return query_all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

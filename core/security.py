"""CSRF protection, session guards and role-based access control."""

import hmac
import os
import secrets
import sys
from functools import wraps

from flask import session, request, abort, flash, redirect, url_for

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def csrf_token():
    """Per-session token; templates embed it in every POST form, and
    fetch() calls send it in the X-CSRF-Token header."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf_token"] = token
    return token


def csrf_protect():
    """before_request hook: reject state-changing requests without a valid token."""
    if not config.CSRF_ENABLED:
        return
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("_csrf_token", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, description="Security check failed (missing or invalid CSRF token). "
                                   "Reload the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Allow only the listed roles (e.g. 'admin'); others get a clear
    message and are sent back to the dashboard."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                flash("You don't have permission to do that (admin only).", "danger")
                return redirect(url_for("dashboard.index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator

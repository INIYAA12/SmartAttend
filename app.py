"""
Smart Attendance Monitoring and Academic Performance Prediction System.

Run (development):   python app.py
Run (production):    python serve.py
"""

import time
from datetime import timedelta

from flask import Flask, g, request, render_template_string

import config
from core.logging_setup import setup_logging, get_logger
from core.security import csrf_token, csrf_protect

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.students import students_bp
from routes.syllabus import syllabus_bp
from routes.academic import academic_bp
from routes.face import face_bp
from routes.attendance import attendance_bp
from routes.predictions import predictions_bp
from routes.reports import reports_bp
from routes.system import system_bp
from routes.admin import admin_bp

_ERROR_PAGE = """<!doctype html><title>{{ code }}</title>
<body style="font-family:Segoe UI,Arial;max-width:560px;margin:15vh auto;color:#333">
<h2>{{ code }} — {{ title }}</h2><p>{{ message }}</p><p><a href="/">Back to the dashboard</a></p></body>"""


def create_app():
    setup_logging()
    log = get_logger("web")

    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=config.SESSION_LIFETIME_HOURS),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # CSV imports are small; reject anything huge
    )

    for bp in (auth_bp, dashboard_bp, students_bp, syllabus_bp, academic_bp, face_bp,
               attendance_bp, predictions_bp, reports_bp, system_bp, admin_bp):
        app.register_blueprint(bp)

    app.before_request(csrf_protect)

    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()

    @app.after_request
    def _after(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.path.startswith(("/static", "/face/stream")) and hasattr(g, "_t0"):
            log.info("%s %s -> %s (%.0f ms)", request.method, request.path, resp.status_code,
                     (time.perf_counter() - g._t0) * 1000)
        return resp

    @app.context_processor
    def _globals():
        def demo_mode():
            try:
                from database.db import query_one
                row = query_one("SELECT value FROM app_meta WHERE key = 'demo_data'")
                return bool(row and row["value"] == "1")
            except Exception:
                return False
        return {"csrf_token": csrf_token, "demo_mode": demo_mode, "app_version": config.APP_VERSION}

    def _error(code, title, message):
        return render_template_string(_ERROR_PAGE, code=code, title=title, message=message), code

    @app.errorhandler(400)
    def _bad(e):
        return _error(400, "Request rejected", getattr(e, "description", "Bad request."))

    @app.errorhandler(404)
    def _missing(e):
        return _error(404, "Page not found", "Use the sidebar navigation to get back on track.")

    @app.errorhandler(413)
    def _big(e):
        return _error(413, "File too large", "Uploads are limited to 5 MB.")

    @app.errorhandler(500)
    def _boom(e):
        log.exception("Unhandled server error")
        return _error(500, "Something went wrong", "The error was logged. See logs/app.log for details.")

    return app


app = create_app()

if __name__ == "__main__":
    from core.bootstrap import ensure_ready
    ensure_ready()
    # threaded=True is required: the camera page streams video while the
    # browser separately polls status endpoints.
    app.run(debug=config.DEBUG, use_reloader=False, host=config.HOST, port=config.PORT, threaded=True)

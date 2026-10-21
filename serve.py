"""
Production entry point (Waitress -- a pure-Python WSGI server that works on
Windows, Linux and macOS; Gunicorn does not run on Windows).

    python serve.py

One process, many threads: the camera session and job queue live in this
process, so don't run multiple worker processes.
"""

import config
from core.bootstrap import ensure_ready
from core.logging_setup import get_logger


def main():
    ensure_ready()
    from app import app
    from waitress import serve
    get_logger("serve").info("Serving on http://%s:%s (env=%s)", config.HOST, config.PORT, config.ENV)
    serve(app, host=config.HOST, port=config.PORT, threads=8, channel_timeout=120)


if __name__ == "__main__":
    main()

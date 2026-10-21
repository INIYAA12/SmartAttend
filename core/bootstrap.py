"""First-run bootstrap: gets a fresh checkout to a working, populated app
with a single `python app.py` -- no separate seed step to forget."""

import os
import secrets
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.logging_setup import setup_logging, get_logger


def ensure_ready():
    setup_logging()
    log = get_logger("bootstrap")

    from database.db import init_db, query_one, execute
    from core import jobs

    applied = init_db()
    if applied:
        log.info("Applied migrations: %s", ", ".join(applied))
    jobs.recover_stale()

    if query_one("SELECT id FROM users LIMIT 1") is None:
        if config.AUTO_SEED_DEMO:
            log.info("Empty database: seeding built-in demo data (set AUTO_SEED_DEMO=0 to disable).")
            from database import seed
            seed.run(log=log.info)
        else:
            from werkzeug.security import generate_password_hash
            password = os.environ.get("INITIAL_ADMIN_PASSWORD") or secrets.token_urlsafe(10)
            execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                    ("admin", generate_password_hash(password)))
            log.warning("Created initial admin account  ->  username: admin   password: %s", password)

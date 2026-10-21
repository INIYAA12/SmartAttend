"""Authentication with brute-force throttling."""

import os
import sys

from werkzeug.security import check_password_hash, generate_password_hash

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import execute, query_one


class LockedOutError(Exception):
    pass


def _recent_failures(username):
    row = query_one(
        "SELECT COUNT(*) AS c FROM login_attempts WHERE username = ? AND success = 0 "
        "AND attempted_at > datetime('now', ?)",
        (username, f"-{config.LOGIN_LOCKOUT_MINUTES} minutes"),
    )
    return row["c"]


def is_locked_out(username):
    return _recent_failures(username) >= config.LOGIN_MAX_ATTEMPTS


def _record(username, ip, success):
    execute("INSERT INTO login_attempts (username, ip, success) VALUES (?, ?, ?)",
            (username, ip, 1 if success else 0))


def authenticate(username, password, ip=None):
    """Returns the user row on success, None on bad credentials, and raises
    LockedOutError while the account is throttled. Unknown usernames are
    throttled and recorded the same way as real ones, so the response
    doesn't reveal which usernames exist."""
    if is_locked_out(username):
        raise LockedOutError()
    user = query_one("SELECT * FROM users WHERE username = ?", (username,))
    if user and check_password_hash(user["password_hash"], password):
        execute("DELETE FROM login_attempts WHERE username = ? AND success = 0", (username,))
        _record(username, ip, True)
        return user
    _record(username, ip, False)
    return None


def validate_new_password(password, username=None):
    """Returns an error string, or None if acceptable."""
    if len(password) < config.MIN_PASSWORD_LENGTH:
        return f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters."
    if username and password.lower() == username.lower():
        return "Password can't be the same as the username."
    return None


def hash_password(password):
    return generate_password_hash(password)

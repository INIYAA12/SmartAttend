import sqlite3
import os
import sys
from contextlib import contextmanager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def get_connection():
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL, far fewer fsyncs
    return conn


def init_db():
    """Brings the schema up to date by applying pending migrations."""
    from database.migrate import run_migrations
    return run_migrations()


@contextmanager
def transaction():
    """One connection / one commit for a batch of statements (bulk seeding,
    multi-row saves) instead of a commit per statement."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(query, params=()):
    conn = get_connection()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def execute_rowcount(query, params=()):
    """Like execute(), but returns the number of rows changed (so
    INSERT OR IGNORE callers can tell inserted from already-present)."""
    conn = get_connection()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def query_all(query, params=()):
    conn = get_connection()
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def query_one(query, params=()):
    conn = get_connection()
    try:
        return conn.execute(query, params).fetchone()
    finally:
        conn.close()

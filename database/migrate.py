"""
Minimal versioned migration runner.

Migrations are numbered .sql files in database/migrations/ (001_..., 002_...).
Each is applied exactly once and recorded in `schema_migrations`, so the
schema can evolve without deleting the database and reseeding.

Usage:  python database/migrate.py          (apply anything pending)
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import get_connection


def _migration_files():
    if not os.path.isdir(config.MIGRATIONS_DIR):
        return []
    return sorted(f for f in os.listdir(config.MIGRATIONS_DIR) if f.endswith(".sql"))


def applied_versions():
    conn = get_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
        return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()


def run_migrations():
    """Applies pending migrations in order. Returns the list applied."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = get_connection()
    applied = []
    try:
        conn.execute("PRAGMA journal_mode = WAL")  # readers don't block the camera/job writers
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for filename in _migration_files():
            version = filename.split("_", 1)[0]
            if version in done:
                continue
            with open(os.path.join(config.MIGRATIONS_DIR, filename), "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            conn.commit()
            applied.append(filename)
    finally:
        conn.close()
    return applied


if __name__ == "__main__":
    applied = run_migrations()
    print("Applied:", ", ".join(applied) if applied else "nothing (already up to date)")

-- Platform tables: audit trail, login throttling, background jobs, app metadata.

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    username   TEXT,
    role       TEXT,
    ip         TEXT,
    action     TEXT NOT NULL,
    entity     TEXT,
    entity_id  TEXT,
    details    TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

CREATE TABLE IF NOT EXISTS login_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    ip           TEXT,
    success      INTEGER NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_user ON login_attempts(username, attempted_at);

CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
    progress     INTEGER NOT NULL DEFAULT 0,
    message      TEXT,
    result_json  TEXT,
    error        TEXT,
    submitted_by TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    started_at   TEXT,
    finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_name_status ON jobs(name, status);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- One row per student: their most recent prediction. Keyed on the
-- autoincrement id (not a timestamp) so two predictions in the same
-- second can never produce duplicate rows.
CREATE VIEW IF NOT EXISTS latest_predictions AS
SELECT p.* FROM predictions p
WHERE p.id = (SELECT MAX(p2.id) FROM predictions p2 WHERE p2.student_id = p.student_id);

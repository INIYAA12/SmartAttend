-- Initial schema

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK(role IN ('admin', 'teacher')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT UNIQUE NOT NULL,
    roll_number     TEXT,
    name            TEXT NOT NULL,
    department      TEXT,
    year            TEXT,
    section         TEXT,
    semester        TEXT,
    email           TEXT,
    previous_gpa    REAL,
    face_registered INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- SYLLABUS MANAGEMENT: subjects are now GLOBAL, not tied to a section.
-- Register a subject once here; it's reusable everywhere a subject is
-- needed (marks entry, live attendance, reports).
CREATE TABLE IF NOT EXISTS subjects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_code TEXT UNIQUE NOT NULL,
    subject_name TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL,
    subject_id  INTEGER NOT NULL,
    date        TEXT NOT NULL,
    time        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Present',
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE (student_id, subject_id, date)
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
);

-- MARKS: fully generic, no Exam Type. Subject + a free-typed exam name +
-- a total mark (set once per sheet, same for every student in it) +
-- each student's obtained mark. Percentage is computed and stored at
-- save time. Nothing here is flagged as "the final exam" -- every row is
-- just one more data point averaged into that student's overall
-- marks_average_percentage for prediction (see academic/marks.py).
CREATE TABLE IF NOT EXISTS marks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT NOT NULL,
    subject_id      INTEGER NOT NULL,
    exam_name       TEXT NOT NULL,
    total_marks     REAL NOT NULL,
    obtained_marks  REAL NOT NULL,
    percentage      REAL NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE (student_id, subject_id, exam_name)
);

CREATE TABLE IF NOT EXISTS predictions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id            TEXT NOT NULL,
    predicted_score       REAL NOT NULL,
    performance_category  TEXT NOT NULL,
    risk_level            TEXT NOT NULL,
    model_version         TEXT NOT NULL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);
CREATE INDEX IF NOT EXISTS idx_marks_student ON marks(student_id);
CREATE INDEX IF NOT EXISTS idx_marks_subject ON marks(subject_id);
CREATE INDEX IF NOT EXISTS idx_predictions_student ON predictions(student_id);

-- Migration 003: Case-insensitive exam names and unique constraint
PRAGMA foreign_keys = OFF;

CREATE TABLE marks_new (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT NOT NULL,
    subject_id      INTEGER NOT NULL,
    exam_name       TEXT COLLATE NOCASE NOT NULL,
    total_marks     REAL NOT NULL,
    obtained_marks  REAL NOT NULL,
    percentage      REAL NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE (student_id, subject_id, exam_name COLLATE NOCASE)
);

-- Copy existing data safely, deduplicating any case differences by keeping the most recently updated
INSERT INTO marks_new (id, student_id, subject_id, exam_name, total_marks, obtained_marks, percentage, created_at, updated_at)
SELECT id, student_id, subject_id, exam_name, total_marks, obtained_marks, percentage, created_at, updated_at
FROM marks
GROUP BY student_id, subject_id, lower(exam_name);

DROP TABLE marks;
ALTER TABLE marks_new RENAME TO marks;

CREATE INDEX IF NOT EXISTS idx_marks_student ON marks(student_id);
CREATE INDEX IF NOT EXISTS idx_marks_subject ON marks(subject_id);

PRAGMA foreign_keys = ON;

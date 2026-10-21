import datetime
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import execute_rowcount


def mark_attendance(student_id, subject_id, when=None):
    """Marks a student present. Returns True if newly marked, False if they
    were already marked for that subject today. The UNIQUE(student_id,
    subject_id, date) constraint makes this race-free: INSERT OR IGNORE is
    atomic, so two camera frames can never create a duplicate."""
    when = when or datetime.datetime.now()
    changed = execute_rowcount(
        "INSERT OR IGNORE INTO attendance (student_id, subject_id, date, time, status) VALUES (?, ?, ?, ?, 'Present')",
        (student_id, subject_id, when.date().isoformat(), when.strftime("%H:%M:%S")),
    )
    if changed == 1:
        try:
            from services.prediction_service import refresh_student_prediction
            refresh_student_prediction(student_id)
        except Exception:
            pass
    return changed == 1


"""
Marks entry and feature computation -- redesigned around a fully generic
exam model: Subject + a free-typed Exam Name + a Total Mark (same for
every student in that sheet) + each student's Obtained Mark. There is no
"Exam Type" category and nothing is flagged as "the final exam" -- every
row is just one more real data point.

For prediction, every mark a student has (across every subject and every
exam name) is averaged into ONE feature: marks_average_percentage.
Combined with real attendance % (computed from actual attendance records,
never typed in) and previous GPA (a one-time profile field), that's the
full feature set fed to the trained model.

Training itself still uses the synthetic baseline dataset
(data/academic_dataset.csv) -- there is no reliable "true final outcome"
signal in the free-form real marks data to train a regression target
against, so real data is used for INFERENCE (predicting a current
student's likely outcome), not for retraining the model itself. This is
a deliberate, documented choice, not an oversight.
"""

import os
import sys
import csv
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import query_all, query_one, execute


class MissingFeaturesError(Exception):
    """Raised when a student doesn't have enough data yet to build a
    complete feature row (missing marks, attendance, or GPA)."""
    def __init__(self, missing_fields):
        self.missing_fields = missing_fields
        super().__init__(f"Missing: {', '.join(missing_fields)}")


def upsert_mark(student_id, subject_id, exam_name, total_marks, obtained_marks):
    """
    Inserts a new mark, or UPDATES it in place if this exact
    (student, subject, exam_name) combination already exists -- this is
    what makes re-saving a sheet an edit rather than a duplicate.
    Exam name matching is case-insensitive.
    """
    if total_marks <= 0:
        raise ValueError("Total marks must be greater than 0.")
    exam_name = exam_name.strip()
    percentage = round((obtained_marks / total_marks) * 100, 2)

    execute(
        """
        INSERT INTO marks (student_id, subject_id, exam_name, total_marks, obtained_marks, percentage, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(student_id, subject_id, exam_name)
        DO UPDATE SET total_marks=excluded.total_marks,
                      obtained_marks=excluded.obtained_marks,
                      percentage=excluded.percentage,
                      updated_at=datetime('now')
        """,
        (student_id, subject_id, exam_name, total_marks, obtained_marks, percentage),
    )
    # Refresh student prediction so predictions never remain stale after marks entry
    try:
        from services.prediction_service import refresh_student_prediction
        refresh_student_prediction(student_id)
    except Exception:
        pass
    return percentage


def compute_attendance_percentage(student_id):
    """
    Derived automatically from real attendance records -- never typed in.
    The denominator represents sessions actually applicable to this student:
    - If the student belongs to a section, count distinct (date, subject_id)
      sessions held for students in that section (matching department/year if present).
    - If no peer section sessions exist or student has no section, look at subjects
      this student has attended or global sessions.
    - If no applicable sessions were ever held, returns None.
    - If sessions were held and the student attended none, returns 0.0.
    """
    student = query_one(
        "SELECT section, department, year FROM students WHERE student_id = ?",
        (student_id,),
    )
    if not student:
        return None

    section = (student["section"] or "").strip()
    dept = (student["department"] or "").strip()
    year = (student["year"] or "").strip()

    # Sessions attended by this student
    present_row = query_one(
        "SELECT COUNT(DISTINCT date || '-' || subject_id) AS c FROM attendance WHERE student_id = ?",
        (student_id,),
    )
    present = present_row["c"] if present_row else 0

    # Applicable sessions for student's academic group
    total = 0
    if section:
        if dept and year:
            query = """
                SELECT COUNT(DISTINCT a.date || '-' || a.subject_id) AS c
                FROM attendance a
                JOIN students s ON a.student_id = s.student_id
                WHERE s.section = ? AND s.department = ? AND s.year = ?
            """
            params = (section, dept, year)
        else:
            query = """
                SELECT COUNT(DISTINCT a.date || '-' || a.subject_id) AS c
                FROM attendance a
                JOIN students s ON a.student_id = s.student_id
                WHERE s.section = ?
            """
            params = (section,)
        total_row = query_one(query, params)
        total = total_row["c"] if total_row else 0

    if total == 0:
        total_sub_row = query_one(
            """
            SELECT COUNT(DISTINCT date || '-' || subject_id) AS c
            FROM attendance
            WHERE subject_id IN (SELECT DISTINCT subject_id FROM attendance WHERE student_id = ?)
            """,
            (student_id,),
        )
        total = total_sub_row["c"] if total_sub_row else 0
        if total == 0 and present == 0:
            all_sess = query_one("SELECT COUNT(DISTINCT date || '-' || subject_id) AS c FROM attendance")
            total = all_sess["c"] if all_sess else 0

    if total == 0:
        if present > 0:
            total = present
        else:
            return None

    total = max(total, present)
    if total == 0:
        return None

    pct = (present / total) * 100.0
    return round(min(100.0, max(0.0, pct)), 1)


def compute_marks_average_percentage(student_id):
    """
    Average percentage across EVERY mark this student has:
    AVG(percentage) across all recorded exams for the student.
    Protects against nulls and clamps between 0.0 and 100.0.
    """
    row = query_one(
        """
        SELECT AVG(percentage) AS avg_pct,
               COUNT(*) AS c
        FROM marks
        WHERE student_id = ? AND percentage IS NOT NULL
        """,
        (student_id,),
    )
    if not row or row["c"] == 0 or row["avg_pct"] is None:
        return None

    pct = row["avg_pct"]
    pct = max(0.0, min(100.0, pct))
    return round(pct, 1)



def compute_features_for_student(student_id):
    """
    Returns a dict with all ML feature columns for one student.
    Raises MissingFeaturesError (naming exactly what's missing) if the
    student doesn't have complete data yet.
    """
    student = query_one("SELECT previous_gpa FROM students WHERE student_id = ?", (student_id,))
    if not student:
        raise MissingFeaturesError(["student record not found"])

    attendance_pct = compute_attendance_percentage(student_id)
    marks_avg = compute_marks_average_percentage(student_id)
    previous_gpa = student["previous_gpa"]

    missing = []
    if attendance_pct is None:
        missing.append("attendance history (no sessions recorded yet)")
    if marks_avg is None:
        missing.append("marks (no exams entered yet)")
    if previous_gpa is None:
        missing.append("previous GPA (set it on the student's profile)")

    if missing:
        raise MissingFeaturesError(missing)

    return {
        "attendance_percentage": attendance_pct,
        "marks_average_percentage": marks_avg,
        "previous_gpa": previous_gpa,
    }


def get_marks_for_sheet(subject_id, section=None):
    """
    Returns every student (optionally filtered by section) with any
    existing mark for every exam_name already entered for this subject,
    pivoted so the marks-entry grid can show one row per (student, exam)
    pre-filled with whatever's already saved.
    """
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if section:
        query += " AND section = ?"
        params.append(section)
    query += " ORDER BY name"
    students = query_all(query, tuple(params))

    marks = query_all(
        "SELECT * FROM marks WHERE subject_id = ? ORDER BY student_id",
        (subject_id,),
    )
    marks_by_student = {}
    for m in marks:
        marks_by_student.setdefault(m["student_id"], []).append(m)

    return students, marks_by_student


def export_sheet_csv(subject_id, exam_name):
    rows = query_all(
        """
        SELECT st.student_id, st.name, st.roll_number, m.total_marks, m.obtained_marks, m.percentage
        FROM students st
        LEFT JOIN marks m ON m.student_id = st.student_id AND m.subject_id = ? AND m.exam_name = ?
        ORDER BY st.name
        """,
        (subject_id, exam_name),
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_id", "name", "roll_number", "total_marks", "obtained_marks", "percentage"])
    for r in rows:
        writer.writerow([r["student_id"], r["name"], r["roll_number"], r["total_marks"], r["obtained_marks"], r["percentage"]])
    return buf.getvalue()

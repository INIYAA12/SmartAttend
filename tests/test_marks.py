import os
import sys
import unittest
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MarksTestCase(unittest.TestCase):
    def setUp(self):
        import config
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.DATABASE_PATH = self.tmp_db.name

        from database.db import init_db, execute
        init_db()
        execute("INSERT INTO students (student_id, name, previous_gpa) VALUES (?, ?, ?)",
                ("STU001", "Test Student", 8.5))
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)",
                ("CS101", "Machine Learning"))
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)",
                ("CS102", "Data Structures"))
        self.execute = execute

    def tearDown(self):
        os.unlink(self.tmp_db.name)

    def test_upsert_mark_computes_correct_percentage(self):
        from academic.marks import upsert_mark
        pct = upsert_mark("STU001", 1, "Mid Term 1", 100, 85)
        self.assertEqual(pct, 85.0)

    def test_upsert_same_exam_updates_not_duplicates(self):
        from academic.marks import upsert_mark
        from database.db import query_all
        upsert_mark("STU001", 1, "Mid Term 1", 100, 70)
        upsert_mark("STU001", 1, "Mid Term 1", 100, 90)  # same subject+exam_name -> update
        rows = query_all("SELECT * FROM marks WHERE student_id = ? AND subject_id = 1", ("STU001",))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["obtained_marks"], 90.0)

    def test_different_exam_names_create_separate_rows(self):
        from academic.marks import upsert_mark
        from database.db import query_all
        upsert_mark("STU001", 1, "Mid Term 1", 100, 70)
        upsert_mark("STU001", 1, "Surprise Quiz", 20, 18)
        rows = query_all("SELECT * FROM marks WHERE student_id = ?", ("STU001",))
        self.assertEqual(len(rows), 2)

    def test_upsert_rejects_zero_total_marks(self):
        from academic.marks import upsert_mark
        with self.assertRaises(ValueError):
            upsert_mark("STU001", 1, "Broken Exam", 0, 5)

    def test_marks_average_percentage_averages_across_subjects_and_exams(self):
        from academic.marks import upsert_mark, compute_marks_average_percentage
        upsert_mark("STU001", 1, "Mid Term 1", 100, 80)   # 80%
        upsert_mark("STU001", 1, "Surprise Quiz", 20, 16)  # 80%
        upsert_mark("STU001", 2, "Unit Test", 50, 30)      # 60%
        avg = compute_marks_average_percentage("STU001")
        self.assertAlmostEqual(avg, (80 + 80 + 60) / 3, places=1)

    def test_attendance_percentage_none_when_no_sessions_exist(self):
        from academic.marks import compute_attendance_percentage
        self.assertIsNone(compute_attendance_percentage("STU001"))

    def test_attendance_percentage_computed_correctly(self):
        import datetime
        today = datetime.date.today().isoformat()
        # Two sessions held for subject 1 (by anyone), student only in one
        self.execute("INSERT INTO students (student_id, name) VALUES (?, ?)", ("STU002", "Other Student"))
        self.execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, ?, '09:00', 'Present')", ("STU001", today))
        self.execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, ?, '09:00', 'Present')", ("STU002", "2020-01-01"))

        from academic.marks import compute_attendance_percentage
        pct = compute_attendance_percentage("STU001")
        self.assertEqual(pct, 50.0)  # present for 1 of 2 distinct sessions

    def test_compute_features_raises_with_specific_missing_fields(self):
        from academic.marks import compute_features_for_student, MissingFeaturesError
        self.execute("INSERT INTO students (student_id, name) VALUES (?, ?)", ("BLANK", "Blank Student"))
        with self.assertRaises(MissingFeaturesError) as ctx:
            compute_features_for_student("BLANK")
        missing_text = " ".join(ctx.exception.missing_fields)
        self.assertIn("attendance", missing_text.lower())
        self.assertIn("marks", missing_text.lower())
        self.assertIn("gpa", missing_text.lower())

    def test_compute_features_succeeds_with_complete_data(self):
        import datetime
        today = datetime.date.today().isoformat()
        self.execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, ?, '09:00', 'Present')", ("STU001", today))
        from academic.marks import upsert_mark, compute_features_for_student
        upsert_mark("STU001", 1, "Mid Term 1", 100, 80)

        features = compute_features_for_student("STU001")
        self.assertEqual(features["attendance_percentage"], 100.0)
        self.assertEqual(features["marks_average_percentage"], 80.0)
        self.assertEqual(features["previous_gpa"], 8.5)

    def test_no_exam_type_column_in_schema(self):
        """The whole point of this redesign -- exam_type must not exist anymore."""
        from database.db import get_connection
        conn = get_connection()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(marks)").fetchall()]
        conn.close()
        self.assertNotIn("exam_type", cols)
        self.assertIn("exam_name", cols)

    def test_subjects_table_has_no_section_column(self):
        """Subjects are global now -- no per-section subject rows."""
        from database.db import get_connection
        conn = get_connection()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(subjects)").fetchall()]
        conn.close()
        self.assertNotIn("section", cols)


if __name__ == "__main__":
    unittest.main()

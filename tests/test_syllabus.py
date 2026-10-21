import os, sys, unittest, tempfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SyllabusTestCase(unittest.TestCase):
    def setUp(self):
        import config
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.DATABASE_PATH = self.tmp_db.name
        from database.db import init_db, execute
        init_db()
        from werkzeug.security import generate_password_hash
        execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", generate_password_hash("admin123"), "admin"))
        from app import create_app
        self.client = create_app().test_client()
        self.client.post("/login", data={"username": "admin", "password": "admin123"})

    def tearDown(self):
        os.unlink(self.tmp_db.name)

    def test_add_subject(self):
        r = self.client.post("/syllabus/add", data={"subject_code": "CS999", "subject_name": "Deep Learning"}, follow_redirects=True)
        self.assertIn(b"added", r.data.lower())
        from database.db import query_one
        row = query_one("SELECT * FROM subjects WHERE subject_code = ?", ("CS999",))
        self.assertIsNotNone(row)

    def test_duplicate_subject_code_rejected(self):
        self.client.post("/syllabus/add", data={"subject_code": "CS999", "subject_name": "Deep Learning"})
        r = self.client.post("/syllabus/add", data={"subject_code": "CS999", "subject_name": "Another Name"}, follow_redirects=True)
        self.assertIn(b"already exists", r.data)
        from database.db import query_all
        rows = query_all("SELECT * FROM subjects WHERE subject_code = ?", ("CS999",))
        self.assertEqual(len(rows), 1)

    def test_subject_usable_across_sections(self):
        """A single global subject should show up regardless of which
        section's students are being marked -- no per-section duplication."""
        from database.db import execute, query_all
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", ("CS500", "Global Subject"))
        execute("INSERT INTO students (student_id, name, section) VALUES (?, ?, ?)", ("A1", "Student A", "A"))
        execute("INSERT INTO students (student_id, name, section) VALUES (?, ?, ?)", ("B1", "Student B", "B"))

        from academic.marks import get_marks_for_sheet
        subject_id = query_all("SELECT id FROM subjects WHERE subject_code = ?", ("CS500",))[0]["id"]
        students_a, _ = get_marks_for_sheet(subject_id, section="A")
        students_b, _ = get_marks_for_sheet(subject_id, section="B")
        self.assertEqual([s["student_id"] for s in students_a], ["A1"])
        self.assertEqual([s["student_id"] for s in students_b], ["B1"])

    def test_delete_subject_blocked_if_in_use(self):
        from database.db import execute, query_one
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", ("CS600", "In-Use Subject"))
        subject_id = query_one("SELECT id FROM subjects WHERE subject_code = ?", ("CS600",))["id"]
        execute("INSERT INTO students (student_id, name) VALUES (?, ?)", ("S1", "Student"))
        execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, ?, '2026-01-01', '09:00', 'Present')",
                ("S1", subject_id))

        r = self.client.post(f"/syllabus/{subject_id}/delete", follow_redirects=True)
        self.assertIn(b"Can", r.data)  # "Can't delete..."
        still_there = query_one("SELECT id FROM subjects WHERE id = ?", (subject_id,))
        self.assertIsNotNone(still_there)


if __name__ == "__main__":
    unittest.main()
